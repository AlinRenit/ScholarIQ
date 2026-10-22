from __future__ import annotations

import ipaddress
import shutil
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from scholariq.compliance.policy import PROHIBITED_ENV_VARS
from scholariq.core.config import Settings, get_settings
from scholariq.curriculum.sync import load_files, sync_curricula
from scholariq.db.session import build_engine, get_engine
from scholariq.knowledge.loader import KnowledgeContent, load_content
from scholariq.knowledge.sync import sync_knowledge
from scholariq.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

_real_connect = socket.socket.connect


def _is_local(address: object) -> bool:
    if isinstance(address, (str, bytes)):  # AF_UNIX path
        return True
    host = address[0] if isinstance(address, tuple) else None
    if host in ("localhost", None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs with outbound network blocked; only loopback is allowed.

    The intelligence pipeline must work offline, so any test that tries to
    reach the internet fails loudly instead of passing by accident.
    """

    def guarded(self: socket.socket, address: object) -> None:
        if not _is_local(address):
            raise RuntimeError(f"network access attempted during test: {address!r}")
        _real_connect(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture(autouse=True)
def _clean_ai_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a clean install even if the developer's shell has AI keys set.

    Tests that exercise the refusal path set the variables explicitly.
    """
    for name in PROHIBITED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def migrated_url(database_url: str) -> str:
    command.upgrade(alembic_config(database_url), "head")
    return database_url


@pytest.fixture
def settings(tmp_path: Path, migrated_url: str) -> Settings:
    content = tmp_path / "content"
    shutil.copytree(REPO_ROOT / "content", content)
    return Settings(
        environment="test",
        database_url=migrated_url,
        upload_dir=tmp_path / "uploads",
        content_dir=content,
        warm_caches_on_start=False,
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    eng = build_engine(settings.database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def curriculum(settings: Settings, engine: Engine) -> None:
    """Load the seed curriculum from the (copied) content directory."""
    with Session(engine) as session:
        sync_curricula(session, load_files(settings.content_dir))


@pytest.fixture(scope="session")
def knowledge_content() -> KnowledgeContent:
    """The repository's knowledge files, parsed and validated once per run."""
    return load_content(REPO_ROOT / "content")


@pytest.fixture
def knowledge(curriculum: None, engine: Engine, knowledge_content: KnowledgeContent) -> None:
    """Load the seed knowledge base (after the curriculum it refers to)."""
    with Session(engine) as session:
        sync_knowledge(session, knowledge_content)


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as c:
        yield c
