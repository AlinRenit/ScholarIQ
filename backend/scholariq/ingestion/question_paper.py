"""Read questions, sub-questions and marks from an exam question paper.

Input is the same ``ExtractedContent`` the marksheet importer uses (PDF text,
or OCR for scans and photos), so no new reading code is involved. Everything
here is deterministic pattern matching over text lines:

* Question labels at the start of a line: ``Q1``, ``Q.1``, ``Question 1``,
  ``1.``, ``1)``, sub-questions ``(a)``, ``a)``, ``b.``, and roman parts
  ``(i)``, ``ii)``. Compact forms such as ``2(b)(i)`` or ``Q2 a)`` work too.
  A bare number counts as a new question only when it continues the
  numbering, so "2 marks each" inside a question is not mistaken for Q2.
* Marks at the end of a line: ``[5]``, ``(5 marks)``, ``[5M]``, ``5 marks``,
  ``(3+2)``, a trailing ``(10)``, or a marks column in a ruled table.
* Sections and choices: ``Section A``, ``PART B``, ``Module II``,
  "Answer any two questions", "Each question carries 5 marks",
  "(5 x 2 = 10)", and ``OR`` between two alternatives.
* Lines that do not start a question continue the previous one.

When a question has sub-questions with their own marks, the sub-questions are
the markable items and the parent text becomes their context. When only the
parent carries marks, the parent is one item that includes its parts.

Every item gets a heuristic confidence (reading confidence x label certainty x
marks certainty). It is a ranking aid for the review screen, not a
probability. Nothing parsed here is used until the student has reviewed it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from scholariq.ingestion.types import ExtractedContent, Row

PARSER_NAME = "question-paper/1"
MAX_QUESTION_MARKS = Decimal(200)
MAX_PAPER_TOTAL = Decimal(1000)
REVIEW_BELOW = 0.6

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]
_ROMAN_VALUE = {r: n for n, r in enumerate(_ROMAN, 1)}
_UPPER_ROMAN = {r.upper(): n for r, n in _ROMAN_VALUE.items()}

_NUM = r"\d+(?:\.\d+)?"
# Marks at the end of a line.
_MARKS_BRACKETED = re.compile(
    rf"[\[(]\s*((?:{_NUM}\s*\+\s*)*{_NUM})\s*(marks?|mks?\.?|m)?\s*[\])]\s*$", re.I
)
# "Define a stack. 3": a small number after the end of a sentence (marks column
# flattened into the text line).
_MARKS_TRAILING_NUMBER = re.compile(r"[.?:)]\s+(\d{1,2}(?:\.5)?)$")
_MARKS_WORD = re.compile(rf"(?<![\w.])({_NUM})\s*(?:marks?|mks?)\.?\s*$", re.I)
# Course-outcome / Bloom-level columns printed after the marks in many papers.
_TRAILING_CODES = re.compile(r"(?:\s+(?:CO|BL|L|K|PO)\s*-?\s*\d{1,2})+\s*$", re.I)
_PAGE_FOOTER = re.compile(r"^(?:page\s*\d+(?:\s*of\s*\d+)?|\d+\s*/\s*\d+|-+\s*\d+\s*-+)$", re.I)
_DECORATION = re.compile(r"^[\W_]*$")
_OR_LINE = re.compile(r"^\(?\s*or\s*\)?$", re.I)
_TOTAL = re.compile(
    rf"(?:max(?:imum)?\.?\s*marks?|total\s*marks?|full\s*marks?)\s*[:\-–=]?\s*({_NUM})", re.I
)
_TIME = re.compile(r"\b(?:time|duration)\s*[:\-–]", re.I)
_SECTION = re.compile(r"^(?:section|part)\s*[-–:]?\s*([A-Z]|[IVX]{1,4}|\d{1,2})\b\.?\s*(.*)$", re.I)
_MODULE = re.compile(r"^(?:module|unit)\s*[-–:]?\s*([IVX]{1,4}|\d{1,2})\b\.?\s*(.*)$", re.I)
_ANSWER_ANY = re.compile(r"\b(?:answer|attempt)\s+any\s+(\d+|[a-z]+)\b", re.I)
_ANSWER_ALL = re.compile(r"\b(?:answer|attempt)\s+all\b", re.I)
_EACH_MODULE = re.compile(r"\b(?:from|in)\s+each\s+(?:module|unit)\b", re.I)
_EACH_CARRIES = re.compile(
    rf"\beach\s+(?:question\s+|sub-?question\s+)?carries\s+({_NUM})\s*marks?", re.I
)
_PRODUCT = re.compile(rf"(\d+)\s*[x×X*]\s*({_NUM})\s*=\s*({_NUM})")

_Q_PREFIX = re.compile(r"^(?:q(?:uestion)?|q\.?\s*no)\s*\.?\s*(\d{1,3})\b\s*[.):\-]?\s*", re.I)
_BARE_PUNCT = re.compile(r"^(\d{1,3})\s*(?:[.)]|:)(?!\d)\s*")
_BARE_COMPACT = re.compile(r"^(\d{1,3})(?=\s*\(?[a-h]\s*[).])")
_BARE_SPACE = re.compile(r"^(\d{1,3})\s+(?=[A-Z(\"'])")
_LETTER = re.compile(r"^(?:\(\s*([a-z])\s*\)|([a-z])\s*[).])\s*")
_ROMAN_LABEL = re.compile(
    r"^(?:\(\s*(i{1,3}|iv|vi{0,3}|ix|xi{0,2})\s*\)|(i{1,3}|iv|vi{0,3}|ix|xi{0,2})\s*[).])\s*"
)


@dataclass(frozen=True)
class Line:
    text: str
    page: int | None
    confidence: float
    # Marks found in a separate table cell at the end of the row.
    cell_marks: Decimal | None = None


@dataclass
class _Node:
    top: str
    letter: str | None
    roman: str | None
    section: str | None
    module: str | None
    page: int | None
    label_confidence: float
    texts: list[str] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    marks: Decimal | None = None
    marks_confidence: float = 0.0
    children: list[_Node] = field(default_factory=list)

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(p for p in (self.top, self.letter, self.roman) if p)

    @property
    def label(self) -> str:
        return self.top + "".join(f"({p})" for p in (self.letter, self.roman) if p)

    @property
    def text(self) -> str:
        return _squash(" ".join(self.texts))

    @property
    def reading_confidence(self) -> float:
        return min((ln.confidence for ln in self.lines), default=1.0)

    def has_marks_below(self) -> bool:
        return any(c.marks is not None or c.has_marks_below() for c in self.children)


@dataclass
class ParsedQuestion:
    label: str
    text: str
    context: str | None
    section: str | None
    paper_module: str | None
    page: int | None
    max_marks: Decimal | None
    confidence: float
    is_optional: bool = False
    choice_group: str | None = None
    needs_review: bool = False
    source_text: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class PaperParse:
    questions: list[ParsedQuestion]
    declared_total: Decimal | None
    choice_rules: dict[str, int]
    warnings: list[str]
    parser: str = PARSER_NAME


@dataclass
class _SectionRule:
    choose: int | None = None
    per_module: bool = False
    each_carries: Decimal | None = None
    product: tuple[int, Decimal, Decimal] | None = None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _decimal(text: str) -> Decimal | None:
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _count(word: str) -> int | None:
    return int(word) if word.isdigit() else _NUMBER_WORDS.get(word.lower())


def lines_from_content(content: ExtractedContent) -> list[Line]:
    out: list[Line] = []
    for block in content.blocks:
        for row in block.rows:
            line = _line_from_row(row, block.page)
            if line is not None:
                out.append(line)
    return out


_CODE_CELL = re.compile(r"(?:CO|BL|L|K|PO)\s*-?\s*\d{1,2}", re.I)


def _line_from_row(row: Row, page: int | None) -> Line | None:
    cells = [c for c in row.cells if c.text.strip()]
    if not cells:
        return None
    conf = min(c.confidence for c in cells)
    cell_marks = None
    # A ruled table with a marks column: the last cell is a number, possibly
    # next to course-outcome / Bloom-level code cells, which are dropped.
    if len(cells) >= 2:

        def strip_codes() -> None:
            while len(cells) > 1 and _CODE_CELL.fullmatch(cells[-1].text.strip()):
                cells.pop()

        strip_codes()
        tail = cells[-1].text.strip().strip("[]() ")
        value = _decimal(tail) if re.fullmatch(_NUM, tail) else None
        if len(cells) >= 2 and value is not None and 0 < value <= MAX_QUESTION_MARKS:
            cell_marks = value
            cells.pop()
            strip_codes()
    text = _squash(" ".join(c.text for c in cells))
    return Line(text, page if page is not None else 1, conf, cell_marks)


def _strip_marks(text: str) -> tuple[str, Decimal | None, float]:
    """Remove a marks annotation from the end of ``text``."""
    body = _TRAILING_CODES.sub("", text).rstrip()
    m = _MARKS_BRACKETED.search(body)
    if m:
        parts = [_decimal(p) for p in re.split(r"\s*\+\s*", m.group(1))]
        if all(p is not None for p in parts):
            value = sum((p for p in parts if p is not None), Decimal(0))
            unit = m.group(2)
            square = m.group(0).lstrip().startswith("[")
            if 0 < value <= MAX_QUESTION_MARKS and (unit or square or value <= 100):
                confidence = 1.0 if unit else 0.95 if square else 0.8
                return body[: m.start()].rstrip(), value, confidence
    m = _MARKS_TRAILING_NUMBER.search(body)
    if m:
        bare = _decimal(m.group(1))
        if bare is not None and 0 < bare <= 50:
            return body[: m.start() + 1].rstrip(), bare, 0.75
    m = _MARKS_WORD.search(body)
    if m:
        word_value = _decimal(m.group(1))
        if word_value is not None and 0 < word_value <= MAX_QUESTION_MARKS:
            return body[: m.start()].rstrip(" -–:,"), word_value, 1.0
    return text, None, 0.0


@dataclass
class _Label:
    top: str | None
    letter: str | None
    roman: str | None
    rest: str
    confidence: float


class _Parser:
    def __init__(self) -> None:
        self.nodes: list[_Node] = []
        self.by_key: dict[tuple[str, str | None, str | None], _Node] = {}
        self.current: _Node | None = None
        self.last_top = 0
        self.section: str | None = None
        self.module: str | None = None
        self.rules: dict[str | None, _SectionRule] = {}
        self.module_rules: dict[tuple[str | None, str], _SectionRule] = {}
        self.or_pairs: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self.pending_or: tuple[str, ...] | None = None
        self.declared_total: Decimal | None = None
        self.warnings: list[str] = []

    # -- labels ---------------------------------------------------------- #

    def _letter_or_roman(self, rest: str, letter: str | None) -> tuple[str, str | None, str | None]:
        """Read an optional sub-question letter and roman part from ``rest``."""
        roman = None
        rest = rest.lstrip()
        m = _LETTER.match(rest)
        if m:
            ch = m.group(1) or m.group(2)
            if ch in "ivx" and self._is_roman(ch, letter):
                rm = _ROMAN_LABEL.match(rest)
                if rm:
                    return rest[rm.end() :], letter, rm.group(1) or rm.group(2)
            elif ch <= "l":
                letter = ch
                rest = rest[m.end() :]
                rm = _ROMAN_LABEL.match(rest)
                if rm:
                    roman = rm.group(1) or rm.group(2)
                    rest = rest[rm.end() :]
                return rest, letter, roman
            return rest, None, None
        rm = _ROMAN_LABEL.match(rest)
        if rm:
            return rest[rm.end() :], letter, rm.group(1) or rm.group(2)
        return rest, None, None

    def _is_roman(self, ch: str, letter: str | None) -> bool:
        cur = self.current
        prev_letter = cur.letter if cur else None
        if ch == "i" and prev_letter == "h":
            return False
        if ch in "vx":
            prev_roman = cur.roman if cur else None
            return (
                prev_roman is not None and _ROMAN_VALUE.get(prev_roman, 0) + 1 == _ROMAN_VALUE[ch]
            )
        return True

    def read_label(self, text: str) -> _Label | None:
        m = _Q_PREFIX.match(text)
        top_conf = 1.0
        if m:
            top: str | None = m.group(1)
        else:
            m = _BARE_PUNCT.match(text) or _BARE_COMPACT.match(text)
            top = m.group(1) if m else None
            if m is None:
                m = _BARE_SPACE.match(text)
                # A bare number followed by a space must continue the numbering exactly.
                if m and (
                    int(m.group(1)) == self.last_top + 1
                    or (self.current is None and int(m.group(1)) > self.last_top)
                ):
                    top = m.group(1)
                    top_conf = 0.8
                else:
                    m = None
            elif top is not None:
                n = int(top)
                sequential = self.last_top < n <= self.last_top + 3
                # Right after a heading, numbering may jump (Part B starts at 11)
                # or restart at 1.
                after_heading = self.current is None and (n > self.last_top or n == 1)
                if not (sequential or after_heading):
                    return None
                top_conf = 1.0 if n == self.last_top + 1 or (after_heading and n == 1) else 0.75
        if m is not None and top is not None:
            rest, letter, roman = self._letter_or_roman(text[m.end() :], None)
            return _Label(top, letter, roman, rest, top_conf)
        if self.current is None:
            return None
        rest, letter, roman = self._letter_or_roman(text, self.current.letter)
        if letter is None and roman is None:
            return None
        if letter is not None and letter == self.current.letter and roman is None:
            return None  # "a." repeated: more likely prose than a new part
        return _Label(None, letter, roman, rest, 0.9)

    # -- lines ----------------------------------------------------------- #

    def feed(self, line: Line) -> None:
        text = line.text.strip()
        if not text or _DECORATION.match(text) or _PAGE_FOOTER.match(text):
            return
        if _OR_LINE.match(text):
            if self.current is not None:
                self.pending_or = self.current.path
            return
        if self._header(text):
            return
        if self._heading(text):
            return
        label = self.read_label(text)
        if label is None or (label.top is None and label.letter is None and label.roman is None):
            self._continue(line, text)
            return
        self._start(line, label)

    def _header(self, text: str) -> bool:
        m = _TOTAL.search(text)
        if m and (self.current is None or _TIME.search(text)):
            value = _decimal(m.group(1))
            if value is not None and 0 < value <= MAX_PAPER_TOTAL:
                self.declared_total = value
            return True
        return self.current is None and bool(_TIME.search(text))

    def _heading(self, text: str) -> bool:
        m = _SECTION.match(text)
        if m and len(m.group(2)) < 120:
            self.section = f"{text[: m.start(1)].strip().title()} {m.group(1).upper()}"
            self.module = None
            self.rules.setdefault(self.section, _SectionRule())
            self._instruction(m.group(2))
            self.current = None
            return True
        m = _MODULE.match(text)
        if m and len(m.group(2)) < 120 and not _LETTER.match(m.group(2) or "x"):
            number = m.group(1).upper()
            number = str(_UPPER_ROMAN.get(number, number))
            self.module = f"{text[: m.start(1)].strip().title()} {number}"
            self._instruction(m.group(2))
            self.current = None
            return True
        if _ANSWER_ANY.search(text) or _ANSWER_ALL.search(text) or _EACH_CARRIES.search(text):
            if len(text) < 200:
                self._instruction(text)
                return True
        if self.current is None and _PRODUCT.search(text) and len(text) < 80:
            self._instruction(text)
            return True
        return False

    def _instruction(self, text: str) -> None:
        if not text:
            return
        rule = self.rules.setdefault(self.section, _SectionRule())
        if self.module is not None:
            rule = self.module_rules.setdefault((self.section, self.module), _SectionRule())
        if m := _ANSWER_ANY.search(text):
            rule.choose = _count(m.group(1))
            rule.per_module = bool(_EACH_MODULE.search(text))
        if m := _EACH_CARRIES.search(text):
            rule.each_carries = _decimal(m.group(1))
        if m := _PRODUCT.search(text):
            a, b, total = int(m.group(1)), _decimal(m.group(2)), _decimal(m.group(3))
            if b is not None and total is not None and a * b == total:
                rule.product = (a, b, total)

    def _continue(self, line: Line, text: str) -> None:
        node = self.current
        if node is None:
            return  # title, university name, instructions before the first question
        body, marks, conf = _strip_marks(text)
        if marks is None and line.cell_marks is not None:
            marks, conf = line.cell_marks, 0.9
        node.texts.append(body)
        node.lines.append(line)
        if marks is not None and node.marks is None:
            node.marks, node.marks_confidence = marks, conf

    def _start(self, line: Line, label: _Label) -> None:
        cur = self.current
        if label.top is not None:
            top, letter, roman = label.top, label.letter, label.roman
            self.last_top = int(top)
        else:
            assert cur is not None
            top = cur.top
            letter = label.letter if label.letter is not None else cur.letter
            roman = label.roman
        # Make sure parents exist ("2(a)" read before any "2" line).
        if (top, None, None) not in self.by_key:
            self._node(top, None, None, line, label.confidence)
        if letter and roman and (top, letter, None) not in self.by_key:
            self._node(top, letter, None, line, label.confidence)
        node = self.by_key.get((top, letter, roman))
        if node is None:
            node = self._node(top, letter, roman, line, label.confidence)
        if self.pending_or is not None:
            if label.top is not None:
                # "11 ... OR 12 ...": the whole questions are the alternatives.
                self.or_pairs.append((self.pending_or[:1], (top,)))
            elif len(self.pending_or) == len(node.path):
                self.or_pairs.append((self.pending_or, node.path))
        self.pending_or = None
        self.current = node
        self._continue(line, label.rest)
        if not node.lines:
            node.lines.append(line)

    def _node(
        self, top: str, letter: str | None, roman: str | None, line: Line, confidence: float
    ) -> _Node:
        node = _Node(top, letter, roman, self.section, self.module, line.page, confidence)
        self.by_key[(top, letter, roman)] = node
        if letter is None and roman is None:
            self.nodes.append(node)
        else:
            parent = self.by_key[(top, letter, None) if roman else (top, None, None)]
            parent.children.append(node)
        return node

    # -- result ---------------------------------------------------------- #

    def result(self) -> PaperParse:
        items: list[tuple[_Node, ParsedQuestion]] = []
        for top in self.nodes:
            for node, item in self._items(top, []):
                items.append((node, item))
        choice_rules = self._apply_choices(items)
        self._apply_defaults(items)
        questions = [q for _, q in items]
        for q in questions:
            q.needs_review = q.needs_review or q.max_marks is None or q.confidence < REVIEW_BELOW
            if q.max_marks is None:
                q.notes.append("Maximum marks not found; enter them.")
        warnings = list(self.warnings)
        if not questions:
            warnings.append("No numbered questions were found. Add the questions by hand.")
        expected = _expected_total(questions, choice_rules)
        if self.declared_total is not None and expected is not None:
            if expected != self.declared_total:
                warnings.append(
                    f"The questions add up to {_fmt(expected)} marks but the paper says "
                    f"{_fmt(self.declared_total)}. Check the marks and the choice rules."
                )
        return PaperParse(questions, self.declared_total, choice_rules, warnings)

    def _items(self, node: _Node, context: list[str]) -> list[tuple[_Node, ParsedQuestion]]:
        if not node.children or (node.marks is not None and not node.has_marks_below()):
            return [(node, _question(node, context, collapse=bool(node.children)))]
        out = []
        ctx = [*context, f"{node.label}: {node.text}"] if node.text else context
        if node.marks is not None:
            total = sum((_leaf_total(c) for c in node.children), Decimal(0))
            if total and total != node.marks:
                self.warnings.append(
                    f"Q{node.label}: its parts add up to {_fmt(total)} marks, "
                    f"but the question shows {_fmt(node.marks)}."
                )
        for child in node.children:
            out += self._items(child, ctx)
        return out

    def _apply_choices(self, items: list[tuple[_Node, ParsedQuestion]]) -> dict[str, int]:
        rules: dict[str, int] = {}
        for a, b in self.or_pairs:
            group = f"Q{_path_label(a)} or Q{_path_label(b)}"
            hit = False
            for node, q in items:
                if node.path[: len(a)] in (a, b):
                    q.is_optional, q.choice_group = True, group
                    hit = True
            if hit:
                rules[group] = 1
        for node, q in items:
            if q.choice_group is not None:
                continue
            rule = self.module_rules.get((node.section, node.module or "")) if node.module else None
            section_rule = self.rules.get(node.section)
            if section_rule and section_rule.per_module and node.module:
                rule = section_rule
                group = " ".join(p for p in (node.section, node.module) if p)
            elif rule is not None:
                group = " ".join(p for p in (node.section, node.module) if p)
            else:
                rule = section_rule
                group = node.section or "Paper"
            if rule is None or rule.choose is None:
                continue
            tops = {n.top for n, _ in items if _same_group(n, node, rule)}
            if rule.choose < len(tops):
                q.is_optional, q.choice_group = True, group
                rules[group] = rule.choose
        return rules

    def _apply_defaults(self, items: list[tuple[_Node, ParsedQuestion]]) -> None:
        for node, q in items:
            if q.max_marks is not None:
                continue
            rule = self.rules.get(node.section)
            if node.module and (node.section, node.module) in self.module_rules:
                rule = self.module_rules[(node.section, node.module)]
            if rule is None:
                continue
            value = rule.each_carries
            if value is None and rule.product is not None:
                a, b, total = rule.product
                tops = len({n.top for n, _ in items if n.section == node.section})
                # "5 x 2 = 10": five questions of two marks, or two of five.
                value = b if tops == a or rule.choose == a else total / Decimal(tops or 1)
                if tops != a and Decimal(tops) * value != total:
                    value = b
            if value is not None and node.letter is None and node.roman is None:
                q.max_marks = value
                q.confidence = round(q.confidence * 0.75 / 0.5, 3)
                q.notes.append("Marks taken from the section instructions.")


def _same_group(a: _Node, b: _Node, rule: _SectionRule) -> bool:
    if a.section != b.section:
        return False
    return a.module == b.module if rule.per_module or a.module or b.module else True


def _path_label(path: tuple[str, ...]) -> str:
    return path[0] + "".join(f"({p})" for p in path[1:])


def _leaf_total(node: _Node) -> Decimal:
    if node.marks is not None:
        return node.marks
    return sum((_leaf_total(c) for c in node.children), Decimal(0))


def _question(node: _Node, context: list[str], collapse: bool) -> ParsedQuestion:
    text = node.text
    lines = list(node.lines)
    if collapse:
        parts = []
        for child in _descendants(node):
            parts.append(f"({child.roman or child.letter}) {child.text}")
            lines += child.lines
        text = _squash(" ".join([text, *parts]))
    reading = min((ln.confidence for ln in lines), default=1.0)
    marks_conf = node.marks_confidence if node.marks is not None else 0.5
    confidence = reading * node.label_confidence * marks_conf
    if len(text) < 5:
        confidence *= 0.7
    notes = []
    if reading < 0.8:
        notes.append("Read with OCR at low confidence; check the text and marks.")
    return ParsedQuestion(
        label=node.label,
        text=text,
        context=" / ".join(context) or None,
        section=node.section,
        paper_module=node.module,
        page=node.page,
        max_marks=node.marks,
        confidence=round(min(max(confidence, 0.0), 1.0), 3),
        source_text=_squash(" ".join(ln.text for ln in lines))[:1000],
        notes=notes,
    )


def _descendants(node: _Node) -> list[_Node]:
    out = []
    for c in node.children:
        out.append(c)
        out += _descendants(c)
    return out


def _expected_total(questions: list[ParsedQuestion], rules: dict[str, int]) -> Decimal | None:
    """Marks a complete script can earn: required items plus the chosen ones.

    Unknown when a mark is missing or a choice group has unequal options.
    """
    if any(q.max_marks is None for q in questions):
        return None
    total = sum((q.max_marks or Decimal(0) for q in questions if not q.is_optional), Decimal(0))
    for group, choose in rules.items():
        members = [q for q in questions if q.choice_group == group]
        tops: dict[str, Decimal] = {}
        for q in members:
            key = _top_key(q.label, group)
            tops[key] = tops.get(key, Decimal(0)) + (q.max_marks or Decimal(0))
        values = set(tops.values())
        if len(values) != 1:
            return None
        total += values.pop() * min(choose, len(tops))
    return total


def _top_key(label: str, group: str) -> str:
    # In an "OR" between sub-parts the alternatives are the parts themselves.
    if "(" in group:
        return label[: label.index(")") + 1] if ")" in label else label
    return re.match(r"\d+", label).group(0) if re.match(r"\d+", label) else label  # type: ignore[union-attr]


def _fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


def parse_lines(lines: list[Line]) -> PaperParse:
    parser = _Parser()
    for line in lines:
        parser.feed(line)
    return parser.result()


def parse_question_paper(content: ExtractedContent) -> PaperParse:
    return parse_lines(lines_from_content(content))


def parse_text(text: str, confidence: float = 1.0) -> PaperParse:
    """Convenience for plain text (tests, pasted papers)."""
    return parse_lines([Line(t, 1, confidence) for t in text.splitlines()])
