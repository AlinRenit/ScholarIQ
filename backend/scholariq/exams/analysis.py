"""Exam performance from question-level marks: overall, per module, per topic.

Rules, in order, for each question:

1. Flagged as uncertain (``needs_review``)       -> left out.
2. Maximum marks unknown                          -> left out.
3. Attempted with a mark (including an explicit 0) -> counted: mark / maximum.
4. Attempted without a mark                       -> left out (never zero).
5. Not attempted, optional (part of a choice)     -> left out; it is not part
   of this student's paper, so it must not enlarge the denominator.
6. Not attempted, required                        -> counted as 0 / maximum.
7. Attempt status unknown                         -> left out.

Percentages are always sum(marks obtained) / sum(maximum marks) over the
counted questions, never an average of percentages. A question mapped to
several topics or modules gives each one its share of both the marks obtained
and the maximum (shares are normalised to add up to 1), so a 10-mark question
split 60/40 counts as 6 marks for one topic and 4 for the other.

A module or topic is "partial" when a question mapped to it was left out for a
reason other than rule 5: its numbers cover only part of what the exam asked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from scholariq.domain.enums import AttemptStatus

ZERO = Decimal(0)
CENT = Decimal("0.01")


class Exclusion(StrEnum):
    NEEDS_REVIEW = "needs_review"
    NO_MAX = "no_max"
    NO_MARK = "no_mark"
    UNKNOWN_STATUS = "unknown_status"
    OPTIONAL_NOT_CHOSEN = "optional_not_chosen"


EXCLUSION_TEXT = {
    Exclusion.NEEDS_REVIEW: "Flagged as uncertain",
    Exclusion.NO_MAX: "Maximum marks not confirmed",
    Exclusion.NO_MARK: "Attempted, but the mark is missing",
    Exclusion.UNKNOWN_STATUS: "Not known whether it was attempted",
    Exclusion.OPTIONAL_NOT_CHOSEN: "Optional and not chosen",
}


@dataclass(frozen=True)
class MappingInput:
    topic_id: str | None
    module_id: str | None
    share: Decimal


@dataclass(frozen=True)
class QuestionInput:
    id: str
    label: str
    max_marks: Decimal | None
    marks_obtained: Decimal | None
    attempt_status: AttemptStatus
    is_optional: bool
    needs_review: bool
    mappings: tuple[MappingInput, ...] = ()


@dataclass(frozen=True)
class QuestionResult:
    id: str
    label: str
    counted: bool
    exclusion: Exclusion | None
    earned: Decimal | None
    possible: Decimal | None


@dataclass
class Tally:
    earned: Decimal = ZERO
    possible: Decimal = ZERO
    questions: list[str] = field(default_factory=list)
    # (question label, marks lost in this group from that question)
    lost_by: list[tuple[str, Decimal]] = field(default_factory=list)
    # Labels of questions mapped here but left out (rules 1, 2, 4, 7).
    left_out: list[str] = field(default_factory=list)
    module_only: list[str] = field(default_factory=list)
    topic_ids: list[str] = field(default_factory=list)

    @property
    def lost(self) -> Decimal:
        return self.possible - self.earned

    @property
    def fraction(self) -> Decimal | None:
        return self.earned / self.possible if self.possible > 0 else None

    @property
    def partial(self) -> bool:
        return bool(self.left_out)


@dataclass
class Breakdown:
    questions: list[QuestionResult]
    overall: Tally
    # module id (None = topics that are not in any module) -> tally
    modules: dict[str | None, Tally]
    topics: dict[str, Tally]
    unmapped: list[str]
    excluded: dict[Exclusion, list[str]]

    @property
    def complete(self) -> bool:
        """Every question the student sat is counted."""
        return all(k is Exclusion.OPTIONAL_NOT_CHOSEN for k in self.excluded)


def evaluate(q: QuestionInput) -> QuestionResult:
    def out(exclusion: Exclusion) -> QuestionResult:
        return QuestionResult(q.id, q.label, False, exclusion, None, None)

    if q.needs_review:
        return out(Exclusion.NEEDS_REVIEW)
    if q.max_marks is None:
        return out(Exclusion.NO_MAX)
    match q.attempt_status:
        case AttemptStatus.ATTEMPTED:
            if q.marks_obtained is None:
                return out(Exclusion.NO_MARK)
            return QuestionResult(q.id, q.label, True, None, q.marks_obtained, q.max_marks)
        case AttemptStatus.NOT_ATTEMPTED:
            if q.is_optional:
                return out(Exclusion.OPTIONAL_NOT_CHOSEN)
            return QuestionResult(q.id, q.label, True, None, ZERO, q.max_marks)
        case _:
            return out(Exclusion.UNKNOWN_STATUS)


def _shares(mappings: tuple[MappingInput, ...]) -> list[tuple[MappingInput, Decimal]]:
    total = sum((m.share for m in mappings), ZERO)
    if total <= 0:
        return []
    return [(m, m.share / total) for m in mappings]


def analyse(questions: list[QuestionInput], topic_module: dict[str, str | None]) -> Breakdown:
    """``topic_module`` maps each topic of the subject to its module (or None)."""
    results = [evaluate(q) for q in questions]
    overall = Tally()
    modules: dict[str | None, Tally] = defaultdict(Tally)
    topics: dict[str, Tally] = defaultdict(Tally)
    unmapped: list[str] = []
    excluded: dict[Exclusion, list[str]] = defaultdict(list)

    for q, r in zip(questions, results, strict=True):
        if not r.counted:
            assert r.exclusion is not None
            excluded[r.exclusion].append(q.label)
            if r.exclusion is not Exclusion.OPTIONAL_NOT_CHOSEN:
                for m, _ in _shares(q.mappings):
                    module = m.module_id if m.topic_id is None else topic_module.get(m.topic_id)
                    _note(modules[module].left_out, q.label)
                    if m.topic_id is not None:
                        _note(topics[m.topic_id].left_out, q.label)
            continue
        assert r.earned is not None and r.possible is not None
        overall.earned += r.earned
        overall.possible += r.possible
        overall.questions.append(q.label)
        if r.earned < r.possible:
            overall.lost_by.append((q.label, r.possible - r.earned))
        shares = _shares(q.mappings)
        if not shares:
            unmapped.append(q.label)
            continue
        for m, share in shares:
            earned, possible = r.earned * share, r.possible * share
            module = m.module_id if m.topic_id is None else topic_module.get(m.topic_id)
            groups = [modules[module]]
            if m.topic_id is not None:
                groups.append(topics[m.topic_id])
                _note(modules[module].topic_ids, m.topic_id)
            else:
                _note(modules[module].module_only, q.label)
            for g in groups:
                g.earned += earned
                g.possible += possible
                _note(g.questions, q.label)
                if earned < possible:
                    g.lost_by.append((q.label, possible - earned))
    return Breakdown(results, overall, dict(modules), dict(topics), unmapped, dict(excluded))


def _note(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def round_marks(value: Decimal | None) -> Decimal | None:
    """Marks for display: two decimal places, as stored."""
    return value.quantize(CENT) if value is not None else None


def percent(t: Tally) -> float | None:
    f = t.fraction
    return round(float(f * 100), 1) if f is not None else None
