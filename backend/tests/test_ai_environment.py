from __future__ import annotations

import pytest

from scholariq.compliance.runtime import ComplianceError, enforce_environment
from scholariq.core.config import Settings
from scholariq.main import create_app


def test_strict_mode_refuses_ai_credentials() -> None:
    with pytest.raises(ComplianceError, match="OPENAI_API_KEY"):
        enforce_environment(True, {"OPENAI_API_KEY": "sk-test", "PATH": "/bin"})


def test_lenient_mode_reports_without_failing() -> None:
    assert enforce_environment(False, {"ANTHROPIC_API_KEY": "x"}) == ["ANTHROPIC_API_KEY"]


def test_empty_values_are_ignored() -> None:
    assert enforce_environment(True, {"OPENAI_API_KEY": ""}) == []


def test_app_refuses_to_start_with_ai_key(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    with pytest.raises(ComplianceError):
        create_app(settings)
