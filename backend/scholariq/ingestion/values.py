"""Parsing of individual cell values: numbers, fractions, grades, semesters.

Each parser returns the value plus an interpretation confidence and an
optional note, so callers can explain any correction they applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from scholariq.domain.enums import ResultStatus


class MarkKind(StrEnum):
    NUMBER = "number"
    FRACTION = "fraction"
    PERCENT = "percent"
    STATUS = "status"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class ParsedMark:
    kind: MarkKind
    value: Decimal | None = None
    maximum: Decimal | None = None
    status: ResultStatus | None = None
    confidence: float = 1.0
    note: str | None = None


_ABSENT = {"ab", "abs", "absent", "a/b"}
_WITHHELD = {"w", "wh", "withheld", "rw", "rl"}
_EMPTY = {"", "-", "--", "—", "na", "n/a", "nil", "*"}

# Characters Tesseract commonly confuses with digits.
_OCR_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1",
                                  "S": "5", "B": "8", "Z": "2"})  # fmt: skip

_NUM = r"\d+(?:[.,]\d+)?"
_FRACTION = re.compile(rf"^({_NUM})\s*/\s*({_NUM})$")
_PERCENT = re.compile(rf"^({_NUM})\s*%$")
_NUMBER = re.compile(rf"^{_NUM}$")


def to_decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def parse_mark(text: str, ocr: bool = False) -> ParsedMark:
    raw = text.strip()
    low = raw.lower().rstrip(".")
    if low in _EMPTY:
        return ParsedMark(MarkKind.EMPTY, status=ResultStatus.MISSING)
    if low in _ABSENT:
        return ParsedMark(MarkKind.STATUS, status=ResultStatus.ABSENT)
    if low in _WITHHELD:
        return ParsedMark(MarkKind.STATUS, status=ResultStatus.WITHHELD)

    compact = raw.replace(" ", "")
    candidates: list[tuple[str, float, str | None]] = [(compact, 1.0, None)]
    if ocr:
        fixed = compact.translate(_OCR_DIGIT_FIXES)
        if fixed != compact:
            candidates.append((fixed, 0.75, f"read '{raw}' as '{fixed}'"))

    for cand, conf, note in candidates:
        if m := _FRACTION.match(cand):
            num, den = to_decimal(m.group(1)), to_decimal(m.group(2))
            return ParsedMark(MarkKind.FRACTION, num, den, ResultStatus.PRESENT, conf, note)
        if m := _PERCENT.match(cand):
            return ParsedMark(
                MarkKind.PERCENT, to_decimal(m.group(1)), Decimal(100), ResultStatus.PRESENT,
                conf, note,
            )  # fmt: skip
        if _NUMBER.match(cand):
            return ParsedMark(
                MarkKind.NUMBER, to_decimal(cand), None, ResultStatus.PRESENT, conf, note
            )
    return ParsedMark(MarkKind.UNREADABLE, confidence=0.0, note=f"could not read '{raw}'")


_GRADE = re.compile(r"^(?:[A-FOPSU][+-]?|[A-F]{2}|EX|AP|AB|NC|RA)$", re.IGNORECASE)


def parse_grade(text: str) -> str | None:
    """Return a grade token as printed (upper-cased), without interpreting it."""
    raw = text.strip().upper().replace(" ", "")
    return raw if raw and _GRADE.match(raw) else None


_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
          "IX": 9, "X": 10, "XI": 11, "XII": 12}  # fmt: skip
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
                  "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}  # fmt: skip

_SEM_PATTERNS = [
    re.compile(r"\b(?:semester|sem|term)\s*[-:.#]?\s*([0-9]{1,2}|[IVX]{1,4})\b", re.IGNORECASE),
    re.compile(r"\b([0-9]{1,2})(?:st|nd|rd|th)\s+(?:semester|sem)\b", re.IGNORECASE),
    re.compile(r"\b([IVX]{1,4})\s+(?:semester|sem)\b"),
    re.compile(r"\b(" + "|".join(_ORDINAL_WORDS) + r")\s+(?:semester|sem)\b", re.IGNORECASE),
]


def parse_semester_value(token: str) -> int | None:
    t = token.strip()
    if t.isdigit():
        n = int(t)
    elif t.upper() in _ROMAN:
        n = _ROMAN[t.upper()]
    elif t.lower() in _ORDINAL_WORDS:
        n = _ORDINAL_WORDS[t.lower()]
    else:
        return None
    return n if 1 <= n <= 12 else None


def find_semester(text: str) -> int | None:
    for pattern in _SEM_PATTERNS:
        if m := pattern.search(text):
            if (n := parse_semester_value(m.group(1))) is not None:
                return n
    return None


def parse_credits(text: str) -> Decimal | None:
    value = to_decimal(text.strip()) if _NUMBER.match(text.strip()) else None
    return value if value is not None and 0 <= value <= 30 else None
