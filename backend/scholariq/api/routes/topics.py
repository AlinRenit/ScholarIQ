from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from scholariq.analytics.service import (
    compute_topics,
    load_result_rows,
    refresh_student,
)
from scholariq.analytics.subjects import summarise_subjects
from scholariq.analytics.topics import EvidenceItem, describe
from scholariq.api.deps import PolicyDep, SessionDep, StudentDep
from scholariq.db.models import Topic, TopicEvidence
from scholariq.domain.enums import EvidenceKind, MasteryClass

router = APIRouter(prefix="/topics", tags=["topics"])

STUDENT_ENTERED = {EvidenceKind.SELF_REPORT, EvidenceKind.TOPIC_EXAM}


class EvidenceOut(BaseModel):
    id: str
    kind: EvidenceKind
    description: str
    observed_at: datetime
    removable: bool


class SubjectLink(BaseModel):
    id: str
    name: str
    importance: int


class TopicOut(BaseModel):
    id: str
    slug: str
    name: str
    estimated_study_minutes: int | None
    subjects: list[SubjectLink]
    classification: MasteryClass
    direct_observations: int
    reasons: list[str]
    subject_messages: list[str]
    next_action: str
    rule_version: str
    evidence: list[EvidenceOut]


@router.get("", response_model=list[TopicOut])
def list_topics(student: StudentDep, session: SessionDep, policy: PolicyDep) -> list[TopicOut]:
    rows = load_result_rows(session, student.id)
    views = compute_topics(session, student.id, policy, summarise_subjects(rows, policy))
    out = []
    for v in views:
        c = v.classification
        out.append(
            TopicOut(
                id=v.topic.id,
                slug=v.topic.slug,
                name=v.topic.name,
                estimated_study_minutes=v.topic.estimated_study_minutes,
                subjects=[SubjectLink(id=i, name=n, importance=imp) for i, n, imp in v.subjects],
                classification=c.label,
                direct_observations=c.direct_observations,
                reasons=c.reasons,
                subject_messages=c.subject_messages,
                next_action=c.next_action,
                rule_version=c.rule_version,
                evidence=[
                    EvidenceOut(
                        id=e.id,
                        kind=e.kind,
                        description=describe(
                            EvidenceItem(
                                e.id, e.kind, e.score, e.sample_size, e.observed_at, e.details
                            )
                        ),
                        observed_at=e.observed_at,
                        removable=e.kind in STUDENT_ENTERED,
                    )
                    for e in v.evidence
                ],
            )
        )
    order = {
        MasteryClass.NEEDS_ATTENTION: 0,
        MasteryClass.DEVELOPING: 1,
        MasteryClass.INSUFFICIENT_EVIDENCE: 2,
        MasteryClass.STRONG: 3,
    }
    return sorted(
        out, key=lambda t: (t.subjects[0].name if t.subjects else "", order[t.classification])
    )


class NewEvidence(BaseModel):
    kind: Literal["self_report", "topic_exam"]
    # self_report: how confident you feel, 1 (not at all) .. 5 (very).
    rating: Annotated[int, Field(ge=1, le=5)] | None = None
    # topic_exam: a test or quiz that covered only this topic.
    obtained: Annotated[Decimal, Field(ge=0, max_digits=7, decimal_places=2)] | None = None
    maximum: Annotated[Decimal, Field(gt=0, max_digits=7, decimal_places=2)] | None = None
    questions: Annotated[int, Field(ge=1, le=200)] = 1

    @model_validator(mode="after")
    def _shape(self) -> NewEvidence:
        if self.kind == "self_report" and self.rating is None:
            raise ValueError("a self-report needs a rating from 1 to 5")
        if self.kind == "topic_exam":
            if self.obtained is None or self.maximum is None:
                raise ValueError("a topic test needs marks obtained and maximum marks")
            if self.obtained > self.maximum:
                raise ValueError("marks obtained exceed maximum marks")
        return self


@router.post("/{topic_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence(
    topic_id: str, body: NewEvidence, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> dict[str, str]:
    if session.get(Topic, topic_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found.")
    if body.kind == "self_report":
        assert body.rating is not None
        ev = TopicEvidence(
            student_id=student.id,
            topic_id=topic_id,
            kind=EvidenceKind.SELF_REPORT,
            score=(Decimal(body.rating - 1) / 4).quantize(Decimal("0.0001")),
            sample_size=1,
            details={"rating": body.rating},
        )
    else:
        assert body.obtained is not None and body.maximum is not None
        ev = TopicEvidence(
            student_id=student.id,
            topic_id=topic_id,
            kind=EvidenceKind.TOPIC_EXAM,
            score=(body.obtained / body.maximum).quantize(Decimal("0.0001")),
            sample_size=body.questions,
            details={
                "obtained": str(body.obtained),
                "maximum": str(body.maximum),
                "questions": body.questions,
            },
        )
    session.add(ev)
    session.commit()
    refresh_student(session, student.id, policy)
    return {"id": ev.id}


@router.delete("/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    evidence_id: str, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> None:
    ev = session.get(TopicEvidence, evidence_id)
    if ev is None or ev.student_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found.")
    if ev.kind not in STUDENT_ENTERED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This evidence comes from your results, quizzes or exam breakdowns; "
            "change those instead.",
        )
    session.delete(ev)
    session.commit()
    refresh_student(session, student.id, policy)
