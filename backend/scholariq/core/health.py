"""Readiness checks. Each returns a CheckResult; none of them use the network."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from scholariq.compliance.runtime import check_environment
from scholariq.core.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class CheckStatus(StrEnum):
    OK = "ok"
    # Optional capability missing; core features still work.
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str
    required: bool = True


def expected_schema_revision() -> str | None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(cfg).get_current_head()


def check_database(engine: Engine) -> CheckResult:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001 - surfaced as a failed check
        return CheckResult("database", CheckStatus.FAILED, f"{type(exc).__name__}")
    head = expected_schema_revision()
    if current != head:
        return CheckResult(
            "database", CheckStatus.FAILED, f"schema at {current}, expected {head}; run migrations"
        )
    return CheckResult("database", CheckStatus.OK, f"{engine.dialect.name}, schema {current}")


def check_upload_dir(settings: Settings) -> CheckResult:
    path = settings.upload_dir
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CheckResult("upload_storage", CheckStatus.FAILED, f"cannot create: {exc.strerror}")
    if not os.access(path, os.W_OK):
        return CheckResult("upload_storage", CheckStatus.FAILED, "not writable")
    return CheckResult("upload_storage", CheckStatus.OK, "writable")


def check_content_dir(settings: Settings) -> CheckResult:
    if not settings.content_dir.is_dir():
        return CheckResult("knowledge_content", CheckStatus.FAILED, "content directory missing")
    return CheckResult("knowledge_content", CheckStatus.OK, "present")


def check_ocr(settings: Settings) -> CheckResult:
    binary = settings.tesseract_cmd or shutil.which("tesseract")
    if binary and Path(binary).exists():
        return CheckResult("ocr", CheckStatus.OK, "tesseract found", required=False)
    return CheckResult(
        "ocr",
        CheckStatus.DEGRADED,
        "tesseract not found; scanned PDFs and images cannot be imported",
        required=False,
    )


def check_ai_compliance() -> CheckResult:
    found = check_environment()
    if found:
        return CheckResult(
            "no_external_ai",
            CheckStatus.FAILED,
            "AI provider variables set: " + ", ".join(found),
        )
    return CheckResult("no_external_ai", CheckStatus.OK, "no AI provider configuration present")


def overall(results: list[CheckResult]) -> CheckStatus:
    if any(r.status is CheckStatus.FAILED and r.required for r in results):
        return CheckStatus.FAILED
    if any(r.status is not CheckStatus.OK for r in results):
        return CheckStatus.DEGRADED
    return CheckStatus.OK
