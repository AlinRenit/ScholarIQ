from __future__ import annotations

import pytest
from pydantic import ValidationError

from scholariq.core.config import Settings


def make(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type, call-arg]


def test_defaults_are_valid() -> None:
    s = make()
    assert s.strict_ai_env_check is True
    assert not s.is_sqlite


def test_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCHOLARIQ_MAX_UPLOAD_BYTES", "2048")
    monkeypatch.setenv("SCHOLARIQ_LOG_LEVEL", "debug")
    s = make()
    assert s.max_upload_bytes == 2048
    assert s.log_level == "DEBUG"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"database_url": "mysql://x"},
        {"deployment_mode": "offline"},  # postgres URL with offline mode
        {"environment": "production"},  # default secret key
        {"environment": "production", "secret_key": "short"},
        {"max_upload_bytes": 0},
        {"upload_retention_days": -1},
        {"log_level": "LOUD"},
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make(**kwargs)


def test_offline_mode_with_sqlite() -> None:
    s = make(deployment_mode="offline", database_url="sqlite:///./scholariq.db")
    assert s.is_sqlite


def test_production_with_strong_secret() -> None:
    make(environment="production", secret_key="x" * 40)
