"""Asymptotic solutions of common recurrences.

Supported forms (a, b, k, p constants; f is the extra work per call):

* Divide and conquer, T(n) = a T(n/b) + f(n) with f(n) = n^k (log n)^p,
  solved with the master theorem, including the log-factor form of case 2.
  Case 3's regularity condition holds automatically for these f.
* Decrease and conquer, T(n) = a T(n - c) + n^k.

Results are Θ bounds. Exact closed forms, floors and ceilings, and other forms
(for example T(n) = T(n/2) + T(n/3) + n) are declined.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction

from scholariq.answering.solvers.base import Solution, SolverError

CONCEPT = "algo.master-theorem"
_LHS = re.compile(r"t\s*\(\s*n\s*\)\s*=", re.I)


def _num(s: str) -> Fraction:
    return Fraction(s)


def parse_f(text: str) -> tuple[Fraction, int] | None:
    """f(n) -> (k, p) for n^k log^p n. Accepts c, n, n^2, n log n, n^2 logn, log n, sqrt n."""
    t = re.sub(r"\s+", "", text.lower()).replace("·", "").replace("*", "")
    t = re.sub(r"^\d+(\.\d+)?(?=[nl√s])", "", t)  # constant factor
    if re.fullmatch(r"\d+(\.\d+)?|c|o\(1\)|θ\(1\)|theta\(1\)", t):
        return Fraction(0), 0
    t = re.sub(r"^(o|θ|theta)\((.*)\)$", r"\2", t)
    m = re.fullmatch(
        r"(?:(?P<sqrt>√n|sqrt\(?n\)?)|n(?:\^\(?(?P<k>\d+(?:\.\d+)?(?:/\d+)?)\)?)?)?"
        r"(?:(?:\(?log\(?n\)?\)?|lgn|logn|log2n|log_2n)(?:\^(?P<p>\d+))?)?",
        t,
    )
    if not m or not t:
        return None
    has_n = t.startswith("n") or bool(m.group("sqrt"))
    has_log = "log" in t or "lg" in t
    k = (
        Fraction(1, 2)
        if m.group("sqrt")
        else (Fraction(m.group("k")) if m.group("k") else Fraction(1 if has_n else 0))
    )
    p = int(m.group("p")) if m.group("p") else (1 if has_log else 0)
    return k, p


def theta(k: Fraction | float, p: int) -> str:
    if isinstance(k, float):
        npart = f"n^{k:.3f}"
    elif k == 0:
        npart = ""
    elif k == 1:
        npart = "n"
    else:
        npart = f"n^{k}" if k.denominator == 1 else f"n^({k})"
    lpart = "" if p == 0 else "log n" if p == 1 else f"(log n)^{p}"
    body = " ".join(x for x in (npart, lpart) if x) or "1"
    return f"Θ({body})"


class RecurrenceSolver:
    name = "master-theorem"
    description = "Recurrences T(n) = aT(n/b) + f(n) and T(n) = aT(n−c) + f(n)"

    def solve(self, text: str) -> Solution | SolverError | None:
        t = text.replace("−", "-").replace("–", "-")
        m = _LHS.search(t)
        if not m:
            return None
        rhs = t[m.end() :].strip().rstrip("?.").split(",")[0]
        rhs = re.sub(r"\s+for\s+n.*$|\s*,?\s*t\(1\).*$", "", rhs, flags=re.I).strip()
        if len(re.findall(r"t\s*\(", rhs, re.I)) > 1:
            return SolverError(
                self.name,
                "Recurrences with more than one recursive term, such as T(n/2) + T(n/3), are not "
                "supported.",
                CONCEPT,
            )
        dc = re.fullmatch(
            r"(?P<a>\d+)?\s*\*?\s*t\s*\(\s*n\s*/\s*(?P<b>\d+)\s*\)\s*(?:\+\s*(?P<f>.+))?", rhs, re.I
        )
        if dc:
            return self._master(
                Fraction(dc.group("a") or 1), int(dc.group("b")), dc.group("f") or "0"
            )
        dec = re.fullmatch(
            r"(?P<a>\d+)?\s*\*?\s*t\s*\(\s*n\s*-\s*(?P<c>\d+)\s*\)\s*(?:\+\s*(?P<f>.+))?", rhs, re.I
        )
        if dec:
            return self._decrease(
                int(dec.group("a") or 1), int(dec.group("c")), dec.group("f") or "0"
            )
        return SolverError(
            self.name,
            "Only T(n) = aT(n/b) + f(n) and T(n) = aT(n−c) + f(n) are supported, with f(n) a "
            "power of n times a power of log n.",
            CONCEPT,
        )

    def _master(self, a: Fraction, b: int, f_text: str) -> Solution | SolverError:
        if a < 1 or b < 2:
            return SolverError(self.name, "The master theorem needs a ≥ 1 and b ≥ 2.", CONCEPT)
        if f_text.strip() == "0":
            kp: tuple[Fraction, int] | None = (Fraction(0), 0)
        else:
            kp = parse_f(f_text)
        if kp is None:
            return SolverError(
                self.name,
                f"Could not read f(n) = {f_text.strip()}; use forms like n, n^2, n log n or 1.",
                CONCEPT,
            )
        k, p = kp
        crit = math.log(float(a), b)
        crit_exact: Fraction | None = None
        for cand in range(0, 11):
            if b**cand == a:
                crit_exact = Fraction(cand)
        crit_shown = str(crit_exact) if crit_exact is not None else f"{crit:.3f}"
        steps = [
            f"a = {a}, b = {b}, f(n) = {theta(k, p)[2:-1]}.",
            f"Compare f(n) with n^(log_{b} {a}) = n^{crit_shown}.",
        ]
        crit_val = crit_exact if crit_exact is not None else None
        if crit_val is not None and k == crit_val:
            result = theta(k, p + 1)
            steps.append(
                f"Case 2: f(n) matches n^{k} up to (log n)^{p}, so multiply by one more "
                f"log n: {result}."
            )
        elif float(k) < crit - 1e-12:
            result = theta(crit_exact, 0) if crit_exact is not None else theta(crit, 0)
            steps.append(
                f"Case 1: f(n) grows polynomially slower than n^{crit:.3g}, so the recursion "
                f"dominates: {result}."
            )
        else:
            result = theta(k, p)
            steps.append(
                f"Case 3: f(n) grows polynomially faster than n^{crit:.3g}, and the regularity "
                f"condition a·f(n/b) ≤ c·f(n) holds for this f, so f dominates: {result}."
            )
        return Solution(
            self.name,
            "Recurrence (master theorem)",
            f"T(n) = {result}",
            steps=steps,
            limitations=["Asymptotic bound only; assumes T(n) is constant for small n."],
            concept=CONCEPT,
        )

    def _decrease(self, a: int, c: int, f_text: str) -> Solution | SolverError:
        kp = (Fraction(0), 0) if f_text.strip() == "0" else parse_f(f_text)
        if kp is None or kp[1] != 0 or kp[0].denominator != 1:
            return SolverError(
                self.name,
                "For T(n) = aT(n − c) + f(n), f(n) must be a constant or a whole power of n.",
                CONCEPT,
            )
        k = int(kp[0])
        steps = [f"a = {a}, each call reduces n by {c}, f(n) = {theta(kp[0], 0)[2:-1]}."]
        if a == 1:
            result = theta(Fraction(k + 1), 0)
            steps.append(
                f"With one recursive call there are about n/{c} levels, each costing up to "
                f"n^{k}; summing gives {result}."
            )
        else:
            base = f"{a}^(n/{c})" if c > 1 else f"{a}^n"
            result = f"Θ({base})"
            steps.append(
                f"With {a} calls per level the number of calls grows as {base}, which "
                f"dominates any polynomial f(n): {result}."
            )
        return Solution(
            self.name,
            "Recurrence (decrease and conquer)",
            f"T(n) = {result}",
            steps=steps,
            limitations=["Asymptotic bound only; assumes T(n) is constant for small n."],
            concept="algo.recurrence-relation",
        )
