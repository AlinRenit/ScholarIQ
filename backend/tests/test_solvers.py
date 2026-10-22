"""Deterministic solvers and static code analysis."""

from __future__ import annotations

import pytest

from scholariq.answering.code import analyse_python, detect_language
from scholariq.answering.solvers import Solution, SolverError, solve
from scholariq.answering.solvers.arithmetic import ArithmeticSolver


def result(text: str) -> str:
    r = solve(text)
    assert isinstance(r, Solution), r
    return r.result


def error(text: str) -> str:
    r = solve(text)
    assert isinstance(r, SolverError), r
    return r.message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what is 2+3*4", "2+3*4 = 14"),
        ("(1/3)+(1/6)", "(1/3)+(1/6) = 1/2 (about 0.5)"),
        ("2^10 + 5", "2^10 + 5 = 1029"),
        ("15% of 80", "15% of 80 = 12"),
        ("45 is what percent of 60", "45 is 75% of 60"),
        ("percentage change from 50 to 65", "From 50 to 65 is a change of 30%"),
        ("42 out of 60 as a percentage", "42 out of 60 = 70%"),
        ("solve 2x + 3 = 7", "x = 2"),
        ("x^2 - 5x + 6 = 0", "x = 2 or 3"),
        ("solve for y: 4y - 2 = 2y + 8", "y = 5"),
        ("3(x+1) = 3x + 3", "True for every x"),
        ("x^2 + 1 = 0", "No real solutions"),
        ("Solve T(n) = 2T(n/2) + n", "T(n) = Θ(n log n)"),
        ("T(n) = T(n/2) + 1", "T(n) = Θ(log n)"),
        ("T(n) = 8T(n/2) + n^2", "T(n) = Θ(n^3)"),
        ("T(n) = 2T(n/2) + n^2", "T(n) = Θ(n^2)"),
        ("T(n) = 4T(n/2) + n^2 log n", "T(n) = Θ(n^2 (log n)^2)"),
        ("T(n) = T(n-1) + n", "T(n) = Θ(n^2)"),
        ("T(n) = 2T(n-1) + 1", "T(n) = Θ(2^n)"),
        ("is p | !p a tautology?", "(p ∨ ¬p) is a tautology (true in every row)."),
        ("truth table for p -> q", "(p → q) is contingent (true in 3 of 4 rows)."),
        ("BFS from A on edges A-B, A-C, B-D, C-D, D-E", "BFS order: A, B, C, D, E"),
        ("dfs starting at 1 edges 1-2, 1-3, 2-4, 3-4", "DFS order: 1, 2, 4, 3"),
        (
            "shortest path from A to D with edges A-B:1, B-C:2, A-C:5, C-D:1",
            "Shortest A to D: 4 via A → B → C → D",
        ),
    ],
)
def test_solvers(text: str, expected: str) -> None:
    assert result(text) == expected


def test_irrational_roots_in_surd_form() -> None:
    assert result("x^2 = 2").startswith("x = ± √2, about -1.41421 or 1.41421")


def test_truth_table_rows() -> None:
    r = solve("truth table for p and q")
    assert isinstance(r, Solution)
    assert r.columns == ["p", "q", "(p ∧ q)"]
    assert r.rows[0] == ["T", "T", "T"] and r.rows[-1] == ["F", "F", "F"]


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("calculate 7/0", "division by zero"),
        ("2^5000", "powers above 1000"),
        ("x^3 = 8", "only linear and quadratic"),
        ("T(n) = T(n/2) + T(n/3) + n", "more than one recursive term"),
        ("truth table for p &&& q", "Could not read"),
    ],
)
def test_supported_kinds_with_bad_input_explain_why(text: str, fragment: str) -> None:
    assert fragment in error(text)


@pytest.mark.parametrize(
    "text", ["what is a stack", "explain tcp and udp", "__import__('os').system('ls')", "1 2 3"]
)
def test_solvers_do_not_claim_other_questions(text: str) -> None:
    assert solve(text) is None


def test_arithmetic_never_evaluates_python() -> None:
    assert ArithmeticSolver().solve("2 + __import__('os')") is None


# ------------------------------------------------------------------------ SQL


def test_sql_runs_select_on_practice_data() -> None:
    r = solve(
        "SELECT name, marks FROM students JOIN enrollments ON id = student_id "
        "WHERE course_id = 'CS201' ORDER BY marks DESC"
    )
    assert isinstance(r, Solution)
    assert r.columns == ["name", "marks"]
    assert r.rows == [["Divya", "92"], ["Asha", "78"], ["Ben", "55"]]
    assert r.concept == "db.sql-joins"


@pytest.mark.parametrize(
    ("sql", "fragment"),
    [
        ("select count(*) from students; drop table students", "one SELECT statement"),
        ("SELECT * FROM sqlite_master", "could not run"),
        ("SELECT load_extension('x') FROM students", "only reading"),
        (
            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c",
            "took too long",
        ),
    ],
)
def test_sql_sandbox_refuses_unsafe_or_runaway_queries(sql: str, fragment: str) -> None:
    assert fragment in error(sql)


# ------------------------------------------------------------------- code


def complexity(code: str, name: str | None = None) -> str:
    r = analyse_python(code)
    unit = next(f for f in r.functions if f.name == name) if name else r.top_level
    assert unit is not None
    return unit.cost.show()


def test_code_templates() -> None:
    assert complexity("for i in range(n):\n    for j in range(n):\n        s += 1\n") == "Θ(n^2)"
    assert complexity("for i in range(10):\n    s += i\n") == "Θ(1)"
    binary = (
        "def bs(a, x):\n    lo, hi = 0, len(a) - 1\n    while lo <= hi:\n"
        "        mid = (lo + hi) // 2\n        if a[mid] < x:\n            lo = mid + 1\n"
        "        else:\n            hi = mid - 1\n    return -1\n"
    )
    assert complexity(binary, "bs") == "Θ(log n)"
    merge = (
        "def ms(a):\n    if len(a) <= 1:\n        return a\n    mid = len(a) // 2\n"
        "    left = ms(a[:mid])\n    right = ms(a[mid:])\n    out = []\n"
        "    for x in left + right:\n        out.append(x)\n    return out\n"
    )
    assert complexity(merge, "ms") == "Θ(n log n)"
    fact = "def f(n):\n    return 1 if n == 0 else n * f(n - 1)\n"
    assert complexity(fact, "f") == "Θ(n)"
    fib = "def fib(n):\n    if n < 2:\n        return n\n    return fib(n - 1) + fib(n - 2)\n"
    assert complexity(fib, "fib") == "O(2^n), an upper bound"


def test_code_unknown_patterns_are_not_guessed() -> None:
    assert complexity("while busy:\n    poll()\n") == "not matched by a template"


def test_code_syntax_errors_and_languages() -> None:
    r = analyse_python("def f(:\n    pass")
    assert not r.parsed and r.error and "line 1" in r.error
    assert detect_language("#include <stdio.h>\nint main() {}") == "c/c++"
    assert detect_language("x = 1", "py") == "python"
