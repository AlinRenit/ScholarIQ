"""Interpret extracted rows as candidate assessment results.

Layout parsers are pluggable: each scores how well it fits a document and the
best-scoring one produces the candidates. Two parsers ship today:

* ``HeaderTableParser`` finds header rows (by matching column names against a
  synonym dictionary) and reads the rows beneath them column by column. It
  covers tabular marksheets, spreadsheets and CSV exports.
* ``LineFallbackParser`` reads rows without a recognised header, using value
  order (subject text, then marks/max/grade). It is deliberately conservative
  and marks everything it produces as low confidence.

Candidates are never academic records. They feed the review screen, and only
student-confirmed values are saved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from rapidfuzz import fuzz

from scholariq.domain.enums import ExamType, ResultComponent, ResultStatus
from scholariq.ingestion.types import Cell, ExtractedContent, Row, SourceKind
from scholariq.ingestion.values import (
    MarkKind,
    ParsedMark,
    find_semester,
    parse_credits,
    parse_grade,
    parse_mark,
    parse_semester_value,
    to_decimal,
)

# Fields below this confidence are highlighted for the student.
REVIEW_THRESHOLD = 0.8


class Role(StrEnum):
    CODE = "code"
    SUBJECT = "subject"
    OBTAINED = "obtained"
    MAX = "max"
    PERCENT = "percent"
    INTERNAL = "internal"
    EXTERNAL = "external"
    THEORY = "theory"
    PRACTICAL = "practical"
    GRADE = "grade"
    GRADE_POINTS = "grade_points"
    CREDITS = "credits"
    SEMESTER = "semester"
    RESULT = "result"
    SERIAL = "serial"


# Normalised header text -> role. Matching is exact first, then fuzzy.
HEADER_SYNONYMS: dict[Role, tuple[str, ...]] = {
    Role.SERIAL: ("s no", "sl no", "sr no", "serial", "no", "s n", "#"),
    Role.CODE: ("code", "subject code", "course code", "paper code", "sub code", "course no",
                "paper id", "subject id", "course id"),
    Role.SUBJECT: ("subject", "subject name", "subjects", "course", "course name", "course title",
                   "paper", "paper name", "title", "subject title", "name of the subject",
                   "name of subject", "module"),
    Role.OBTAINED: ("marks", "marks obtained", "obtained", "marks secured", "secured", "score",
                    "total", "total marks", "marks scored", "scored", "obtained marks",
                    "total obtained", "mark"),
    Role.MAX: ("max", "max marks", "maximum", "maximum marks", "out of", "full marks",
               "total max", "max mark", "max score", "maximum score"),
    Role.PERCENT: ("percentage", "percent", "%", "marks %", "score %"),
    Role.INTERNAL: ("internal", "internal marks", "ia", "cie", "sessional", "int"),
    Role.EXTERNAL: ("external", "external marks", "see", "ese", "university exam", "ext",
                    "end sem", "end semester"),
    Role.THEORY: ("theory", "theory marks", "th"),
    Role.PRACTICAL: ("practical", "practical marks", "lab", "lab marks", "pr"),
    Role.GRADE: ("grade", "letter grade", "grd", "grade obtained", "grades"),
    Role.GRADE_POINTS: ("grade point", "grade points", "gp", "points", "grade pt"),
    Role.CREDITS: ("credit", "credits", "cr", "credit hours", "units", "credit points"),
    Role.SEMESTER: ("semester", "sem", "term"),
    Role.RESULT: ("result", "status", "remarks", "remark", "pass fail"),
}  # fmt: skip

_SYNONYM_LOOKUP = {s: role for role, syns in HEADER_SYNONYMS.items() for s in syns}
_VALUE_ROLES = {
    Role.OBTAINED, Role.MAX, Role.PERCENT, Role.GRADE, Role.GRADE_POINTS,
    Role.CREDITS, Role.THEORY, Role.PRACTICAL, Role.INTERNAL, Role.EXTERNAL,
}  # fmt: skip

_SUMMARY = re.compile(
    r"^(grand\s+)?(total|sgpa|cgpa|gpa|percentage|aggregate|result|overall|credits earned)\b",
    re.IGNORECASE,
)
_NOT_SUBJECT = re.compile(
    r"\b(name of (the )?(student|candidate)|roll|register|reg\.? no|enrol+ment|father|mother|"
    r"date of|university|college|institute|signature|controller|principal|seat no|prn|usn|"
    r"statement of|marks ?(card|sheet)|grade (card|sheet)|examination held|page \d)\b",
    re.IGNORECASE,
)
_LAB = re.compile(r"\b(lab|laboratory|practical|practicals|workshop)\b", re.IGNORECASE)
_SUPPLEMENTARY = re.compile(r"\b(supplementary|supply|re-?appear|improvement|re-?exam)\b", re.I)
_BACKLOG = re.compile(r"\b(backlog|arrear|ATKT|carry ?over)\b", re.IGNORECASE)
_REGULAR = re.compile(r"\bregular\b", re.IGNORECASE)
_EXAM_NAME = re.compile(
    r"\b(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s/-]*(?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_CODE_PREFIX = re.compile(r"^([A-Z]{2,5}[- ]?\d{2,4}[A-Z]?|\d{2}[A-Z]{2,4}\d{2,3}[A-Z]?)\s+(.+)$")
_EMPTY_MARKERS = {"", "-", "--", "—", "NA", "N/A", "na", "n/a", "*"}
_COMMON_MAX = {Decimal(v) for v in (10, 15, 20, 25, 30, 40, 50, 60, 70, 75, 80, 100, 125, 150,
                                    200)}  # fmt: skip


def normalise_header(text: str) -> str:
    t = text.lower().replace("&", " and ").replace(".", " ")
    t = re.sub(r"[^a-z0-9%#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def match_header(text: str) -> tuple[Role | None, float]:
    norm = normalise_header(text)
    if not norm:
        return None, 0.0
    if norm in _SYNONYM_LOOKUP:
        return _SYNONYM_LOOKUP[norm], 1.0
    # Headers like "Marks Obtained (100)" or "Credits*": strip trailing qualifiers.
    stripped = re.sub(r"\s*\d+$", "", norm).strip()
    if stripped in _SYNONYM_LOOKUP:
        return _SYNONYM_LOOKUP[stripped], 0.95
    best: tuple[Role | None, float] = (None, 0.0)
    for syn, role in _SYNONYM_LOOKUP.items():
        if len(syn) < 4:
            continue  # short synonyms only match exactly
        score = fuzz.ratio(norm, syn) / 100
        if score > best[1]:
            best = (role, score)
    return best if best[1] >= 0.86 else (None, 0.0)


# --------------------------------------------------------------------------- #
# Candidates
# --------------------------------------------------------------------------- #


@dataclass
class Candidate:
    row_index: int
    source_text: str
    fields: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def set(self, name: str, value: Any, confidence: float) -> None:
        if isinstance(value, Decimal):
            value = format(value.normalize(), "f")
        self.fields[name] = value
        self.confidence[name] = round(max(0.0, min(1.0, confidence)), 2)


@dataclass
class DocumentContext:
    semester: int | None = None
    exam_type: ExamType = ExamType.UNKNOWN
    exam_name: str | None = None


@dataclass
class Interpretation:
    parser: str
    candidates: list[Candidate]
    context: DocumentContext
    grades_seen: list[str]
    warnings: list[str]


def _update_context(ctx: DocumentContext, text: str) -> None:
    if (sem := find_semester(text)) is not None:
        ctx.semester = sem
    if _BACKLOG.search(text):
        ctx.exam_type = ExamType.BACKLOG
    elif _SUPPLEMENTARY.search(text):
        ctx.exam_type = ExamType.SUPPLEMENTARY
    elif _REGULAR.search(text) and ctx.exam_type is ExamType.UNKNOWN:
        ctx.exam_type = ExamType.REGULAR
    if ctx.exam_name is None and (m := _EXAM_NAME.search(text)):
        ctx.exam_name = m.group(0)


def _split_code(subject: str) -> tuple[str | None, str]:
    if m := _CODE_PREFIX.match(subject.strip()):
        return m.group(1), m.group(2).strip()
    return None, subject.strip()


def _looks_like_subject(text: str) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    return (
        letters >= 3
        and letters >= len(text.replace(" ", "")) * 0.5
        and not _SUMMARY.match(text.strip())
        and not _NOT_SUBJECT.search(text)
    )


def _apply_mark(
    cand: Candidate, parsed: ParsedMark, reading_conf: float, interp_conf: float, label: str
) -> None:
    conf = reading_conf * interp_conf * parsed.confidence
    if parsed.note:
        cand.warnings.append(f"{label}: {parsed.note}.")
    match parsed.kind:
        case MarkKind.EMPTY:
            cand.set("status", ResultStatus.MISSING.value, conf)
        case MarkKind.STATUS:
            assert parsed.status is not None
            cand.set("status", parsed.status.value, conf)
        case MarkKind.UNREADABLE:
            cand.set("marks_obtained", None, 0.0)
        case MarkKind.NUMBER:
            cand.set("marks_obtained", parsed.value, conf)
        case MarkKind.FRACTION | MarkKind.PERCENT:
            cand.set("marks_obtained", parsed.value, conf)
            cand.set("max_marks", parsed.maximum, conf)
            if parsed.kind is MarkKind.PERCENT:
                cand.warnings.append("Score was given as a percentage; recorded out of 100.")


def finalise(cand: Candidate, ctx: DocumentContext) -> None:
    """Fill context fields and add validation warnings."""
    f = cand.fields
    if "semester" not in f:
        cand.set("semester", ctx.semester, 0.8 if ctx.semester is not None else 0.0)
    if "exam_type" not in f:
        cand.set("exam_type", ctx.exam_type.value, 0.8)
    if ctx.exam_name and "exam_name" not in f:
        cand.set("exam_name", ctx.exam_name, 0.8)
    if "component" not in f:
        name = str(f.get("subject_name") or "")
        comp = ResultComponent.LAB if _LAB.search(name) else ResultComponent.COMBINED
        cand.set("component", comp.value, 0.9)

    obtained, maximum = f.get("marks_obtained"), f.get("max_marks")
    status = f.get("status")
    if status is None:
        if obtained is not None or f.get("grade"):
            cand.set("status", ResultStatus.PRESENT.value, 1.0)
        else:
            cand.set("status", ResultStatus.MISSING.value, 0.5)
            status = ResultStatus.MISSING.value

    if status == ResultStatus.MISSING.value and not f.get("grade"):
        cand.warnings.append("No marks or grade found. Recorded as missing, not zero.")
    if obtained is not None and maximum is None:
        cand.warnings.append("Maximum marks not found. Add them so a percentage can be calculated.")
    if obtained is not None and maximum is not None:
        o, m = Decimal(str(obtained)), Decimal(str(maximum))
        if m <= 0:
            cand.warnings.append("Maximum marks must be greater than zero.")
        elif o > m:
            cand.warnings.append("Marks obtained are higher than maximum marks.")
    low = [k for k, v in cand.confidence.items() if v < REVIEW_THRESHOLD and k in f]
    if low:
        cand.warnings.append("Please check: " + ", ".join(sorted(low)).replace("_", " ") + ".")


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #


class LayoutParser(Protocol):
    name: str

    def parse(self, content: ExtractedContent) -> Interpretation: ...


def _header_roles(row: Row) -> dict[int, tuple[Role, float]]:
    roles: dict[int, tuple[Role, float]] = {}
    used: set[Role] = set()
    scored = []
    for i, cell in enumerate(row.cells):
        role, score = match_header(cell.text)
        if role is not None:
            scored.append((score, i, role))
    for score, i, role in sorted(scored, reverse=True):
        if role not in used:
            roles[i] = (role, score)
            used.add(role)
    return roles


def is_header(roles: dict[int, tuple[Role, float]]) -> bool:
    found = {r for r, _ in roles.values()}
    return Role.SUBJECT in found and bool(found & _VALUE_ROLES)


def _align(header: Row, row: Row) -> dict[int, Cell] | None:
    """Map header column index -> data cell. None when alignment is unreliable."""
    if all(c.x0 is not None for c in header.cells + row.cells):
        out: dict[int, Cell] = {}
        centres = [((c.x0 or 0) + (c.x1 or 0)) / 2 for c in header.cells]
        bounds = [((c.x0 or 0), (c.x1 or 0)) for c in header.cells]
        for cell in row.cells:
            x0, x1 = cell.x0 or 0, cell.x1 or 0
            overlaps = [max(0.0, min(x1, b1) - max(x0, b0)) for b0, b1 in bounds]
            if max(overlaps) > 0:
                idx = overlaps.index(max(overlaps))
            else:
                mid = (x0 + x1) / 2
                idx = min(range(len(centres)), key=lambda i: abs(centres[i] - mid))
            if idx in out:  # two cells in one column: join (e.g. split subject name)
                prev = out[idx]
                out[idx] = Cell(
                    f"{prev.text} {cell.text}",
                    min(prev.confidence, cell.confidence),
                    prev.x0,
                    cell.x1,
                )
            else:
                out[idx] = cell
        return out
    if len(row.cells) == len(header.cells):
        return dict(enumerate(row.cells))
    return None


class HeaderTableParser:
    name = "header_table"

    def parse(self, content: ExtractedContent) -> Interpretation:
        ctx = DocumentContext()
        ocr = content.source is SourceKind.OCR
        candidates: list[Candidate] = []
        misaligned: list[tuple[int, Row, DocumentContext]] = []
        index = 0
        for block in content.blocks:
            header: Row | None = None
            roles: dict[int, tuple[Role, float]] = {}
            for row in block.rows:
                index += 1
                row_roles = _header_roles(row)
                if is_header(row_roles):
                    header, roles = row, row_roles
                    continue
                if header is None:
                    _update_context(ctx, row.text)
                    continue
                aligned = _align(header, row)
                if aligned is None:
                    misaligned.append((index, row, _copy(ctx)))
                    continue
                produced = self._read_row(index, row, aligned, roles, ocr)
                if not produced:
                    # Text between tables can carry the next table's semester.
                    _update_context(ctx, row.text)
                for cand in produced:
                    finalise(cand, ctx)
                    candidates.append(cand)

        # Rows that could not be aligned to their header are read positionally.
        for idx, row, row_ctx in misaligned:
            if (fallback := read_line(idx, row, ocr)) is not None:
                cand = fallback
                cand.warnings.append("Row did not line up with the table header; check columns.")
                finalise(cand, row_ctx)
                candidates.append(cand)

        candidates.sort(key=lambda c: c.row_index)
        return _result(self.name, candidates, ctx)

    def _read_row(
        self,
        index: int,
        row: Row,
        cells: dict[int, Cell],
        roles: dict[int, tuple[Role, float]],
        ocr: bool,
    ) -> list[Candidate]:
        by_role = {role: (cells[i], score) for i, (role, score) in roles.items() if i in cells}
        if Role.SUBJECT not in by_role:
            return []
        subject_cell, subject_score = by_role[Role.SUBJECT]
        subject_text = subject_cell.text.strip()
        if not _looks_like_subject(subject_text):
            return []
        # Free-text rows need at least one value, otherwise they are captions or
        # notes. In a structured table an empty row is a genuinely missing result.
        structured = all(c.x0 is None for c in row.cells)
        has_value = any(by_role.get(r, (Cell(""), 0))[0].text.strip() for r in _VALUE_ROLES)
        if not has_value and not structured:
            return []

        base = Candidate(index, row.text)
        code_from_name, name = _split_code(subject_text)
        base.set("subject_name", name, subject_cell.confidence * subject_score)
        if Role.CODE in by_role and by_role[Role.CODE][0].text.strip():
            c, s = by_role[Role.CODE]
            base.set("subject_code", c.text.strip(), c.confidence * s)
        elif code_from_name:
            base.set("subject_code", code_from_name, subject_cell.confidence * 0.9)

        for role, fname in ((Role.GRADE, "grade"),):
            if role in by_role and by_role[role][0].text.strip() not in _EMPTY_MARKERS:
                c, s = by_role[role]
                grade = parse_grade(c.text)
                if grade:
                    base.set(fname, grade, c.confidence * s)
                else:
                    base.set(fname, c.text.strip(), 0.4)
                    base.warnings.append(f"Unrecognised grade '{c.text.strip()}'.")
        for role, fname in ((Role.GRADE_POINTS, "grade_points"), (Role.CREDITS, "credits")):
            if role in by_role and by_role[role][0].text.strip():
                c, s = by_role[role]
                value = parse_credits(c.text) if role is Role.CREDITS else _number(c.text)
                if value is not None:
                    base.set(fname, value, c.confidence * s)
                else:
                    base.warnings.append(f"Could not read {fname.replace('_', ' ')} '{c.text}'.")
        if Role.SEMESTER in by_role:
            c, s = by_role[Role.SEMESTER]
            sem = parse_semester_value(c.text) or find_semester(c.text)
            if sem is not None:
                base.set("semester", sem, c.confidence * s)
        if Role.RESULT in by_role:
            c, _ = by_role[Role.RESULT]
            text = c.text.strip().lower()
            if text in {"ab", "abs", "absent"}:
                base.set("status", ResultStatus.ABSENT.value, c.confidence)
            elif text in {"w", "wh", "withheld"}:
                base.set("status", ResultStatus.WITHHELD.value, c.confidence)
            if text:
                base.set("result", c.text.strip(), c.confidence)
        _apply_row_exam_type(base, row.text)

        # Separate theory and practical columns become two component records.
        if Role.THEORY in by_role and Role.PRACTICAL in by_role:
            out = []
            for role, comp in ((Role.THEORY, ResultComponent.THEORY),
                               (Role.PRACTICAL, ResultComponent.LAB)):  # fmt: skip
                c, s = by_role[role]
                if not c.text.strip():
                    continue
                cand = Candidate(index, row.text, dict(base.fields), dict(base.confidence),
                                 list(base.warnings))  # fmt: skip
                cand.set("component", comp.value, s)
                _apply_mark(cand, parse_mark(c.text, ocr), c.confidence, s, comp.value)
                out.append(cand)
            return out

        if Role.OBTAINED in by_role and by_role[Role.OBTAINED][0].text.strip():
            c, s = by_role[Role.OBTAINED]
            _apply_mark(base, parse_mark(c.text, ocr), c.confidence, s, "Marks")
        elif Role.PERCENT in by_role and by_role[Role.PERCENT][0].text.strip():
            c, s = by_role[Role.PERCENT]
            parsed = parse_mark(c.text.rstrip("%").strip(), ocr)
            if parsed.kind is MarkKind.NUMBER:
                base.set("marks_obtained", parsed.value, c.confidence * s * parsed.confidence)
                base.set("max_marks", Decimal(100), c.confidence * s)
                base.warnings.append("Score was given as a percentage; recorded out of 100.")
            else:
                _apply_mark(base, parsed, c.confidence, s, "Percentage")
        elif Role.INTERNAL in by_role and Role.EXTERNAL in by_role:
            ci, _ = by_role[Role.INTERNAL]
            ce, _ = by_role[Role.EXTERNAL]
            pi, pe = parse_mark(ci.text, ocr), parse_mark(ce.text, ocr)
            if pi.kind is MarkKind.NUMBER and pe.kind is MarkKind.NUMBER:
                assert pi.value is not None and pe.value is not None
                conf = min(ci.confidence, ce.confidence) * 0.7
                base.set("marks_obtained", pi.value + pe.value, conf)
                base.warnings.append("Total computed as internal + external marks; confirm it.")
            elif pe.kind is MarkKind.STATUS:
                _apply_mark(base, pe, ce.confidence, 1.0, "External")
        if Role.MAX in by_role and by_role[Role.MAX][0].text.strip():
            c, s = by_role[Role.MAX]
            parsed = parse_mark(c.text, ocr)
            if parsed.kind is MarkKind.NUMBER:
                base.set("max_marks", parsed.value, c.confidence * s * parsed.confidence)
            elif parsed.kind is MarkKind.FRACTION:
                base.set("max_marks", parsed.maximum, c.confidence * s * 0.8)
        return [base]


def _number(text: str) -> Decimal | None:
    t = text.strip()
    return to_decimal(t) if re.fullmatch(r"\d+(?:[.,]\d+)?", t) else None


def _apply_row_exam_type(cand: Candidate, text: str) -> None:
    if _BACKLOG.search(text):
        cand.set("exam_type", ExamType.BACKLOG.value, 0.9)
    elif _SUPPLEMENTARY.search(text):
        cand.set("exam_type", ExamType.SUPPLEMENTARY.value, 0.9)


def _copy(ctx: DocumentContext) -> DocumentContext:
    return DocumentContext(ctx.semester, ctx.exam_type, ctx.exam_name)


_TOKEN = re.compile(r"\S+")


def read_line(index: int, row: Row, ocr: bool) -> Candidate | None:
    """Positional reading: '<code?> <subject words> <numbers / fraction / grade>...'."""
    text = row.text
    if _SUMMARY.match(text) or _NOT_SUBJECT.search(text) or find_semester(text) is not None:
        return None
    tokens = _TOKEN.findall(text)
    name_parts: list[str] = []
    values: list[str] = []
    for tok in tokens:
        if not values and (re.search(r"[A-Za-z]{2,}", tok) and not parse_grade(tok)):
            name_parts.append(tok)
        elif name_parts:
            values.append(tok)
    # A trailing grade may have been absorbed into the name ("... Systems A+").
    if not name_parts or not values:
        return None
    subject = " ".join(name_parts)
    code, name = _split_code(subject)
    if not _looks_like_subject(name):
        return None

    conf = row.confidence * 0.6
    cand = Candidate(index, text)
    cand.set("subject_name", name, conf)
    if code:
        cand.set("subject_code", code, conf)

    marks: list[ParsedMark] = []
    for tok in values:
        if grade := parse_grade(tok):
            if grade in {"AB"}:
                cand.set("status", ResultStatus.ABSENT.value, conf)
            else:
                cand.set("grade", grade, conf)
            continue
        parsed = parse_mark(tok, ocr)
        if parsed.kind in (MarkKind.NUMBER, MarkKind.FRACTION, MarkKind.PERCENT, MarkKind.STATUS):
            marks.append(parsed)

    fractions = [m for m in marks if m.kind in (MarkKind.FRACTION, MarkKind.PERCENT)]
    numbers = [m for m in marks if m.kind is MarkKind.NUMBER and m.value is not None]
    statuses = [m for m in marks if m.kind is MarkKind.STATUS]
    if fractions:
        _apply_mark(cand, fractions[0], row.confidence, 0.7, "Marks")
    elif statuses:
        _apply_mark(cand, statuses[0], row.confidence, 0.7, "Marks")
    elif len(numbers) >= 2:
        a, b = numbers[0].value, numbers[1].value
        assert a is not None and b is not None
        if a <= b and b in _COMMON_MAX:
            cand.set("marks_obtained", a, conf)
            cand.set("max_marks", b, conf)
        elif b <= a and a in _COMMON_MAX:
            cand.set("marks_obtained", b, conf * 0.8)
            cand.set("max_marks", a, conf * 0.8)
        else:
            cand.set("marks_obtained", numbers[-1].value, conf * 0.6)
            cand.warnings.append("Several numbers on this line; check which one is the mark.")
    elif numbers:
        cand.set("marks_obtained", numbers[0].value, conf)
    elif "grade" not in cand.fields and "status" not in cand.fields:
        return None
    cand.warnings.append("Layout not recognised; values were read from text order.")
    return cand


class LineFallbackParser:
    name = "line_fallback"

    def parse(self, content: ExtractedContent) -> Interpretation:
        ctx = DocumentContext()
        ocr = content.source is SourceKind.OCR
        candidates = []
        for index, row in enumerate(content.rows(), 1):
            cand = read_line(index, row, ocr)
            if cand is None:
                _update_context(ctx, row.text)
                continue
            finalise(cand, ctx)
            candidates.append(cand)
        return _result(self.name, candidates, ctx)


def _result(name: str, candidates: list[Candidate], ctx: DocumentContext) -> Interpretation:
    warnings: list[str] = []
    seen: dict[tuple[str, str, str, str], int] = {}
    for c in candidates:
        key = (
            str(c.fields.get("subject_name", "")).lower(),
            str(c.fields.get("component")),
            str(c.fields.get("semester")),
            str(c.fields.get("exam_type")),
        )
        seen[key] = seen.get(key, 0) + 1
    for c in candidates:
        key = (
            str(c.fields.get("subject_name", "")).lower(),
            str(c.fields.get("component")),
            str(c.fields.get("semester")),
            str(c.fields.get("exam_type")),
        )
        if seen[key] > 1:
            c.warnings.append(
                "This subject appears more than once for the same semester and exam. "
                "Mark repeat attempts as supplementary or backlog, or remove the duplicate."
            )
    grades = sorted({str(c.fields["grade"]) for c in candidates if c.fields.get("grade")})
    if grades:
        warnings.append(
            "Grades found (" + ", ".join(grades) + "). They are kept exactly as printed and are "
            "not converted to numbers until you confirm which grading scale they use."
        )
    if ctx.semester is None and not any(c.fields.get("semester") for c in candidates):
        warnings.append("No semester found. Add it so results can be compared over time.")
    return Interpretation(name, candidates, ctx, grades, warnings)


PARSERS: list[LayoutParser] = [HeaderTableParser(), LineFallbackParser()]


def _quality(interp: Interpretation) -> float:
    if not interp.candidates:
        return 0.0
    mean_conf = sum(
        sum(c.confidence.values()) / max(len(c.confidence), 1) for c in interp.candidates
    ) / len(interp.candidates)
    return len(interp.candidates) * mean_conf


def interpret(
    content: ExtractedContent, parsers: list[LayoutParser] | None = None
) -> Interpretation:
    """Run each parser and keep the result with the best count x confidence."""
    results = [p.parse(content) for p in (parsers or PARSERS)]
    best = max(results, key=_quality)
    if not best.candidates:
        best.warnings.append(
            "No subject results could be found in this file. You can add them manually."
        )
    return best
