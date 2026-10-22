"""Analytics and classification checked against hand-calculated values."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from scholariq.analytics.policy import DEFAULT_POLICY, Policy
from scholariq.analytics.subjects import (
    Band,
    Basis,
    ResultRow,
    Trend,
    credit_weighted_percentage,
    data_gaps,
    gpa,
    marks_percentage,
    semester_trend,
    summarise_semesters,
    summarise_subjects,
)
from scholariq.analytics.topics import EvidenceItem, SubjectSignal, _weight, classify, describe
from scholariq.domain.enums import EvidenceKind, MasteryClass, ResultStatus

P = ResultStatus.PRESENT


def row(
    rid: str, assessment: str, seq: int, subject: str, sem: int | None, obtained: str | None,
    maximum: str | None, credits: str | None = None, status: ResultStatus = P,
    component: str = "combined", grade: str | None = None, gp: str | None = None,
    scale: str | None = None,
) -> ResultRow:  # fmt: skip
    return ResultRow(
        result_id=rid,
        assessment_id=assessment,
        sequence=seq,
        subject_id=subject,
        subject_name=subject.upper(),
        semester=sem,
        exam_type="regular",
        component=component,
        status=status,
        attempt_number=1,
        obtained=D(obtained) if obtained else None,
        maximum=D(maximum) if maximum else None,
        grade=grade,
        grade_points=D(gp) if gp else None,
        credits=D(credits) if credits else None,
        scale_id=scale,
        scale_max=D(10) if scale else None,
    )


SEM3 = [
    row("1", "a1", 0, "ds", 3, "78", "100", "4"),
    row("2", "a1", 0, "os", 3, "52", "100", "4"),
    row("3", "a1", 0, "dbms", 3, "45", "100", "3"),
    row("4", "a1", 0, "cn", 3, None, "100", "3", status=ResultStatus.ABSENT),
    row("5", "a1", 0, "ds", 3, "44", "50", "2", component="lab"),
    row("6", "a1", 0, "dm", 3, "91", "100", "4"),
]
SEM4 = [
    row("7", "a2", 1, "os", 4, "61", "100", "4"),
    row("8", "a2", 1, "cn", 4, "64", "100", "3"),
]


def test_semester_marks_percentage_excludes_absent() -> None:
    agg = marks_percentage(SEM3)
    # (78 + 52 + 45 + 44 + 91) / (100 * 4 + 50) = 310 / 450
    assert agg.value == 68.9
    assert (agg.counted, agg.excluded) == (5, 1)


def test_credit_weighted_percentage() -> None:
    # (0.78*4 + 0.52*4 + 0.45*3 + 0.88*2 + 0.91*4) / 17 = 11.95 / 17
    assert credit_weighted_percentage(SEM3).value == 70.3


def test_credit_weighting_refused_when_credits_missing() -> None:
    rows = [row("1", "a", 0, "x", 1, "50", "100", "4"), row("2", "a", 0, "y", 1, "60", "100")]
    agg = credit_weighted_percentage(rows)
    assert agg.value is None and "Credits are missing" in (agg.reason or "")


def test_different_maximum_marks_are_respected() -> None:
    rows = [row("1", "a", 0, "x", 1, "20", "25"), row("2", "a", 0, "y", 1, "60", "150")]
    # 80 / 175, not the mean of 80% and 40%
    assert marks_percentage(rows).value == 45.7


def test_subject_summary_combines_components_and_bands() -> None:
    subjects = {s.subject_id: s for s in summarise_subjects(SEM3 + SEM4, DEFAULT_POLICY)}
    ds = subjects["ds"]
    assert ds.latest is not None and ds.latest.basis is Basis.MARKS
    assert ds.latest.percent == 81.3  # (78 + 44) / 150
    assert ds.band is Band.STRONG
    assert subjects["dbms"].band is Band.NEEDS_ATTENTION
    os_ = subjects["os"]
    assert len(os_.sittings) == 2 and os_.latest and os_.latest.percent == 61.0
    assert os_.band is Band.DEVELOPING
    # CN: absent in sem 3, scored in sem 4 -> latest is the sem 4 score.
    assert subjects["cn"].latest and subjects["cn"].latest.percent == 64.0


def test_absent_subject_has_no_score_not_zero() -> None:
    cn = summarise_subjects(SEM3, DEFAULT_POLICY)[0]
    assert cn.subject_id == "cn"
    assert cn.latest is None and cn.band is Band.NO_SCORE
    assert cn.latest_note == "Marked absent in this sitting."


def test_trend_between_semesters() -> None:
    semesters = summarise_semesters(SEM3 + SEM4)
    assert [s.marks_percentage.value for s in semesters] == [68.9, 62.5]
    trend = semester_trend(semesters, DEFAULT_POLICY)
    assert trend.direction is Trend.DECLINING and trend.change_points == -6.4


def test_trend_needs_two_semesters() -> None:
    assert semester_trend(summarise_semesters(SEM3), DEFAULT_POLICY).direction is (
        Trend.INSUFFICIENT
    )


def test_gpa_only_with_points_credits_and_one_scale() -> None:
    graded = [
        row("1", "a", 0, "x", 1, None, None, "4", grade="B+", gp="7", scale="s1"),
        row("2", "a", 0, "y", 1, None, None, "3", grade="A", gp="8", scale="s1"),
        row("3", "a", 0, "z", 1, None, None, "3", grade="F", gp="0", scale="s1"),
    ]
    assert gpa(graded).value == 5.2  # (28 + 24 + 0) / 10
    mixed = [*graded[:2], row("4", "a", 0, "w", 1, None, None, "3", grade="A", gp="4", scale="s2")]
    assert gpa(mixed).value is None and "different grading scales" in (gpa(mixed).reason or "")
    unconverted = [*graded[:2], row("5", "a", 0, "v", 1, None, None, "3", grade="O")]
    assert gpa(unconverted).value is None


def test_grade_points_basis_is_labelled_and_not_mixed_with_marks() -> None:
    rows = [
        row("1", "a", 0, "x", 1, "70", "100"),
        row("2", "a", 0, "y", 1, None, None, grade="A", gp="8", scale="s1"),
    ]
    subjects = {s.subject_id: s for s in summarise_subjects(rows, DEFAULT_POLICY)}
    assert subjects["y"].latest and subjects["y"].latest.basis is Basis.GRADE_POINTS
    # The marks average ignores the grade-point result instead of blending it in.
    agg = marks_percentage(rows)
    assert agg.value == 70.0 and agg.excluded == 1


def test_data_gaps_reported() -> None:
    rows = [
        row("1", "a", 0, "x", None, "70", None, "4"),
        row("2", "a", 0, "y", 1, None, None, grade="B"),
        row("3", "a", 0, "z", 1, None, None, status=ResultStatus.MISSING),
    ]
    gaps = " ".join(data_gaps(rows))
    assert "no maximum marks" in gaps
    assert "only a grade" in gaps
    assert "no credits" in gaps
    assert "no semester" in gaps
    assert "absent, withheld or missing" in gaps


# --- Topic classification -------------------------------------------------- #

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def ev(
    kind: EvidenceKind, score: str | None, n: int = 1, days_ago: int = 0, **details: object
) -> EvidenceItem:  # noqa: E501
    return EvidenceItem(f"{kind}-{score}-{n}-{days_ago}", kind, D(score) if score else None, n,
                        NOW - timedelta(days=days_ago), dict(details))  # fmt: skip


DBMS_SIGNAL = SubjectSignal(
    "Database Management Systems",
    Band.NEEDS_ATTENTION,
    ("Relational model", "SQL", "Functional dependencies", "Normalization", "Transactions"),
)


def test_subject_score_alone_is_insufficient_with_requested_message() -> None:
    c = classify(
        "Normalization",
        [ev(EvidenceKind.SUBJECT_SCORE_PRIOR, "0.45")],
        [DBMS_SIGNAL],
        DEFAULT_POLICY,
        NOW,
    )
    assert c.label is MasteryClass.INSUFFICIENT_EVIDENCE
    assert c.subject_messages == [
        "Your Database Management Systems score suggests this subject may need attention. "
        "We need topic-level practice results to determine whether Normalization, "
        "Relational model or SQL is the main difficulty."
    ]


def test_topic_evidence_takes_precedence_over_subject_mark() -> None:
    items = [
        ev(EvidenceKind.SUBJECT_SCORE_PRIOR, "0.45"),
        ev(EvidenceKind.DIAGNOSTIC, "0.9", n=6, correct=5, total=6),  # weighted 5.4 of 6
    ]
    c = classify("Normalization", items, [DBMS_SIGNAL], DEFAULT_POLICY, NOW)
    # (0.45*1 + 0.9*6) / 7 = 0.836 -> strong
    assert c.label is MasteryClass.STRONG
    assert any("Topic-level evidence takes precedence" in r for r in c.reasons)
    assert any("5 of 6 correct" in r for r in c.reasons)


@pytest.mark.parametrize(
    ("score", "label"),
    [
        ("0.4", MasteryClass.NEEDS_ATTENTION),
        ("0.6", MasteryClass.DEVELOPING),
        ("0.8", MasteryClass.STRONG),
    ],
)
def test_thresholds(score: str, label: MasteryClass) -> None:
    c = classify("T", [ev(EvidenceKind.DIAGNOSTIC, score, n=5)], [], DEFAULT_POLICY, NOW)
    assert c.label is label


def test_self_report_alone_never_classifies() -> None:
    c = classify("T", [ev(EvidenceKind.SELF_REPORT, "1", rating=5)], [], DEFAULT_POLICY, NOW)
    assert c.label is MasteryClass.INSUFFICIENT_EVIDENCE
    assert any("self-assessment" in r for r in c.reasons)


def test_new_evidence_changes_classification() -> None:
    old = [ev(EvidenceKind.DIAGNOSTIC, "0.3", n=5, days_ago=360)]
    assert classify("T", old, [], DEFAULT_POLICY, NOW).label is MasteryClass.NEEDS_ATTENTION
    # Recent strong results outweigh year-old weak ones (half-life 180 days).
    new = [*old, ev(EvidenceKind.DIAGNOSTIC, "0.9", n=5)]
    # weights: old 5 * 0.25 = 1.25, new 5 -> (0.375 + 4.5) / 6.25 = 0.78
    assert classify("T", new, [], DEFAULT_POLICY, NOW).label is MasteryClass.STRONG


def test_recency_half_life() -> None:
    item = ev(EvidenceKind.DIAGNOSTIC, "1", n=1, days_ago=180)
    assert _weight(item, DEFAULT_POLICY, NOW) == pytest.approx(0.5)


def test_thresholds_are_configurable() -> None:
    strict = Policy.model_validate({"topics": {"min_direct_observations": 10}})
    c = classify("T", [ev(EvidenceKind.DIAGNOSTIC, "0.9", n=6)], [], strict, NOW)
    assert c.label is MasteryClass.INSUFFICIENT_EVIDENCE


def test_boundary_is_flagged() -> None:
    c = classify("T", [ev(EvidenceKind.DIAGNOSTIC, "0.76", n=5)], [], DEFAULT_POLICY, NOW)
    assert any("close to a boundary" in r for r in c.reasons)


def test_evidence_descriptions_are_readable() -> None:
    now = datetime.now(UTC)
    exam = EvidenceItem("a", EvidenceKind.TOPIC_EXAM, D("0.4"), 6, now,
                        {"obtained": "4.00", "maximum": "10", "questions": 6})  # fmt: skip
    prior = EvidenceItem("b", EvidenceKind.SUBJECT_SCORE_PRIOR, D("0.64"), 1, now, {})
    rating = EvidenceItem("c", EvidenceKind.SELF_REPORT, D("0.25"), 1, now, {"rating": 2})
    assert describe(exam) == "Topic test: 4 of 10 marks (40%), 6 question(s)"
    assert describe(prior).startswith("Subject result: 64% for the whole subject")
    assert describe(rating) == "Self-assessment: confidence 2 of 5"
