"""Linear and quadratic equations in one variable, solved exactly.

Both sides are parsed into polynomials with fraction coefficients (implicit
multiplication such as ``2x`` and ``3(x + 1)`` is allowed). Equations of
degree 0, 1 or 2 are solved; anything higher is declined rather than guessed.
Irrational roots are shown in surd form with a decimal approximation.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

from scholariq.answering.solvers.arithmetic import ParseError, show
from scholariq.answering.solvers.base import Solution, SolverError

Poly = dict[int, Fraction]  # power -> coefficient
MAX_DEGREE = 2


def _clean(p: Poly) -> Poly:
    return {k: v for k, v in p.items() if v != 0}


def _add(a: Poly, b: Poly, sign: int = 1) -> Poly:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, Fraction(0)) + sign * v
    return _clean(out)


def _mul(a: Poly, b: Poly) -> Poly:
    out: Poly = {}
    for i, x in a.items():
        for j, y in b.items():
            if i + j > 4:
                raise ParseError("the equation's degree is too high")
            out[i + j] = out.get(i + j, Fraction(0)) + x * y
    return _clean(out)


class _PolyParser:
    def __init__(self, text: str, var: str) -> None:
        self.tokens = re.findall(rf"\d+(?:\.\d+)?|{var}|\*\*|[-+*/^()]", text)
        joined = "".join(self.tokens)
        if joined != re.sub(r"\s+", "", text).replace("×", "*"):
            raise ParseError("unsupported symbols in the equation")
        self.i, self.var = 0, var

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        t = self.peek()
        if t is None:
            raise ParseError("the equation ends too early")
        self.i += 1
        return t

    def parse(self) -> Poly:
        p = self.expr()
        if self.peek() is not None:
            raise ParseError(f"unexpected {self.peek()!r}")
        return p

    def expr(self) -> Poly:
        p = self.term()
        while self.peek() in ("+", "-"):
            sign = 1 if self.take() == "+" else -1
            p = _add(p, self.term(), sign)
        return p

    def term(self) -> Poly:
        p = self.factor()
        while True:
            nxt = self.peek()
            if nxt in ("*", "/"):
                op = self.take()
                rhs = self.factor()
                if op == "/":
                    if set(rhs) != {0}:
                        raise ParseError(
                            "dividing by an expression with the variable is not supported"
                        )
                    p = {k: v / rhs[0] for k, v in p.items()}
                else:
                    p = _mul(p, rhs)
            elif nxt is not None and (nxt == "(" or nxt == self.var or nxt[0].isdigit()):
                p = _mul(p, self.factor())  # implicit multiplication: 2x, 3(x+1)
            else:
                return p

    def factor(self) -> Poly:
        if self.peek() == "-":
            self.take()
            return {k: -v for k, v in self.factor().items()}
        base = self.atom()
        if self.peek() in ("^", "**"):
            self.take()
            exp = self.take()
            if not exp.isdigit() or int(exp) > 4:
                raise ParseError("only small whole-number powers are supported")
            out: Poly = {0: Fraction(1)}
            for _ in range(int(exp)):
                out = _mul(out, base)
            return out
        return base

    def atom(self) -> Poly:
        t = self.take()
        if t == "(":
            p = self.expr()
            if self.take() != ")":
                raise ParseError("missing closing bracket")
            return p
        if t == self.var:
            return {1: Fraction(1)}
        if t[0].isdigit():
            return _clean({0: Fraction(t)})
        raise ParseError(f"unexpected {t!r}")


def _fmt_poly(p: Poly, var: str) -> str:
    if not p:
        return "0"
    parts = []
    for k in sorted(p, reverse=True):
        c = p[k]
        mag = abs(c)
        coef = "" if (mag == 1 and k > 0) else (str(mag) if mag.denominator == 1 else f"({mag})")
        term = coef + ("" if k == 0 else var if k == 1 else f"{var}^{k}")
        parts.append(("- " if c < 0 else "+ ") + term)
    s = " ".join(parts)
    return s[2:] if s.startswith("+ ") else "-" + s[2:]


def _sqrt_frac(x: Fraction) -> Fraction | None:
    n, d = x.numerator, x.denominator
    rn, rd = math.isqrt(n), math.isqrt(d)
    return Fraction(rn, rd) if rn * rn == n and rd * rd == d else None


class EquationSolver:
    name = "equation"
    description = "Linear and quadratic equations in one variable"

    def solve(self, text: str) -> Solution | SolverError | None:
        body = re.sub(
            r"^\s*(please\s+)?(solve|find)\s*(for\s+[a-z]\s*)?:?\s*", "", text.strip(), flags=re.I
        )
        body = re.sub(r"\s*(for\s+[a-z])?\s*[?.]?\s*$", "", body, flags=re.I)
        if body.count("=") != 1:
            return None
        letters = set(re.findall(r"(?<![a-z])[a-z](?![a-z])", body.lower()))
        if len(letters) != 1 or re.search(r"[a-z]{2,}", body.lower()):
            return None
        var = letters.pop()
        left, right = (s.strip() for s in body.lower().split("="))
        if not left or not right:
            return None
        try:
            poly = _add(_PolyParser(left, var).parse(), _PolyParser(right, var).parse(), -1)
        except ParseError as e:
            return SolverError(self.name, f"Could not read the equation: {e}.")
        degree = max(poly, default=0)
        steps = [f"Move everything to one side: {_fmt_poly(poly, var)} = 0."]
        if degree > MAX_DEGREE:
            return SolverError(
                self.name,
                f"This is a degree-{degree} equation; only linear and quadratic are supported.",
            )
        if degree == 0:
            holds = not poly
            return Solution(
                self.name,
                "Equation",
                f"True for every {var}" if holds else "No solution",
                steps=steps
                + [
                    "The variable cancels out, leaving "
                    + ("0 = 0." if holds else f"{show(poly[0])} = 0, which is false.")
                ],
            )
        a, b, c = poly.get(2, Fraction(0)), poly.get(1, Fraction(0)), poly.get(0, Fraction(0))
        if degree == 1:
            x = -c / b
            steps.append(f"Subtract {show(c)} and divide by {show(b)}: {var} = {show(x)}.")
            return Solution(self.name, "Linear equation", f"{var} = {show(x)}", steps=steps)
        disc = b * b - 4 * a * c
        steps.append(f"Quadratic with a = {show(a)}, b = {show(b)}, c = {show(c)}.")
        steps.append(f"Discriminant b² − 4ac = {show(disc)}.")
        if disc < 0:
            steps.append("The discriminant is negative, so there are no real roots.")
            return Solution(self.name, "Quadratic equation", "No real solutions", steps=steps)
        root = _sqrt_frac(disc)
        if root is not None:
            r1, r2 = (-b + root) / (2 * a), (-b - root) / (2 * a)
            roots = sorted({r1, r2})
            steps.append(f"{var} = (−b ± √{show(disc)}) / 2a.")
            result = f"{var} = " + " or ".join(show(r) for r in roots)
        else:
            # √(n/d) = √(n·d)/d; pull square factors out of the radicand: √8 = 2√2.
            radicand = disc.numerator * disc.denominator
            outside = Fraction(1, disc.denominator)
            f = 2
            while f * f <= radicand:
                while radicand % (f * f) == 0:
                    radicand //= f * f
                    outside *= f
                f += 1
            centre, spread = -b / (2 * a), abs(outside / (2 * a))
            approx = sorted(
                float(centre) + sgn * float(spread) * math.sqrt(radicand) for sgn in (1, -1)
            )
            steps.append(f"√{show(disc)} is irrational, so the roots are left in surd form.")
            coef = (
                "" if spread == 1 else (str(spread) if spread.denominator == 1 else f"({spread})")
            )
            lead = "" if centre == 0 else f"{show(centre)} "
            result = f"{var} = {lead}± {coef}√{radicand}, about " + " or ".join(
                f"{r:.6g}" for r in approx
            )
        return Solution(self.name, "Quadratic equation", result, steps=steps)
