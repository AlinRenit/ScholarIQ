"""End-to-end parsing of fixture marksheets: extraction + interpretation.

Expected values were checked by hand against the generator in
tests/fixtures/generate.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from scholariq.ingestion.extract import OcrUnavailable, extract
from scholariq.ingestion.interpret import Interpretation, interpret
from scholariq.ingestion.types import SourceKind
from scholariq.ingestion.validation import validate_upload

FIXTURES = Path(__file__).parent / "fixtures" / "marksheets"
needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


def run(name: str) -> tuple[SourceKind, Interpretation]:
    upload = validate_upload(name, (FIXTURES / name).read_bytes(), 10 * 1024 * 1024)
    content = extract(upload)
    return content.source, interpret(content)


def rows(interp: Interpretation, *keys: str) -> list[tuple[Any, ...]]:
    return [tuple(c.fields.get(k) for k in keys) for c in interp.candidates]


def by_subject(interp: Interpretation, name: str) -> list[dict[str, Any]]:
    return [c.fields for c in interp.candidates if c.fields["subject_name"] == name]


def test_digital_pdf_with_ruled_table() -> None:
    source, it = run("digital_semester3.pdf")
    assert source is SourceKind.PDF_TEXT
    assert it.parser == "header_table"
    assert rows(it, "subject_code", "subject_name", "marks_obtained", "max_marks", "grade") == [
        ("CS301", "Data Structures", "78", "100", "A"),
        ("CS302", "Operating Systems", "52", "100", "C"),
        ("CS303", "Database Management Systems", "45", "100", "D"),
        ("CS304", "Computer Networks", None, "100", None),
        ("CS305L", "Data Structures Lab", "44", "50", "A+"),
        ("MA301", "Discrete Mathematics", "91", "100", "O"),
    ]
    # Context lines above the table supply semester and exam details.
    assert {c.fields["semester"] for c in it.candidates} == {3}
    assert {c.fields["exam_type"] for c in it.candidates} == {"regular"}
    assert it.context.exam_name == "November 2025"


def test_absent_is_status_not_zero() -> None:
    _, it = run("digital_semester3.pdf")
    cn = by_subject(it, "Computer Networks")[0]
    assert cn["status"] == "absent"
    assert "marks_obtained" not in cn


def test_lab_component_detected_from_name() -> None:
    _, it = run("digital_semester3.pdf")
    assert by_subject(it, "Data Structures Lab")[0]["component"] == "lab"
    assert by_subject(it, "Data Structures")[0]["component"] == "combined"


def test_grades_are_not_interpreted_without_a_scale() -> None:
    _, it = run("digital_semester3.pdf")
    assert it.grades_seen == ["A", "A+", "C", "D", "O"]
    assert any("not converted" in w for w in it.warnings)
    assert all("grade_points" not in c.fields for c in it.candidates)


def test_unruled_pdf_multiple_semesters_and_supplementary() -> None:
    _, it = run("unruled_grades.pdf")
    assert rows(it, "subject_code", "semester", "grade", "grade_points", "credits") == [
        ("MA101", 1, "B+", "7", "4"),
        ("CS101", 1, "A", "8", "3"),
        ("PH101", 1, "F", "0", "3"),
        ("PH101", 2, "C", "5", "3"),
        ("CS102", 2, "A+", "9", "4"),
    ]
    physics = by_subject(it, "Engineering Physics")
    assert [p["exam_type"] for p in physics] == ["unknown", "supplementary"]
    # Different semester and exam: not flagged as a duplicate.
    assert not any("more than once" in w for c in it.candidates for w in c.warnings)


def test_xlsx_theory_and_practical_columns_split_into_components() -> None:
    source, it = run("theory_practical.xlsx")
    assert source is SourceKind.SPREADSHEET
    assert rows(it, "subject_name", "component", "marks_obtained", "semester") == [
        ("Computer Networks", "theory", "61", 5),
        ("Computer Networks", "lab", "22", 5),
        ("Software Engineering", "theory", "70", 5),
        ("Compiler Design", "theory", "48.5", 5),
        ("Compiler Design", "lab", "18", 5),
    ]
    # No maximum marks column: never assumed.
    assert all(c.fields.get("max_marks") is None for c in it.candidates)
    assert all(any("Maximum marks not found" in w for w in c.warnings) for c in it.candidates)


def test_csv_percentages_missing_and_repeated_subjects() -> None:
    _, it = run("percentages.csv")
    assert rows(it, "subject_name", "marks_obtained", "max_marks", "status") == [
        ("Data Structures", "81", "100", "present"),
        ("Operating Systems", "67", "100", "present"),
        ("Database Systems", None, None, "missing"),
        ("Data Structures", "74", "100", "present"),
    ]
    repeated = by_subject(it, "Data Structures")
    assert len(repeated) == 2
    flagged = [c for c in it.candidates if any("more than once" in w for w in c.warnings)]
    assert len(flagged) == 2


def test_semicolon_csv_unknown_grade_and_missing_max() -> None:
    _, it = run("semicolon_missing_max.csv")
    algos = it.candidates[0]
    assert algos.fields["grade"] == "XQ"
    assert algos.fields.get("max_marks") is None
    assert any("No semester found" in w for w in it.warnings)


def test_plain_text_uses_fallback_with_low_confidence() -> None:
    _, it = run("plain_report.txt")
    assert it.parser == "line_fallback"
    assert rows(it, "subject_name", "marks_obtained", "max_marks", "grade", "status") == [
        ("Design and Analysis of Algorithms", "38", "75", "C", "present"),
        ("Artificial Neural Networks Elective", "64", "100", "B", "present"),
        ("Machine Drawing Practical", None, None, None, "absent"),
    ]
    assert it.context.semester == 6
    assert it.context.exam_type.value == "backlog"
    # The 'Total' line is a summary, not a subject.
    assert not by_subject(it, "Total")
    for c in it.candidates:
        read = [v for k, v in c.confidence.items() if k in ("subject_name", "marks_obtained")]
        assert read and max(read) < 0.8


@needs_tesseract
@pytest.mark.parametrize("name", ["scanned_semester4.png", "scanned_semester4.pdf"])
def test_scanned_documents_via_ocr(name: str) -> None:
    source, it = run(name)
    assert source is SourceKind.OCR
    assert rows(it, "subject_name", "marks_obtained", "max_marks") == [
        ("Data Structures", "78", "100"),
        ("Operating Systems", "52", "100"),
        ("Computer Networks", "64", "100"),
        ("Mathematics", "88", "100"),
    ]
    assert {c.fields["semester"] for c in it.candidates} == {4}


def test_ocr_unavailable_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    upload = validate_upload(
        "s.png", (FIXTURES / "scanned_semester4.png").read_bytes(), 10 * 1024 * 1024
    )
    with pytest.raises(OcrUnavailable, match="Tesseract is not installed"):
        extract(upload)


def test_incorrect_ocr_value_is_flagged() -> None:
    from scholariq.ingestion.interpret import HeaderTableParser
    from scholariq.ingestion.types import Block, Cell, ExtractedContent, Row

    content = ExtractedContent(
        SourceKind.OCR,
        [
            Block(
                [
                    Row([Cell("Subject"), Cell("Max"), Cell("Obtained")]),
                    Row([Cell("Data Structures", 0.95), Cell("100", 0.9), Cell("7O", 0.6)]),
                ]
            )
        ],
    )
    cand = HeaderTableParser().parse(content).candidates[0]
    assert cand.fields["marks_obtained"] == "70"
    assert cand.confidence["marks_obtained"] < 0.8
    assert any("read '7O' as '70'" in w for w in cand.warnings)
    assert any("Please check" in w and "marks obtained" in w for w in cand.warnings)


def test_obtained_above_max_is_warned() -> None:
    from scholariq.ingestion.interpret import HeaderTableParser
    from scholariq.ingestion.types import Block, Cell, ExtractedContent, Row

    content = ExtractedContent(
        SourceKind.CSV,
        [
            Block(
                [
                    Row([Cell("Subject"), Cell("Max Marks"), Cell("Marks")]),
                    Row([Cell("Networks"), Cell("50"), Cell("78")]),
                ]
            )
        ],
    )
    cand = HeaderTableParser().parse(content).candidates[0]
    assert any("higher than maximum" in w for w in cand.warnings)


def test_empty_document_reports_no_results() -> None:
    from scholariq.ingestion.types import ExtractedContent

    it = interpret(ExtractedContent(SourceKind.TEXT, []))
    assert it.candidates == []
    assert any("No subject results" in w for w in it.warnings)
