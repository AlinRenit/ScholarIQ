"""Exact arithmetic and percentages.

Expressions are parsed by a small recursive-descent parser (no ``eval``) and
computed with exact fractions. Supported: + - * / ^ (or **), parentheses,
unary minus, decimals. Powers are limited to exponents up to 1000 and results
to 2000 digits.
"""

from __future__ import annotations

import re
from fractions import Fraction

from scholariq.answering.solvers.base import Solution, SolverError

MAX_EXP = 1000
MAX_DIGITS = 2000

_TOKEN = re.compile(r"\s*(\d+(?:\.\d+)?|\*\*|[-+*/^()])")


class ParseError(ValueError):
    pass


def tokenize(expr: str) -> list[str]:
    pos, out = 0, []
    expr = expr.replace("×", "*").replace("÷", "/").replace("−", "-")
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN.match(expr, pos)
        if not m:
            raise ParseError(f"unexpected character {expr[pos]!r}")
        out.append("^" if m.group(1) == "**" else m.group(1))
        pos = m.end()
    return out


class _Parser:
    """expr := term (('+'|'-') term)*; term := unary (('*'|'/') unary)*;
    unary := '-' unary | power; power := atom ('^' unary)?; atom := number | '(' expr ')'"""

    def __init__(self, tokens: list[str]) -> None:
        self.t, self.i = tokens, 0

    def peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ParseError("expression ends too early")
        self.i += 1
        return tok

    def parse(self) -> Fraction:
        v = self.expr()
        if self.peek() is not None:
            raise ParseError(f"unexpected {self.peek()!r}")
        return v

    def expr(self) -> Fraction:
        v = self.term()
        while self.peek() in ("+", "-"):
            v = v + self.term() if self.take() == "+" else v - self.term()
        return v

    def term(self) -> Fraction:
        v = self.unary()
        while self.peek() in ("*", "/"):
            op, rhs = self.take(), self.unary()
            if op == "/" and rhs == 0:
                raise ParseError("division by zero")
            v = v * rhs if op == "*" else v / rhs
        return v

    def unary(self) -> Fraction:
        if self.peek() == "-":
            self.take()
            return -self.unary()
        if self.peek() == "+":
            self.take()
            return self.unary()
        return self.power()

    def power(self) -> Fraction:
        base = self.atom()
        if self.peek() == "^":
            self.take()
            exp = self.unary()
            if exp.denominator != 1:
                raise ParseError("only whole-number powers are supported")
            if abs(exp) > MAX_EXP:
                raise ParseError(f"powers above {MAX_EXP} are not supported")
            if base == 0 and exp < 0:
                raise ParseError("division by zero")
            result = base ** int(exp)
            if len(str(abs(result.numerator))) > MAX_DIGITS:
                raise ParseError("the result is too large to show")
            return result
        return base

    def atom(self) -> Fraction:
        tok = self.take()
        if tok == "(":
            v = self.expr()
            if self.take() != ")":
                raise ParseError("missing closing bracket")
            return v
        if re.fullmatch(r"\d+(\.\d+)?", tok):
            return Fraction(tok)
        raise ParseError(f"unexpected {tok!r}")


def evaluate(expr: str) -> Fraction:
    return _Parser(tokenize(expr)).parse()


def show(v: Fraction) -> str:
    if v.denominator == 1:
        return str(v.numerator)
    dec = f"{float(v):.10g}"
    return f"{v.numerator}/{v.denominator} (about {dec})"


_LEAD = re.compile(
    r"^\s*(please\s+)?(what\s+is|what's|whats|calculate|compute|evaluate|work\s+out|find)\s+", re.I
)


def _strip(text: str) -> str:
    t = _LEAD.sub("", text.strip())
    return re.sub(r"[\s=?]+$", "", t)


