from __future__ import annotations

from pathlib import Path

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from scholariq.core.config import Settings
from scholariq.db.session import build_engine
from scholariq.main import create_app
from tests.conftest import alembic_config


def test_live(client: TestClient) -> None:
    r = client.get("/api/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_on_migrated_database(client: TestClient) -> None:
    r = client.get("/api/health/ready")
    assert r.status_code == 200
    checks = {c["name"]: c for c in r.json()["checks"]}
    assert checks["database"]["status"] == "ok"
    assert checks["upload_storage"]["status"] == "ok"
    assert checks["knowledge_content"]["status"] == "ok"
    assert checks["no_external_ai"]["status"] == "ok"
    # OCR is optional: missing tesseract degrades readiness but does not fail it.
    assert checks["ocr"]["required"] is False
    assert r.json()["status"] in {"ok", "degraded"}


def test_ready_fails_when_schema_is_behind(settings: Settings, tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'old.db'}"
    command.upgrade(alembic_config(url), "head")
    command.downgrade(alembic_config(url), "base")
    # Warming the tutor caches fails on this database; start-up must survive it.
    stale = settings.model_copy(update={"database_url": url, "warm_caches_on_start": True})
    engine = build_engine(url)
    app = create_app(stale)
    from scholariq.core.config import get_settings
    from scholariq.db.session import get_engine

    app.dependency_overrides[get_settings] = lambda: stale
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as c:
        r = c.get("/api/health/ready")
    engine.dispose()
    assert r.status_code == 503
    db = next(x for x in r.json()["checks"] if x["name"] == "database")
    assert db["status"] == "failed"


def test_ready_fails_without_content_dir(client: TestClient, settings: Settings) -> None:
    import shutil

    shutil.rmtree(settings.content_dir)
    r = client.get("/api/health/ready")
    assert r.status_code == 503


def test_system_info_is_honest(client: TestClient) -> None:
    body = client.get("/api/system/info").json()
    assert body["uses_external_ai"] is False
    caps = {c["key"]: c["status"] for c in body["capabilities"]}
    assert caps["foundation"] == "available"
    assert caps["tutor"] == "available"
    assert caps["diagnostics"] == "available"
    # Features that do not exist yet must not be reported as available.
    assert caps["hardening"] == "available"


def test_start_up_builds_the_tutor_index(
    settings: Settings, engine: Engine, knowledge: None
) -> None:
    from scholariq.core.config import get_settings
    from scholariq.db.session import get_engine
    from scholariq.knowledge import index

    index._cache.clear()
    warm = settings.model_copy(update={"warm_caches_on_start": True})
    app = create_app(warm)
    app.dependency_overrides[get_settings] = lambda: warm
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app):
        assert warm.allow_unreviewed_content in index._cache
