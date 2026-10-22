"""Truth tables for propositional formulas.

Operators (lowest to highest precedence): iff (<->, ↔, <=>), implies (->, →,
=>), or (∨, |, ||, +), xor (⊕), and (∧, &, &&, ., *), not (¬, ~, !, ').
Variables are single letters or words such as ``p``, ``q``, ``rain``. Up to
six variables (64 rows). Implication is right-associative.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from scholariq.answering.solvers.base import Solution, SolverError

MAX_VARS = 6
_KEYWORDS = {
    "and": "&",
    "or": "|",
    "not": "!",
    "xor": "^",
    "implies": "->",
    "iff": "<->",
    "then": "->",
}
_TOKEN = re.compile(r"\s*(<->|<=>|->|=>|&&|\|\||[()!~¬&|∧∨→↔⊕^]|[A-Za-z][A-Za-z0-9_]*)")
_CANON = {
    "<=>": "<->",
    "↔": "<->",
    "=>": "->",
    "→": "->",
    "&&": "&",
    "∧": "&",
    "||": "|",
    "∨": "|",
    "~": "!",
    "¬": "!",
    "⊕": "^",
}


class LogicError(ValueError):
    pass


@dataclass
class Node:
    op: str  # var, !, &, |, ^, ->, <->
    args: tuple[Node, ...] = ()
    name: str = ""

    def eval(self, env: dict[str, bool]) -> bool:
        a = [x.eval(env) for x in self.args]
        match self.op:
            case "var":
                return env[self.name]
            case "!":
                return not a[0]
            case "&":
                return a[0] and a[1]
            case "|":
                return a[0] or a[1]
            case "^":
                return a[0] != a[1]
            case "->":
                return (not a[0]) or a[1]
            case _:
                return a[0] == a[1]

    def show(self) -> str:
        sym = {"&": "∧", "|": "∨", "^": "⊕", "->": "→", "<->": "↔"}
        if self.op == "var":
            return self.name
        if self.op == "!":
            inner = self.args[0].show()
            return f"¬{inner}" if self.args[0].op in ("var", "!") else f"¬({inner})"
        return f"({self.args[0].show()} {sym[self.op]} {self.args[1].show()})"


def tokenize(text: str) -> list[str]:
    out, pos = [], 0
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        m = _TOKEN.match(text, pos)
        if not m:
            raise LogicError(f"unexpected character {text[pos]!r}")
        tok = m.group(1)
        tok = _KEYWORDS.get(tok.lower(), tok) if tok[0].isalpha() else _CANON.get(tok, tok)
        out.append(tok)
        pos = m.end()
    return out


class _Parser:
    LEVELS = (("<->",), ("->",), ("|",), ("^",), ("&",))

    def __init__(self, tokens: list[str]) -> None:
        self.t, self.i = tokens, 0

    def peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise LogicError("the formula ends too early")
        self.i += 1
        return tok

    def parse(self) -> Node:
        n = self.level(0)
        if self.peek() is not None:
            raise LogicError(f"unexpected {self.peek()!r}")
        return n

    def level(self, k: int) -> Node:
        if k == len(self.LEVELS):
            return self.unary()
        left = self.level(k + 1)
        ops = self.LEVELS[k]
        if ops == ("->",) and self.peek() == "->":  # right-associative
            self.take()
            return Node("->", (left, self.level(k)))
        while self.peek() in ops:
            op = self.take()
            left = Node(op, (left, self.level(k + 1)))
        return left

    def unary(self) -> Node:
        if self.peek() == "!":
            self.take()
            return Node("!", (self.unary(),))
        tok = self.take()
        if tok == "(":
            n = self.level(0)
            if self.take() != ")":
                raise LogicError("missing closing bracket")
            return n
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", tok):
            return Node("var", name=tok)
        raise LogicError(f"unexpected {tok!r}")


def variables(n: Node) -> list[str]:
    seen: dict[str, None] = {}

    def walk(x: Node) -> None:
        if x.op == "var":
            seen.setdefault(x.name, None)
        for a in x.args:
            walk(a)

    walk(n)
    return sorted(seen)


_FORMULA = re.compile(
    r"truth\s+table\s*(?:for|of)?\s*:?\s*(?P<f>.+)$|^(?:is\s+)?(?P<g>.+?)\s+(?:a\s+)?(?:tautology|contradiction)\s*\??$",
    re.I,
)


class TruthTableSolver:
    name = "truth-table"
    description = "Truth tables and tautology checks for propositional formulas"

    def solve(self, text: str) -> Solution | SolverError | None:
        m = _FORMULA.search(text.strip())
        if not m:
            return None
        formula = (m.group("f") or m.group("g") or "").strip().rstrip("?.")
        formula = re.sub(
            r"^(is\s+)?(the\s+)?(formula|expression|statement)\s*", "", formula, flags=re.I
        )
        if not formula:
            return SolverError(
                self.name,
                "Give the formula after 'truth table for', e.g. p -> q.",
                "dm.propositional-logic",
            )
        try:
            tree = _Parser(tokenize(formula)).parse()
        except LogicError as e:
            return SolverError(
                self.name, f"Could not read {formula!r}: {e}.", "dm.propositional-logic"
            )
        names = variables(tree)
        if len(names) > MAX_VARS:
            return SolverError(
                self.name, f"At most {MAX_VARS} variables are supported.", "dm.propositional-logic"
            )
        rows, values = [], []
        for combo in itertools.product([True, False], repeat=len(names)):
            env = dict(zip(names, combo, strict=True))
            v = tree.eval(env)
            values.append(v)
            rows.append(["T" if x else "F" for x in combo] + ["T" if v else "F"])
        verdict = (
            "a tautology (true in every row)"
            if all(values)
            else "a contradiction (false in every row)"
            if not any(values)
            else f"contingent (true in {sum(values)} of {len(values)} rows)"
        )
        shown = tree.show()
        return Solution(
            self.name,
            "Truth table",
            f"{shown} is {verdict}.",
            steps=[
                f"Read as {shown} (brackets show how the operators group).",
                f"{len(names)} variable(s) give {len(rows)} rows; each row evaluates the formula.",
            ],
            columns=[*names, shown],
            rows=rows,
            concept="dm.propositional-logic",
        )
