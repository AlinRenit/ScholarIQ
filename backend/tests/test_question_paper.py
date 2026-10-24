"""Question-paper parsing: labels, sub-questions, marks, sections and choices."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scholariq.ingestion.extract import extract, tesseract_available
from scholariq.ingestion.question_paper import (
    Line,
    parse_lines,
    parse_question_paper,
    parse_text,
)
from scholariq.ingestion.types import SourceKind
from scholariq.ingestion.validation import validate_upload

PAPERS = Path(__file__).parent / "fixtures" / "question_papers"
D = Decimal


def by_label(text: str) -> dict[str, object]:
    return {q.label: q for q in parse_text(text).questions}


def test_marks_beside_questions_in_common_notations() -> None:
    qs = parse_text(
        """1. Define a stack. [2]
2. What is a queue? (3 marks)
3. Explain hashing [5M]
4. State the master theorem 4 marks
5. Explain deadlock prevention. (3+2)
6. Explain paging. (10)
"""
    ).questions
    assert [(q.label, q.max_marks) for q in qs] == [
        ("1", D(2)),
        ("2", D(3)),
        ("3", D(5)),
        ("4", D(4)),
        ("5", D(5)),
        ("6", D(10)),
    ]
    assert qs[0].text == "Define a stack."
    assert qs[5].text == "Explain paging."
    # A bare "(10)" is plausible but less certain than "[2]" or "(3 marks)".
    assert qs[5].confidence < qs[1].confidence


def test_nested_subquestions_become_items_with_context() -> None:
    qs = by_label(
        """Q1. Answer the following.
(a) Define a tree. [2]
(b) (i) What is a leaf? [1]
    (ii) What is the height of a tree? [2]
Q2 a) What is a semaphore? [3]
Q2 b) Explain the dining philosophers problem [7]
3(a)(i) Define a graph. [1]
"""
    )
    assert list(qs) == ["1(a)", "1(b)(i)", "1(b)(ii)", "2(a)", "2(b)", "3(a)(i)"]
    leaf = qs["1(b)(ii)"]
    assert leaf.max_marks == D(2)  # type: ignore[attr-defined]
    assert leaf.context.startswith("1: Answer the following.")  # type: ignore[attr-defined]


def test_roman_parts_directly_under_a_question() -> None:
    qs = by_label("4. Explain.\n(i) First part [2]\n(ii) Second part [3]\n(iii) Third [1]\n")
    assert list(qs) == ["4(i)", "4(ii)", "4(iii)"]


def test_parent_marks_with_unmarked_parts_stay_one_item() -> None:
    qs = parse_text("5. Answer both parts. [10]\n(a) Define BFS.\n(b) Define DFS.\n").questions
    assert len(qs) == 1
    assert qs[0].label == "5" and qs[0].max_marks == D(10)
    assert "(a) Define BFS." in qs[0].text and "(b) Define DFS." in qs[0].text


def test_multi_line_questions_are_joined() -> None:
    qs = parse_text(
        "1. Explain how a queue can be implemented using a circular array,\n"
        "showing the enqueue and dequeue operations\n"
        "with an example. [6]\n"
        "2. Define a stack. [2]\n"
    ).questions
    assert qs[0].text == (
        "Explain how a queue can be implemented using a circular array, showing the "
        "enqueue and dequeue operations with an example."
    )
    assert qs[0].max_marks == D(6)


def test_numbers_inside_text_do_not_start_questions() -> None:
    qs = parse_text(
        "1. Insert the keys\n10 20 30 into an AVL tree. [5]\n"
        "2. Explain hashing. [5]\n"
        "5 marks are for the diagram.\n"
    ).questions
    assert [q.label for q in qs] == ["1", "2"]
    assert "10 20 30" in qs[0].text


def test_sections_answer_any_and_section_marks() -> None:
    r = parse_text(
        """Time: 3 Hours   Maximum Marks: 26
