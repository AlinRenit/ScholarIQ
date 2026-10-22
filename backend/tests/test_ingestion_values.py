from __future__ import annotations

from decimal import Decimal

import pytest

from scholariq.domain.enums import ResultStatus
from scholariq.ingestion.interpret import Role, match_header
from scholariq.ingestion.values import MarkKind, find_semester, parse_grade, parse_mark


@pytest.mark.parametrize(
    ("text", "kind", "value", "maximum", "status"),
    [
        ("78", MarkKind.NUMBER, "78", None, ResultStatus.PRESENT),
        ("48.5", MarkKind.NUMBER, "48.5", None, ResultStatus.PRESENT),
        ("38/75", MarkKind.FRACTION, "38", "75", ResultStatus.PRESENT),
        ("38 / 75", MarkKind.FRACTION, "38", "75", ResultStatus.PRESENT),
        ("81%", MarkKind.PERCENT, "81", "100", ResultStatus.PRESENT),
        ("AB", MarkKind.STATUS, None, None, ResultStatus.ABSENT),
        ("Absent", MarkKind.STATUS, None, None, ResultStatus.ABSENT),
        ("W", MarkKind.STATUS, None, None, ResultStatus.WITHHELD),
        ("-", MarkKind.EMPTY, None, None, ResultStatus.MISSING),
        ("", MarkKind.EMPTY, None, None, ResultStatus.MISSING),
    ],
)
def test_parse_mark(
    text: str, kind: MarkKind, value: str | None, maximum: str | None, status: ResultStatus
) -> None:
    p = parse_mark(text)
    assert p.kind is kind
    assert p.value == (Decimal(value) if value else None)
    assert p.maximum == (Decimal(maximum) if maximum else None)
    assert p.status is status


def test_missing_mark_is_never_zero() -> None:
    p = parse_mark("")
    assert p.value is None and p.status is ResultStatus.MISSING


def test_ocr_digit_correction_lowers_confidence_and_explains() -> None:
    p = parse_mark("7O", ocr=True)
    assert p.value == Decimal(70)
    assert p.confidence < 1
    assert p.note and "7O" in p.note


def test_ocr_correction_not_applied_to_digital_text() -> None:
    assert parse_mark("7O").kind is MarkKind.UNREADABLE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Semester III - Regular", 3),
        ("SEM-4", 4),
        ("5th Semester", 5),
        ("Third semester results", 3),
        ("Term 2", 2),
        ("Semesterwise", None),
        ("Semester 14", None),
    ],
)
def test_find_semester(text: str, expected: int | None) -> None:
    assert find_semester(text) == expected


@pytest.mark.parametrize("grade", ["O", "A+", "b-", "AA", "EX", "S"])
def test_grade_tokens_kept_as_printed(grade: str) -> None:
    assert parse_grade(grade) == grade.upper()


@pytest.mark.parametrize("text", ["Excellent", "12", "A++", ""])
def test_non_grades_rejected(text: str) -> None:
    assert parse_grade(text) is None


@pytest.mark.parametrize(
    ("header", "role"),
    [
        ("Subject Name", Role.SUBJECT),
        ("Course Title", Role.SUBJECT),
        ("Marks Obtained", Role.OBTAINED),
        ("Max. Marks", Role.MAX),
        ("Maximum Marks 100", Role.MAX),
        ("Grade Points", Role.GRADE_POINTS),
        ("Credits", Role.CREDITS),
        ("Sub. Code", Role.CODE),
        ("Marks Obtianed", Role.OBTAINED),  # misspelt
    ],
)
def test_header_synonyms(header: str, role: Role) -> None:
    assert match_header(header)[0] is role


def test_unrelated_header_not_matched() -> None:
    assert match_header("Signature of Controller")[0] is None
