"""Startup-time compliance checks."""

from __future__ import annotations

import os
from collections.abc import Mapping

from scholariq.compliance.policy import present_prohibited_env_vars


class ComplianceError(RuntimeError):
    pass


def check_environment(environ: Mapping[str, str] | None = None) -> list[str]:
    """Return prohibited AI-provider variables found in the environment."""
    return present_prohibited_env_vars(dict(os.environ if environ is None else environ))


def enforce_environment(strict: bool, environ: Mapping[str, str] | None = None) -> list[str]:
    found = check_environment(environ)
    if found and strict:
        raise ComplianceError(
            "AI provider credentials are set in the environment: "
            + ", ".join(found)
            + ". ScholarIQ never uses them; unset them, or set "
            "SCHOLARIQ_STRICT_AI_ENV_CHECK=false to start with a warning."
        )
    return found
