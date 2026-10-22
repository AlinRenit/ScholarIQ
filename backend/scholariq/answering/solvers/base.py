"""Common shapes for solver results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Solution:
    solver: str  # machine name, e.g. "master-theorem"
    title: str
    result: str
    steps: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    concept: str | None = None  # knowledge-base concept this problem belongs to


@dataclass
class SolverError:
    """The input is of a supported kind but cannot be solved as given."""

    solver: str
    message: str
    concept: str | None = None


class Solver(Protocol):
    name: str
    description: str

    def solve(self, text: str) -> Solution | SolverError | None: ...
