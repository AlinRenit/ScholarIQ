from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from scholariq.analytics.service import refresh_student
from scholariq.api.deps import PolicyDep, SessionDep, StudentDep
from scholariq.db.models import Assessment, AssessmentResult, Subject, SubjectTopic, Topic

router = APIRouter(tags=["curriculum"])


class TopicRef(BaseModel):
    id: str
    slug: str
    name: str
    importance: int


class SubjectWithTopics(BaseModel):
    id: str
    slug: str
    name: str
    code: str | None
    aliases: list[str]
    is_custom: bool
    topics: list[TopicRef]


@router.get("/curriculum/subjects", response_model=list[SubjectWithTopics])
def list_subjects(session: SessionDep) -> list[SubjectWithTopics]:
    subjects = session.scalars(select(Subject).order_by(Subject.is_custom, Subject.name)).all()
    links = session.execute(
        select(SubjectTopic, Topic)
        .join(Topic, SubjectTopic.topic_id == Topic.id)
        .order_by(SubjectTopic.position)
    ).all()
    by_subject: dict[str, list[TopicRef]] = {}
    for link, topic in links:
        by_subject.setdefault(link.subject_id, []).append(
            TopicRef(id=topic.id, slug=topic.slug, name=topic.name, importance=link.importance)
        )
    return [
        SubjectWithTopics(
            id=s.id,
            slug=s.slug,
            name=s.name,
            code=s.code,
            aliases=s.aliases,
            is_custom=s.is_custom,
            topics=by_subject.get(s.id, []),
        )
        for s in subjects
    ]


class Remap(BaseModel):
    from_subject_id: str
    to_subject_id: str


@router.post("/academics/subjects/remap")
def remap_subject(
    body: Remap, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> dict[str, int]:
    """Move this student's results from one subject to another (e.g. a custom
    subject to the matching curriculum subject). Other students are unaffected."""
    target = session.get(Subject, body.to_subject_id)
    if target is None or session.get(Subject, body.from_subject_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found.")
    mine = select(Assessment.id).where(Assessment.student_id == student.id)
    result = session.execute(
        update(AssessmentResult)
        .where(
            AssessmentResult.subject_id == body.from_subject_id,
            AssessmentResult.assessment_id.in_(mine),
        )
        .values(subject_id=target.id)
    )
    session.commit()
    refresh_student(session, student.id, policy)
    return {"results_moved": result.rowcount}  # type: ignore[attr-defined]


class TopicMapping(BaseModel):
    topic_ids: list[str] = Field(max_length=50)


@router.put("/curriculum/subjects/{subject_id}/topics", response_model=SubjectWithTopics)
def set_custom_topics(
    subject_id: str,
    body: TopicMapping,
    student: StudentDep,
    session: SessionDep,
    policy: PolicyDep,
) -> SubjectWithTopics:
    """Choose which curriculum topics a custom subject covers. Curriculum
    subjects are configured in content/curriculum and cannot be changed here."""
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found.")
    if not subject.is_custom:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Curriculum subjects are configured in the curriculum files.",
        )
    # Custom subjects are shared rows; only the sole student using one may remap it.
    others = session.scalar(
        select(AssessmentResult.id)
        .join(Assessment, AssessmentResult.assessment_id == Assessment.id)
        .where(AssessmentResult.subject_id == subject.id, Assessment.student_id != student.id)
        .limit(1)
    )
    if others is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another profile also uses this subject, so its topics cannot be changed here.",
        )
    topics = session.scalars(select(Topic).where(Topic.id.in_(body.topic_ids))).all()
    if len(topics) != len(set(body.topic_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown topic id.")
    session.query(SubjectTopic).filter(SubjectTopic.subject_id == subject.id).delete()
    order = {tid: i for i, tid in enumerate(body.topic_ids)}
    for t in topics:
        session.add(SubjectTopic(subject_id=subject.id, topic_id=t.id, position=order[t.id]))
    session.commit()
    refresh_student(session, student.id, policy)
    return next(s for s in list_subjects(session) if s.id == subject.id)
