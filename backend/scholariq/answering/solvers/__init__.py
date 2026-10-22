"""Deterministic solvers for defined problem families (Handler D).

Each solver recognises its own inputs strictly and returns ``None`` for
anything else, so a solver never guesses at a question it was not built for.
The registry tries them in a fixed order.
"""

from __future__ import annotations

from scholariq.answering.solvers.arithmetic import ArithmeticSolver, PercentageSolver
from scholariq.answering.solvers.base import Solution, Solver, SolverError
from scholariq.answering.solvers.equations import EquationSolver
from scholariq.answering.solvers.graph import GraphSolver
from scholariq.answering.solvers.logic import TruthTableSolver
from scholariq.answering.solvers.recurrence import RecurrenceSolver
from scholariq.answering.solvers.sql import SqlSolver

SOLVERS: tuple[Solver, ...] = (
    RecurrenceSolver(),
    TruthTableSolver(),
    SqlSolver(),
    GraphSolver(),
    PercentageSolver(),
    EquationSolver(),
    ArithmeticSolver(),
)


def solve(text: str) -> Solution | SolverError | None:
    """First solver that recognises the text wins; None if none does."""
    for solver in SOLVERS:
        result = solver.solve(text)
        if result is not None:
            return result
    return None


SUPPORTED = [s.description for s in SOLVERS]

__all__ = ["SOLVERS", "SUPPORTED", "Solution", "Solver", "SolverError", "solve"]
