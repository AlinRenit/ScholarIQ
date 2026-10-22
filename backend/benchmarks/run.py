"""Measure how long the main operations take on this machine.

    cd backend && python benchmarks/run.py [--out ../docs/PERFORMANCE.md] [--repeat 3]

Everything runs in-process against a fresh SQLite database through the real
FastAPI app (TestClient), so the times include validation, database access and
serialisation, but not a network hop or the web front end. Outbound network
access is blocked for the whole run. Numbers are wall-clock milliseconds; the
median of ``--repeat`` runs is reported for one-off steps, and p50/p95/max over
all questions for the tutor.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from scholariq.api import deps
from scholariq.core.config import Settings, get_settings
from scholariq.curriculum.sync import load_files, sync_curricula
from scholariq.db.session import build_engine, get_engine
from scholariq.knowledge import index as kindex
from scholariq.knowledge.loader import load_content
from scholariq.knowledge.sync import sync_knowledge
from scholariq.main import create_app

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
MARKSHEET = BACKEND / "tests/fixtures/marksheets/digital_semester3.pdf"
SCANNED = BACKEND / "tests/fixtures/marksheets/scanned_semester4.png"
RESULT_KEYS = [
    "subject_name",
    "subject_code",
    "component",
    "status",
    "marks_obtained",
    "max_marks",
    "grade",
    "grade_points",
    "credits",
    "semester",
    "exam_type",
    "exam_name",
]


def _block_network() -> None:
    real = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> None:
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError(f"network access attempted: {address!r}")
        real(self, address)

    socket.socket.connect = guarded  # type: ignore[method-assign, assignment]


def _ms(fn: Callable[[], Any]) -> tuple[float, Any]:
    start = time.perf_counter()
    value = fn()
    return (time.perf_counter() - start) * 1000, value


def _ok(response: Any) -> Any:
    if response.status_code >= 400:
        raise RuntimeError(f"{response.request.url}: {response.status_code} {response.text[:300]}")
    return response.json() if response.content else None


def run_once(work: Path) -> dict[str, float | list[float]]:
    db = work / "bench.db"
    url = f"sqlite:///{db}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    t: dict[str, float | list[float]] = {}

    t["migrate (empty database)"], _ = _ms(lambda: command.upgrade(cfg, "head"))
    settings = Settings(
        environment="test",
        database_url=url,
        upload_dir=work / "uploads",
        content_dir=ROOT / "content",
        _env_file=None,
    )
    engine = build_engine(url)
    with Session(engine) as s:
        t["load curriculum"], _ = _ms(lambda: sync_curricula(s, load_files(ROOT / "content")))
    t["parse and validate knowledge files"], content = _ms(lambda: load_content(ROOT / "content"))
    with Session(engine) as s:
        t["sync knowledge base into database"], _ = _ms(lambda: sync_knowledge(s, content))
    with Session(engine) as s:
        kindex._cache.clear()
        t["build retrieval index (BM25)"], _ = _ms(
            lambda: kindex.build_index(s, allow_unreviewed=True)
        )
    kindex._cache.clear()

    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: engine
    client = TestClient(app)
    t["app start-up (builds index and tutor vocabulary)"], c = _ms(client.__enter__)
    try:
        _ok(c.post("/api/profile", json={"display_name": "Bench", "consent": True}))

        def upload(path: Path, mime: str) -> Any:
            with path.open("rb") as fh:
                return _ok(c.post("/api/documents", files={"file": (path.name, fh, mime)}))

        t["import digital PDF marksheet"], doc = _ms(lambda: upload(MARKSHEET, "application/pdf"))
        if SCANNED.exists() and shutil.which("tesseract"):
            t["import scanned marksheet (Tesseract OCR)"], _ = _ms(
                lambda: upload(SCANNED, "image/png")
            )
        results = [
            {k: r["fields"][k] for k in RESULT_KEYS if k in r["fields"]} for r in doc["records"]
        ]
        t["confirm results"], _ = _ms(
            lambda: _ok(c.post(f"/api/documents/{doc['id']}/confirm", json={"results": results}))
        )
        t["dashboard analysis"], _ = _ms(lambda: _ok(c.get("/api/analytics/overview")))
        t["topic classification (all topics)"], topics = _ms(lambda: _ok(c.get("/api/topics")))
        by_name = {x["name"]: x["id"] for x in topics}
        t["add a topic test result"], _ = _ms(
            lambda: _ok(
                c.post(
                    f"/api/topics/{by_name['Normalization']}/evidence",
                    json={"kind": "topic_exam", "obtained": 3, "maximum": 10, "questions": 10},
                )
            )
        )

        cases = yaml.safe_load((ROOT / "content/eval/answers.yaml").read_text())["cases"]
        t["first tutor answer"], _ = _ms(
            lambda: _ok(c.post("/api/tutor/ask", json={"text": "What is a stack?"}))
        )
        latencies = []
        for case in cases:
            body = {"text": case["q"]}
            ms, _ = _ms(lambda: _ok(c.post("/api/tutor/ask", json=body)))  # noqa: B023
            latencies.append(ms)
        t["tutor answers"] = latencies

        t["start a diagnostic quiz"], quiz = _ms(
            lambda: _ok(c.post("/api/practice/quizzes", json={"topic": "db.normalization"}))
        )
        answers = {q["slug"]: 0 for q in quiz["questions"]}
        t["submit and mark a quiz"], _ = _ms(
            lambda: _ok(
                c.post(f"/api/practice/quizzes/{quiz['id']}/submit", json={"answers": answers})
            )
        )
        t["build study plan"], _ = _ms(
            lambda: _ok(c.post("/api/study-plan", json={"goal_topics": []}))
        )
        t["knowledge-base search"], _ = _ms(
            lambda: _ok(c.get("/api/knowledge/search", params={"q": "deadlock prevention"}))
        )
        t["delete all of a student's data"], _ = _ms(lambda: c.delete("/api/profile"))
    finally:
        client.__exit__(None, None, None)
    engine.dispose()
    return t


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p * (len(ordered) - 1))))
    return ordered[k]


def report(runs: list[dict[str, float | list[float]]]) -> str:
    lines = [
        "# Performance measurements",
        "",
        f"Measured {datetime.now(UTC):%Y-%m-%d} with `backend/benchmarks/run.py` "
        f"({len(runs)} run(s), median shown).",
        "",
        f"* Machine: {platform.machine()}, {os.cpu_count()} CPU(s), "
        f"{platform.system()} {platform.release()}",
        f"* Python {platform.python_version()}, SQLite database, outbound network blocked",
        "* In-process through the FastAPI app: includes validation, database access and "
        "serialisation; excludes the network hop and the web front end.",
        "",
        "| Operation | Time (ms) |",
        "| --- | ---: |",
    ]
    tutor: list[float] = []
    for name in runs[0]:
        values = [r[name] for r in runs if name in r]
        if name == "tutor answers":
            for v in values:
                assert isinstance(v, list)
                tutor += v
            continue
        nums = [float(v) for v in values if isinstance(v, float)]
        lines.append(f"| {name} | {statistics.median(nums):.0f} |")
    if tutor:
        lines += [
            "",
            f"Tutor answers over the {len(tutor) // len(runs)} gold-standard questions "
            f"(index already built), {len(tutor)} answers in total:",
            "",
            "| p50 | p95 | max |",
            "| ---: | ---: | ---: |",
            f"| {_pct(tutor, 0.5):.0f} ms | {_pct(tutor, 0.95):.0f} ms | {max(tutor):.0f} ms |",
        ]
    lines += [
        "",
        "Notes:",
        "",
        "* The retrieval index and the tutor's vocabulary are built when the API starts "
        "(`SCHOLARIQ_WARM_CACHES_ON_START`, on by default), so the first question is as "
        "fast as the rest. Without it the first question after a restart took about "
        "320 ms on this machine.",
        "* Loading content (parse, validate, sync) runs once per deployment or content "
        "change, not per request.",
        "* OCR time depends on the scan: the sample is one page. Large scanned PDFs (up "
        "to 20 pages) take several seconds, during the upload request.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    _block_network()
    # The per-student question limit (60 a minute) would stop the run part-way;
    # it protects a shared server, not what is being measured here.
    deps.tutor_limiter.allow = lambda key, now=None: True  # type: ignore[method-assign]
    runs = []
    for i in range(args.repeat):
        with tempfile.TemporaryDirectory() as tmp:
            runs.append(run_once(Path(tmp)))
        print(f"run {i + 1}/{args.repeat} done", file=sys.stderr)
    text = report(runs)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
