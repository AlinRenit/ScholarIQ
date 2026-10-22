from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from scholariq.analytics.service import load_result_rows, topic_links
from scholariq.analytics.subjects import (
    Aggregate,
    Score,
    credit_weighted_percentage,
    data_gaps,
    gpa,
    grade_distribution,
    latest_per_subject_component,
    marks_percentage,
    semester_trend,
    spread,
    summarise_semesters,
    summarise_subjects,
)
from scholariq.api.deps import PolicyDep, SessionDep, StudentDep
from scholariq.db.models import Subject

router = APIRouter(prefix="/analytics", tags=["analytics"])

METHODOLOGY = [
    "A score is marks obtained divided by maximum marks. If there are no usable marks and you "
    "confirmed a grading scale, grade points divided by the scale maximum are used instead, and "
    "labelled as such.",
    "Scores on different bases are never averaged together; GPA is only calculated within one "
    "grading scale and only when every graded result has credits.",
    "Absent, withheld and missing results have no score and are never counted as zero.",
    "A subject's current score is its latest sitting. Theory and lab components are combined by "
    "total marks only when every component has marks and maximum marks.",
    "Semester figures use each subject's latest sitting in that semester.",
    "Subject bands describe exam performance only. They are not evidence of which topics you "
    "understand.",
]


class ScoreOut(BaseModel):
    percent: float
    basis: str


def _score(s: Score | None) -> ScoreOut | None:
    return ScoreOut(percent=s.percent, basis=s.basis.value) if s else None


class AggregateOut(BaseModel):
    value: float | None
    basis: str
    counted: int
    excluded: int
    reason: str | None


def _agg(a: Aggregate) -> AggregateOut:
    return AggregateOut(**a.__dict__)


class SittingOut(BaseModel):
    semester: int | None
    exam_type: str
    score: ScoreOut | None
    note: str | None
    components: list[str]


class SubjectOut(BaseModel):
    id: str
    name: str
    is_custom: bool
    mapped_topics: int
    band: str
    latest: ScoreOut | None
    latest_note: str | None
    best: ScoreOut | None
    credits: float | None
    sittings: list[SittingOut]
    notes: list[str]


class SemesterOut(BaseModel):
    semester: int | None
    results: int
    marks_percentage: AggregateOut
    credit_weighted_percentage: AggregateOut
    gpa: AggregateOut


class Overview(BaseModel):
    policy: dict[str, Any]
    counts: dict[str, int]
    overall: dict[str, AggregateOut]
    semesters: list[SemesterOut]
    trend: dict[str, Any]
    spread_points: float | None
    subjects: list[SubjectOut]
    grade_distribution: dict[str, int]
    data_gaps: list[str]
    methodology: list[str]


@router.get("/overview", response_model=Overview)
def overview(student: StudentDep, session: SessionDep, policy: PolicyDep) -> Overview:
    rows = load_result_rows(session, student.id)
    subjects = summarise_subjects(rows, policy)
    semesters = summarise_semesters(rows)
    latest = latest_per_subject_component(rows)
    trend = semester_trend(semesters, policy)
    links = topic_links(session, {s.subject_id for s in subjects})
    custom = {
        sid
        for (sid,) in session.execute(
            select(Subject.id).where(
                Subject.id.in_([s.subject_id for s in subjects]), Subject.is_custom.is_(True)
            )
        )
    }
    gaps = data_gaps(rows)
    unmapped = [s.subject_name for s in subjects if not links.get(s.subject_id)]
    if unmapped:
        gaps.append(
            "No topic mapping for: " + ", ".join(unmapped) + ". Map them to a curriculum subject "
            "or add topics so they appear in Topics."
        )
    return Overview(
        policy={
            "version": policy.version,
            "subject_bands": policy.subject_bands.model_dump(),
            "trend_min_change_points": policy.trends.min_change_points,
        },
        counts={
            "subjects": len(subjects),
            "results": len(rows),
            "assessments": len({r.assessment_id for r in rows}),
            "semesters": len({r.semester for r in rows if r.semester is not None}),
        },
        overall={
            "marks_percentage": _agg(marks_percentage(latest)),
            "credit_weighted_percentage": _agg(credit_weighted_percentage(latest)),
            "gpa": _agg(gpa(latest)),
        },
        semesters=[
            SemesterOut(
                semester=s.semester,
                results=s.results,
                marks_percentage=_agg(s.marks_percentage),
                credit_weighted_percentage=_agg(s.credit_weighted_percentage),
                gpa=_agg(s.gpa),
            )
            for s in semesters
        ],
        trend={
            "direction": trend.direction.value,
            "change_points": trend.change_points,
            "explanation": trend.explanation,
        },
        spread_points=spread(subjects),
        subjects=[
            SubjectOut(
                id=s.subject_id,
                name=s.subject_name,
                is_custom=s.subject_id in custom,
                mapped_topics=len(links.get(s.subject_id, [])),
                band=s.band.value,
                latest=_score(s.latest),
                latest_note=s.latest_note,
                best=_score(s.best),
                credits=float(s.credits) if s.credits is not None else None,
                sittings=[
                    SittingOut(
                        semester=x.semester,
                        exam_type=x.exam_type,
                        score=_score(x.score),
                        note=x.note,
                        components=x.components,
                    )
                    for x in s.sittings
                ],
                notes=s.notes,
            )
            for s in subjects
        ],
        grade_distribution=grade_distribution(rows),
        data_gaps=gaps,
        methodology=METHODOLOGY,
    )
