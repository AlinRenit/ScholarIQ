"""What the running build can actually do.

Shown in the UI so students never see a feature presented as working before it
is implemented and tested. Update the status as milestones land.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class CapabilityStatus(StrEnum):
    AVAILABLE = "available"
    PLANNED = "planned"


class Capability(BaseModel):
    key: str
    label: str
    milestone: int
    status: CapabilityStatus


def _c(key: str, label: str, milestone: int, status: CapabilityStatus) -> Capability:
    return Capability(key=key, label=label, milestone=milestone, status=status)


_A, _P = CapabilityStatus.AVAILABLE, CapabilityStatus.PLANNED

CAPABILITIES: list[Capability] = [
    _c("foundation", "Health checks, configuration and database schema", 1, _A),
    _c("marksheet_import", "Marksheet import (PDF, image, CSV, XLSX) with review", 2, _A),
    _c("analytics", "Subject analytics and topic evidence classification", 3, _A),
    _c("knowledge_base", "Computer Science knowledge base and lexical retrieval", 4, _A),
    _c("tutor", "Question understanding and answer handlers", 5, _A),
    _c("diagnostics", "Diagnostic quizzes and study plans", 6, _A),
    _c("hardening", "Security, offline and accessibility hardening", 7, _A),
]