SECTION A
Answer all questions. (3 x 2 = 6)
1. Define a stack.
2. Define a queue.
3. Define a tree.
SECTION B
Answer any two questions.
4. Explain BFS. [10]
5. Explain DFS. [10]
6. Explain Dijkstra's algorithm. [10]
"""
    )
    qs = {q.label: q for q in r.questions}
    assert r.declared_total == D(26)
    assert [qs[n].max_marks for n in "123"] == [D(2), D(2), D(2)]
    assert qs["1"].section == "Section A" and not qs["1"].is_optional
    assert all(qs[n].is_optional and qs[n].choice_group == "Section B" for n in "456")
    assert r.choice_rules == {"Section B": 2}
    assert r.warnings == []  # 6 + 2 x 10 = 26


def test_total_mismatch_is_a_warning() -> None:
    r = parse_text("Max. Marks: 50\n1. Define a stack. [2]\n2. Define a queue. [3]\n")
    assert any("add up to 5" in w and "50" in w for w in r.warnings)


def test_or_between_questions_and_module_headings() -> None:
    r = parse_text(
        """PART B
Answer any one full question from each module.
Module I
11 a) Explain Big O notation. (7)
b) Solve T(n)=2T(n/2)+n. (7)
OR
12 Explain the master theorem. (14)
Module II
13 Explain merge sort. (14)
OR
14 Explain quick sort. (14)
"""
    )
    qs = {q.label: q for q in r.questions}
    assert set(qs) == {"11(a)", "11(b)", "12", "13", "14"}
    assert qs["11(a)"].choice_group == "Q11 or Q12" and qs["12"].is_optional
    assert qs["13"].paper_module == "Module 2"
    assert r.choice_rules == {"Q11 or Q12": 1, "Q13 or Q14": 1}


def test_marks_column_in_a_table_row() -> None:
    from scholariq.ingestion.types import Block, Cell, ExtractedContent, Row

    rows = [
        Row([Cell("1"), Cell("Define normalization."), Cell("CO1"), Cell("4")]),
        Row([Cell("2"), Cell("Explain 3NF with an example."), Cell("6")]),
    ]
    content = ExtractedContent(SourceKind.PDF_TEXT, [Block(rows, page=2)])
    qs = parse_question_paper(content).questions
    assert [(q.label, q.max_marks, q.page) for q in qs] == [("1", D(4), 2), ("2", D(6), 2)]
    assert qs[0].text == "Define normalization."


def test_uncertain_items_are_flagged_for_review() -> None:
    qs = parse_lines(
        [
            Line("1. Define a stack. [2]", 1, 0.95),
            Line("2. Explain queues", 1, 0.95),  # no marks
            Line("3. Expl@in h4shing [5]", 1, 0.40),  # poor OCR
        ]
    ).questions
    flags = {q.label: q.needs_review for q in qs}
    assert flags == {"1": False, "2": True, "3": True}
    assert any("Maximum marks not found" in n for n in qs[1].notes)
    assert any("OCR" in n for n in qs[2].notes)


def test_no_questions_found_says_so() -> None:
    r = parse_text("Example Institute of Technology\nInstructions to candidates\n")
    assert r.questions == []
    assert any("add the questions by hand" in w.lower() for w in r.warnings)


def test_digital_pdf_question_paper() -> None:
    data = (PAPERS / "digital_ds_paper.pdf").read_bytes()
    content = extract(validate_upload("paper.pdf", data, 10_000_000))
    assert content.source is SourceKind.PDF_TEXT
    r = parse_question_paper(content)
    qs = {q.label: q for q in r.questions}
    assert list(qs) == ["1", "2", "3", "4(a)", "4(b)", "5", "6", "7"]
    assert r.declared_total == D(34)
    assert qs["4(a)"].max_marks == D(6) and qs["6"].text.endswith("time complexity.")
    assert all(not q.needs_review for q in r.questions)
    assert r.warnings == []


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract not installed")
@pytest.mark.parametrize("name", ["scanned_ds_paper.png", "scanned_ds_paper.pdf"])
def test_scanned_question_paper_uses_ocr(name: str) -> None:
    data = (PAPERS / name).read_bytes()
    content = extract(validate_upload(name, data, 10_000_000))
    assert content.source is SourceKind.OCR
    r = parse_question_paper(content)
    labels = [q.label for q in r.questions]
    assert labels == ["1", "2", "3", "4(a)", "4(b)", "5", "6", "7"]
    assert sum((q.max_marks or 0) for q in r.questions if not q.is_optional) == 6 + 8
    # OCR readings carry their (lower) word confidence into the item confidence.
    assert all(q.confidence < 1 for q in r.questions)
