"""Handler E: static analysis of code questions. Code is never executed.

Python is parsed with the standard ``ast`` module. Other languages are
recognised by name only and are not analysed; the answer says so.

Running time is estimated with fixed templates, applied bottom up:

* ``for x in range(.. n ..)``, ``for x in items``: n iterations; a range with
  only constant bounds: constant.
* ``while`` whose body multiplies or divides the loop variable (``i *= 2``,
  ``i //= 2``, ``lo = mid + 1``): log n iterations; one that adds or
  subtracts a constant: n iterations.
* A loop costs its iterations times its body; statements in sequence cost the
  largest of them.
* ``sorted(..)`` and ``.sort()``: n log n.
* A function calling itself a times on n - c: a = 1 gives n·f(n) work in
  total, a >= 2 gives a^n. On n // 2 (or half a list): the master theorem with
  b = 2.

Anything else is reported as not matched rather than guessed. The estimate is
a template match, not a proof.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from fractions import Fraction

from scholariq.answering.solvers.recurrence import RecurrenceSolver, theta


@dataclass(frozen=True)
class Cost:
    k: int = 0  # power of n
    p: int = 0  # power of log n
    exp: str | None = None  # e.g. "2^n"
    unknown: bool = False

    def __mul__(self, other: Cost) -> Cost:
        if self.unknown or other.unknown:
            return Cost(unknown=True)
        return Cost(self.k + other.k, self.p + other.p, self.exp or other.exp)

    def show(self) -> str:
        if self.unknown:
            return "not matched by a template"
        if self.exp:
            return self.exp
        return theta(Fraction(self.k), self.p)


def _max(costs: list[Cost]) -> Cost:
    if not costs:
        return Cost()
    if any(c.unknown for c in costs):
        return Cost(unknown=True)
    exps = [c for c in costs if c.exp]
    if exps:
        return exps[0]
    return max(costs, key=lambda c: (c.k, c.p))


@dataclass
class FunctionReport:
    name: str
    loops: int
    max_nesting: int
    recursive_calls: int
    cost: Cost
    rules: list[str] = field(default_factory=list)


@dataclass
class CodeReport:
    language: str
    parsed: bool
    error: str | None = None
    functions: list[FunctionReport] = field(default_factory=list)
    top_level: FunctionReport | None = None


def detect_language(code: str, hint: str = "") -> str:
    hint = hint.lower()
    if hint in ("py", "python", "python3"):
        return "python"
    if hint:
        return hint
    if re.search(r"#include|\bint\s+main\s*\(|std::|printf\s*\(", code):
        return "c/c++"
    if re.search(r"\bpublic\s+(static\s+)?(class|void)\b|System\.out", code):
        return "java"
    if re.search(r"\bfunction\b|=>|console\.log|\blet\b|\bconst\b", code):
        return "javascript"
    return "python"


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


class _Analyser:
    def __init__(self, fn_name: str | None) -> None:
        self.fn = fn_name
        self.rules: list[str] = []
        self.loops = 0
        self.max_nesting = 0
        self.self_calls: list[ast.Call] = []

    def block(self, stmts: list[ast.stmt], depth: int) -> Cost:
        return _max([self.stmt(s, depth) for s in stmts])

    def stmt(self, s: ast.stmt, depth: int) -> Cost:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return Cost()
        if isinstance(s, ast.For):
            self.loops += 1
            self.max_nesting = max(self.max_nesting, depth + 1)
            it = self.for_iterations(s)
            return it * self.block(s.body, depth + 1)
        if isinstance(s, ast.While):
            self.loops += 1
            self.max_nesting = max(self.max_nesting, depth + 1)
            it = self.while_iterations(s)
            return it * self.block(s.body, depth + 1)
        if isinstance(s, ast.If):
            return _max(
                [self.expr_cost(s.test), self.block(s.body, depth), self.block(s.orelse, depth)]
            )
        if isinstance(s, (ast.With, ast.Try)):
            parts = (
                list(getattr(s, "body", []))
                + list(getattr(s, "orelse", []))
                + list(getattr(s, "finalbody", []))
            )
            return self.block(parts, depth)
        return self.expr_cost(s)

    def expr_cost(self, node: ast.AST) -> Cost:
        cost = Cost()
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                f = n.func
                name = (
                    f.id
                    if isinstance(f, ast.Name)
                    else f.attr
                    if isinstance(f, ast.Attribute)
                    else ""
                )
                if name == self.fn:
                    self.self_calls.append(n)
                elif name in ("sorted", "sort"):
                    self.rules.append(f"line {n.lineno}: {name}() costs n log n")
                    cost = _max([cost, Cost(1, 1)])
                elif name in ("sum", "max", "min", "len") and name != "len" and n.args:
                    cost = _max([cost, Cost(1, 0)])
            if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                cost = _max([cost, Cost(len(n.generators), 0)])
        return cost

    def for_iterations(self, s: ast.For) -> Cost:
        it = s.iter
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range":
            if all(isinstance(a, ast.Constant) for a in it.args):
                self.rules.append(
                    f"line {s.lineno}: range with constant bounds runs a fixed number of times"
                )
                return Cost()
            if len(it.args) == 3 and isinstance(it.args[2], ast.BinOp):
                return Cost(unknown=True)
            self.rules.append(f"line {s.lineno}: for over range(..n..) runs n times")
            return Cost(1, 0)
        self.rules.append(f"line {s.lineno}: for over a collection runs once per element (n)")
        return Cost(1, 0)

    def while_iterations(self, s: ast.While) -> Cost:
        loop_vars = _names(s.test)
        for n in ast.walk(ast.Module(body=s.body, type_ignores=[])):
            if (
                isinstance(n, ast.AugAssign)
                and isinstance(n.target, ast.Name)
                and n.target.id in loop_vars
            ):
                if isinstance(n.op, (ast.Mult, ast.FloorDiv, ast.Div, ast.RShift, ast.LShift)):
                    self.rules.append(
                        f"line {s.lineno}: loop variable is multiplied or divided each time: log n"
                    )
                    return Cost(0, 1)
                if isinstance(n.op, (ast.Add, ast.Sub)) and isinstance(n.value, ast.Constant):
                    self.rules.append(
                        f"line {s.lineno}: loop variable changes by a constant: n iterations"
                    )
                    return Cost(1, 0)
            if (
                isinstance(n, ast.Assign)
                and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
            ):
                t = n.targets[0].id
                if t in loop_vars:
                    src = ast.unparse(n.value)
                    if re.search(r"//\s*2|/\s*2|>>\s*1|\*\s*2|\bmid\b", src):
                        self.rules.append(f"line {s.lineno}: search range halves each time: log n")
                        return Cost(0, 1)
        return Cost(unknown=True)


def _recursion(fn: ast.FunctionDef, an: _Analyser, body_cost: Cost) -> tuple[Cost, list[str]]:
    calls = an.self_calls
    a = len(calls)
    shapes = set()
    decrements: set[int] = set()
    for c in calls:
        txt = " ".join(ast.unparse(x) for x in c.args)
        if re.search(r"//\s*2|/\s*2|\bmid\b|\[:\s*\w+\s*\]|\[\s*\w+\s*:\s*\]|>>\s*1", txt):
            shapes.add("half")
        elif m := re.search(r"-\s*(\d+)", txt):
            shapes.add("minus")
            decrements.add(int(m.group(1)))
        elif re.search(r"\[1:\]", txt):
            shapes.add("minus")
            decrements.add(1)
        else:
            shapes.add("other")
    if len(shapes) != 1 or "other" in shapes or body_cost.unknown or body_cost.exp:
        return Cost(unknown=True), [
            f"{fn.name} calls itself {a} time(s) in a shape no template covers"
        ]
    f = theta(Fraction(body_cost.k), body_cost.p)[2:-1]
    if shapes == {"minus"}:
        if a == 1:
            return Cost(body_cost.k + 1, body_cost.p), [
                f"{fn.name} calls itself once on a smaller input (n - 1): T(n) = T(n-1) + {f}"
            ]
        if len(decrements) == 1:
            step = decrements.pop()
            power = "n" if step == 1 else f"n/{step}"
            return Cost(exp=f"Θ({a}^{power})"), [
                f"{fn.name} calls itself {a} times on n - {step}: T(n) = {a}T(n-{step}) + {f}"
            ]
        return Cost(exp=f"O({a}^n), an upper bound"), [
            f"{fn.name} calls itself {a} times on inputs reduced by different amounts "
            f"({', '.join(f'n - {d}' for d in sorted(decrements))}); {a}^n bounds this from above, "
            "and the tight bound depends on the exact decrements "
            "(for Fibonacci it is about 1.618^n)"
        ]
    rec = f"T(n) = {a}T(n/2) + {f if f != '1' else '1'}"
    sol = RecurrenceSolver().solve(rec)
    result = getattr(sol, "result", "")
    m = re.search(r"Θ\((.*)\)", result)
    body = m.group(1) if m else ""
    km = re.match(r"n(?:\^(\d+))?", body)
    k = int(km.group(1) or 1) if km and body.startswith("n") else 0
    p = 2 if "(log n)^2" in body else 1 if "log n" in body else 0
    if "." in body:
        return Cost(unknown=True), [
            f"{fn.name}: {rec} gives {result}, which has no simple template form"
        ]
    return Cost(k, p), [
        f"{fn.name} calls itself {a} time(s) on half the input: {rec}, so {result} (master theorem)"
    ]


def analyse_python(code: str) -> CodeReport:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return CodeReport("python", False, f"Syntax error on line {e.lineno}: {e.msg}.")
    report = CodeReport("python", True)
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        an = _Analyser(fn.name)
        body = an.block(fn.body, 0)
        rules = list(an.rules)
        cost = body
        if an.self_calls:
            cost, extra = _recursion(fn, an, body)
            rules += extra
        report.functions.append(
            FunctionReport(fn.name, an.loops, an.max_nesting, len(an.self_calls), cost, rules)
        )
    top = [
        s
        for s in tree.body
        if not isinstance(s, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom))
    ]
    if top:
        an = _Analyser(None)
        cost = an.block(top, 0)
        report.top_level = FunctionReport(
            "(top-level code)", an.loops, an.max_nesting, 0, cost, an.rules
        )
    return report