class ArithmeticSolver:
    name = "arithmetic"
    description = "Arithmetic with + - * / ^ and brackets, computed exactly"

    def solve(self, text: str) -> Solution | SolverError | None:
        expr = _strip(text)
        # Only digits, operators, brackets and spaces; at least one operator between numbers.
        if not re.fullmatch(r"[\d\s.+\-*/^()×÷−]+", expr) or not re.search(r"\d\s*[-+*/^×÷]", expr):
            return None
        try:
            v = evaluate(expr)
        except ParseError as e:
            return SolverError(self.name, f"Could not evaluate {expr!r}: {e}.")
        return Solution(
            self.name,
            "Arithmetic",
            f"{expr} = {show(v)}",
            steps=[
                "Brackets first, then powers, then multiplication and division left to right, "
                "then addition and subtraction left to right.",
                "Computed with exact fractions, so there is no rounding until the final "
                "decimal shown.",
            ],
        )


_NUM = r"(-?\d+(?:\.\d+)?)"


class PercentageSolver:
    name = "percentage"
    description = "Percentages: x% of y, x is what percent of y, percentage change"

    def solve(self, text: str) -> Solution | SolverError | None:
        t = re.sub(r"\bper\s*cent\b", "%", text.lower()).replace(" %", "%")
        if m := re.search(rf"{_NUM}%\s*of\s*{_NUM}", t):
            p, y = Fraction(m.group(1)), Fraction(m.group(2))
            v = p / 100 * y
            return Solution(
                self.name,
                "Percentage of a number",
                f"{m.group(1)}% of {m.group(2)} = {show(v)}",
                steps=[
                    f"{m.group(1)}% means {m.group(1)}/100.",
                    f"{m.group(1)}/100 × {m.group(2)} = {show(v)}.",
                ],
            )
        if m := re.search(rf"{_NUM}\s*(?:is|as)\s*what\s*%\s*of\s*{_NUM}", t) or re.search(
            rf"what\s*%\s*of\s*{_NUM}\s*is\s*{_NUM}", t
        ):
            if "what" in t.split(m.group(1))[0]:
                x, y = Fraction(m.group(2)), Fraction(m.group(1))
                xs, ys = m.group(2), m.group(1)
            else:
                x, y = Fraction(m.group(1)), Fraction(m.group(2))
                xs, ys = m.group(1), m.group(2)
            if y == 0:
                return SolverError(self.name, "A percentage of zero is undefined.")
            v = x / y * 100
            return Solution(
                self.name,
                "Percentage",
                f"{xs} is {show(v)}% of {ys}",
                steps=[f"{xs} ÷ {ys} = {show(x / y)}.", f"Multiply by 100: {show(v)}%."],
            )
        if m := re.search(
            rf"(?:percentage|%)\s*(?:change|increase|decrease)\s*from\s*{_NUM}\s*to\s*{_NUM}", t
        ):
            a, b = Fraction(m.group(1)), Fraction(m.group(2))
            if a == 0:
                return SolverError(self.name, "Percentage change from zero is undefined.")
            v = (b - a) / abs(a) * 100
            return Solution(
                self.name,
                "Percentage change",
                f"From {m.group(1)} to {m.group(2)} is a change of {show(v)}%",
                steps=[
                    f"Change = {m.group(2)} − {m.group(1)} = {show(b - a)}.",
                    f"Divide by the starting value and multiply by 100: {show(v)}%.",
                ],
            )
        if m := re.search(rf"{_NUM}\s*(?:out of|/)\s*{_NUM}\s*(?:as a |in )?(?:%|percentage)", t):
            x, y = Fraction(m.group(1)), Fraction(m.group(2))
            if y == 0:
                return SolverError(self.name, "Cannot divide by zero marks.")
            v = x / y * 100
            return Solution(
                self.name,
                "Marks as a percentage",
                f"{m.group(1)} out of {m.group(2)} = {show(v)}%",
                steps=[f"{m.group(1)} ÷ {m.group(2)} × 100 = {show(v)}%."],
            )
        return None
