"""Subject- and semester-level performance analysis.

Pure functions over confirmed results; no database access. Every number says
what it is based on, and anything that cannot be computed validly is returned
as ``None`` with a reason instead of an estimate.

Conversion policy
-----------------
* A result's *score* is a fraction of its maximum:
  - ``marks``: marks obtained / maximum marks, when both are known;
  - ``grade_points``: grade points / the confirmed scale's maximum, when there
    are no usable marks and the student confirmed a grading scale.
* Scores on different bases are never averaged together. Averages are
  computed per basis, and GPA only within a single grading scale.
* Absent, withheld and missing results have no score. They are reported, not
  counted as zero.
* A subject's current score is its latest sitting. Components (theory, lab) of
  one sitting are combined by total marks (sum obtained / sum maximum) only
  when every component has marks and maximum marks.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from scholariq.analytics.policy import Policy
from scholariq.domain.enums import ResultStatus

Q = Decimal("0.0001")


class Basis(StrEnum):
    MARKS = "marks"
    GRADE_POINTS = "grade_points"


class Band(StrEnum):
    STRONG = "strong"
    DEVELOPING = "developing"
    NEEDS_ATTENTION = "needs_attention"
    NO_SCORE = "no_score"


class Trend(StrEnum):
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    INSUFFICIENT = "insufficient_data"


@dataclass(frozen=True)
class ResultRow:
    result_id: str
    assessment_id: str
    sequence: int  # chronological order of sittings (import order)
    subject_id: str
    subject_name: str
    semester: int | None
    exam_type: str
    component: str
    status: ResultStatus
    attempt_number: int
    obtained: Decimal | None
    maximum: Decimal | None
    grade: str | None
    grade_points: Decimal | None
    credits: Decimal | None
    scale_id: str | None
    scale_max: Decimal | None


@dataclass(frozen=True)
class Score:
    value: Decimal  # fraction 0..1
    basis: Basis
    scale_id: str | None = None

    @property
    def percent(self) -> float:
        return float((self.value * 100).quantize(Decimal("0.1")))


def result_score(r: ResultRow) -> Score | None:
    if r.status is not ResultStatus.PRESENT:
        return None
    if r.obtained is not None and r.maximum is not None and r.maximum > 0:
        return Score((r.obtained / r.maximum).quantize(Q), Basis.MARKS)
    if r.grade_points is not None and r.scale_max:
        return Score((r.grade_points / r.scale_max).quantize(Q), Basis.GRADE_POINTS, r.scale_id)
    return None


def _sitting_key(r: ResultRow) -> tuple[int, int]:
    return (r.semester if r.semester is not None else -1, r.sequence)


def combine(rows: list[ResultRow]) -> tuple[Score | None, str | None]:
    """Score for one sitting of a subject (possibly several components)."""
    if len(rows) == 1:
        score = result_score(rows[0])
        return score, None if score else _no_score_reason(rows[0])
    if all(r.status is ResultStatus.PRESENT and r.obtained is not None and r.maximum for r in rows):
        total = sum((r.obtained for r in rows if r.obtained is not None), Decimal(0))
        maximum = sum((r.maximum for r in rows if r.maximum is not None), Decimal(0))
        return Score((total / maximum).quantize(Q), Basis.MARKS), None
    scores = [result_score(r) for r in rows]
    if all(s is not None for s in scores):
        bases = {(s.basis, s.scale_id) for s in scores if s}
        if len(bases) == 1:
            values = [s.value for s in scores if s]
            mean = (sum(values, Decimal(0)) / len(values)).quantize(Q)
            only = next(iter(bases))
            return Score(mean, only[0], only[1]), "Components averaged by grade points."
    return None, "Components cannot be combined (missing marks or different bases)."


def _no_score_reason(r: ResultRow) -> str:
    if r.status is not ResultStatus.PRESENT:
        return f"Marked {r.status.value} in this sitting."
    if r.obtained is not None and r.maximum is None:
        return "Maximum marks unknown."
    if r.grade and r.grade_points is None:
        return "Grade not converted: no grading scale confirmed."
    return "No marks or grade points recorded."


def band_for(score: Score | None, policy: Policy) -> Band:
    if score is None:
        return Band.NO_SCORE
    b = policy.subject_bands
    if score.value >= Decimal(str(b.strong_at)):
        return Band.STRONG
    if score.value < Decimal(str(b.attention_below)):
        return Band.NEEDS_ATTENTION
    return Band.DEVELOPING


@dataclass
class SittingOut:
    assessment_id: str
    semester: int | None
    exam_type: str
    score: Score | None
    note: str | None
    components: list[str]


@dataclass
class SubjectSummary:
    subject_id: str
    subject_name: str
    sittings: list[SittingOut]
    latest: Score | None
    latest_note: str | None
    best: Score | None
    band: Band
    credits: Decimal | None
    notes: list[str] = field(default_factory=list)


def summarise_subjects(rows: list[ResultRow], policy: Policy) -> list[SubjectSummary]:
    by_subject: dict[str, list[ResultRow]] = defaultdict(list)
    for r in rows:
        by_subject[r.subject_id].append(r)
    out = []
    for subject_rows in by_subject.values():
        sittings: dict[str, list[ResultRow]] = defaultdict(list)
        for r in subject_rows:
            sittings[r.assessment_id].append(r)
        ordered = sorted(sittings.values(), key=lambda rs: _sitting_key(rs[0]))
        sitting_out = []
        for rs in ordered:
            score, note = combine(rs)
            sitting_out.append(
                SittingOut(
                    rs[0].assessment_id,
                    rs[0].semester,
                    rs[0].exam_type,
                    score,
                    note,
                    sorted({r.component for r in rs}),
                )
            )
        latest = sitting_out[-1]
        same_basis = [
            s.score
            for s in sitting_out
            if s.score
            and latest.score
            and (s.score.basis, s.score.scale_id) == (latest.score.basis, latest.score.scale_id)
        ]
        best = max(same_basis, key=lambda s: s.value) if same_basis else None
        notes = []
        if len(sitting_out) > 1:
            notes.append(f"{len(sitting_out)} sittings recorded; the latest one is used.")
            if latest.score and best and best.value > latest.score.value:
                notes.append("An earlier sitting scored higher than the latest one.")
        credits = next((r.credits for r in reversed(ordered[-1]) if r.credits is not None), None)
        first = subject_rows[0]
        out.append(
            SubjectSummary(
                subject_id=first.subject_id,
                subject_name=first.subject_name,
                sittings=sitting_out,
                latest=latest.score,
                latest_note=latest.note,
                best=best,
                band=band_for(latest.score, policy),
                credits=credits,
                notes=notes,
            )
        )
    return sorted(out, key=lambda s: s.subject_name.lower())


@dataclass
class Aggregate:
    """An average that is either computable from the data, or explained."""

    value: float | None
    basis: str
    counted: int
    excluded: int
    reason: str | None = None


@dataclass
class SemesterSummary:
    semester: int | None
    results: int
    marks_percentage: Aggregate
    credit_weighted_percentage: Aggregate
    gpa: Aggregate


def latest_per_subject_component(rows: list[ResultRow]) -> list[ResultRow]:
    latest: dict[tuple[str, str], ResultRow] = {}
    for r in sorted(rows, key=_sitting_key):
        latest[(r.subject_id, r.component)] = r
    return list(latest.values())


def marks_percentage(rows: list[ResultRow]) -> Aggregate:
    usable = [r for r in rows if (s := result_score(r)) is not None and s.basis is Basis.MARKS]
    excluded = len(rows) - len(usable)
    if not usable:
        return Aggregate(None, "marks", 0, excluded, "No results with both marks and maximum.")
    total = sum((r.obtained or Decimal(0) for r in usable), Decimal(0))
    maximum = sum((r.maximum or Decimal(0) for r in usable), Decimal(0))
    value = float((total / maximum * 100).quantize(Decimal("0.1")))
    reason = f"{excluded} result(s) without usable marks are not included." if excluded else None
    return Aggregate(value, "marks", len(usable), excluded, reason)


def credit_weighted_percentage(rows: list[ResultRow]) -> Aggregate:
    scored = [(r, result_score(r)) for r in rows]
    usable = [(r, s) for r, s in scored if s and s.basis is Basis.MARKS]
    if not usable:
        return Aggregate(None, "marks", 0, len(rows), "No results with both marks and maximum.")
    if any(r.credits is None for r, _ in usable):
        return Aggregate(
            None,
            "marks",
            0,
            len(rows),
            "Credits are missing for some results, so no credit weighting.",
        )
    total_credits = sum((r.credits or Decimal(0) for r, _ in usable), Decimal(0))
    if total_credits == 0:
        return Aggregate(None, "marks", 0, len(rows), "All credits are zero.")
    weighted = sum((s.value * (r.credits or Decimal(0)) for r, s in usable), Decimal(0))
    value = float((weighted / total_credits * 100).quantize(Decimal("0.1")))
    excluded = len(rows) - len(usable)
    reason = f"{excluded} result(s) without usable marks are not included." if excluded else None
    return Aggregate(value, "marks", len(usable), excluded, reason)


def gpa(rows: list[ResultRow]) -> Aggregate:
    graded = [r for r in rows if r.grade or r.grade_points is not None]
    if not graded:
        return Aggregate(None, "grade_points", 0, len(rows), "No grades recorded.")
    if any(r.grade_points is None for r in graded):
        return Aggregate(
            None,
            "grade_points",
            0,
            len(rows),
            "Some grades have no grade points; confirm a grading scale.",
        )
    if len({r.scale_id for r in graded}) > 1:
        return Aggregate(
            None, "grade_points", 0, len(rows), "Grades come from different grading scales."
        )
    if any(r.credits is None for r in graded):
        return Aggregate(
            None, "grade_points", 0, len(rows), "Credits are missing for some graded results."
        )
    credits = sum((r.credits or Decimal(0) for r in graded), Decimal(0))
    if credits == 0:
        return Aggregate(None, "grade_points", 0, len(rows), "All credits are zero.")
    points = sum(
        ((r.grade_points or Decimal(0)) * (r.credits or Decimal(0)) for r in graded), Decimal(0)
    )
    value = float((points / credits).quantize(Decimal("0.01")))
    return Aggregate(value, "grade_points", len(graded), len(rows) - len(graded))


def summarise_semesters(rows: list[ResultRow]) -> list[SemesterSummary]:
    by_sem: dict[int | None, list[ResultRow]] = defaultdict(list)
    for r in rows:
        by_sem[r.semester].append(r)
    out = []
    for sem in sorted(by_sem, key=lambda s: (s is None, s or 0)):
        latest = latest_per_subject_component(by_sem[sem])
        out.append(
            SemesterSummary(
                semester=sem,
                results=len(latest),
                marks_percentage=marks_percentage(latest),
                credit_weighted_percentage=credit_weighted_percentage(latest),
                gpa=gpa(latest),
            )
        )
    return out


@dataclass
class TrendOut:
    direction: Trend
    change_points: float | None
    explanation: str


def semester_trend(semesters: list[SemesterSummary], policy: Policy) -> TrendOut:
    points = [
        (s.semester, s.marks_percentage.value)
        for s in semesters
        if s.semester is not None and s.marks_percentage.value is not None
    ]
    if len(points) < 2:
        return TrendOut(
            Trend.INSUFFICIENT, None, "At least two semesters with marks are needed to see a trend."
        )
    (s1, v1), (s2, v2) = points[-2], points[-1]
    assert v1 is not None and v2 is not None
    change = round(v2 - v1, 1)
    threshold = policy.trends.min_change_points
    if change >= threshold:
        direction = Trend.IMPROVING
    elif change <= -threshold:
        direction = Trend.DECLINING
    else:
        direction = Trend.STABLE
    return TrendOut(
        direction,
        change,
        f"Semester {s2} vs semester {s1}: {change:+.1f} percentage points "
        f"(a change of {threshold:g} or more counts as a trend).",
    )


def spread(subjects: list[SubjectSummary]) -> float | None:
    """Standard deviation of current marks-based subject scores, in points."""
    values = [
        float(s.latest.value) * 100 for s in subjects if s.latest and s.latest.basis is Basis.MARKS
    ]
    return round(statistics.pstdev(values), 1) if len(values) >= 3 else None


def grade_distribution(rows: list[ResultRow]) -> dict[str, int]:
    latest = latest_per_subject_component(rows)
    return dict(sorted(Counter(r.grade for r in latest if r.grade).items()))


def data_gaps(rows: list[ResultRow]) -> list[str]:
    gaps = []
    no_max = sum(1 for r in rows if r.obtained is not None and r.maximum is None)
    if no_max:
        gaps.append(f"{no_max} result(s) have marks but no maximum marks, so no percentage.")
    unconverted = sum(1 for r in rows if r.grade and r.grade_points is None and r.obtained is None)
    if unconverted:
        gaps.append(f"{unconverted} result(s) have only a grade with no confirmed grading scale.")
    if any(r.credits is not None for r in rows):
        no_credits = sum(1 for r in rows if r.credits is None)
        if no_credits:
            gaps.append(f"{no_credits} result(s) have no credits, so credit weighting is limited.")
    no_sem = sum(1 for r in rows if r.semester is None)
    if no_sem:
        gaps.append(f"{no_sem} result(s) have no semester, so they are left out of trends.")
    not_scored = sum(1 for r in rows if r.status is not ResultStatus.PRESENT)
    if not_scored:
        gaps.append(f"{not_scored} result(s) are absent, withheld or missing and have no score.")
    return gaps
