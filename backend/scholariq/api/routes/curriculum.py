from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from scholariq.analytics.service import refresh_student
from scholariq.api.deps import PolicyDep, SessionDep, StudentDep
from scholariq.db.models import (
    Assessment,
    AssessmentResult,
    ExamBreakdown,
    Subject,
    SubjectModule,
    SubjectTopic,
    Topic,
)

router = APIRouter(tags=["curriculum"])


class TopicRef(BaseModel):
    id: str
    slug: str
    name: str
    importance: int
    module_id: str | None = None


class ModuleRef(BaseModel):
    id: str
    number: int
    name: str


class SubjectWithTopics(BaseModel):
    id: str
    slug: str
    name: str
    code: str | None
    aliases: list[str]
    is_custom: bool
    topics: list[TopicRef]
    modules: list[ModuleRef]


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
            TopicRef(
                id=topic.id,
                slug=topic.slug,
                name=topic.name,
                importance=link.importance,
                module_id=link.module_id,
            )
        )
    modules: dict[str, list[ModuleRef]] = {}
    for m in session.scalars(select(SubjectModule).order_by(SubjectModule.number)):
        modules.setdefault(m.subject_id, []).append(
            ModuleRef(id=m.id, number=m.number, name=m.name)
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
            modules=modules.get(s.id, []),
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
    # This student's exam breakdowns follow their results. Topic and module
    # mappings that do not belong to the new subject are dropped.
    for b in session.scalars(
        select(ExamBreakdown).where(
            ExamBreakdown.student_id == student.id,
            ExamBreakdown.subject_id == body.from_subject_id,
        )
    ):
        b.subject_id = target.id
        _drop_foreign_mappings(session, b, target.id)
    session.commit()
    refresh_student(session, student.id, policy)
    return {"results_moved": result.rowcount}  # type: ignore[attr-defined]


def _drop_foreign_mappings(session: SessionDep, b: ExamBreakdown, subject_id: str) -> None:
    from scholariq.exams.service import sync_evidence

    topics = set(
        session.scalars(select(SubjectTopic.topic_id).where(SubjectTopic.subject_id == subject_id))
    )
    modules = set(
        session.scalars(select(SubjectModule.id).where(SubjectModule.subject_id == subject_id))
    )
    for q in b.questions:
        q.mappings[:] = [
            m
            for m in q.mappings
            if (m.topic_id is not None and m.topic_id in topics)
            or (m.module_id is not None and m.module_id in modules)
        ]
    session.flush()
    sync_evidence(session, b)


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
    subject = _editable_custom_subject(session, student.id, subject_id, "topics")
    topics = session.scalars(select(Topic).where(Topic.id.in_(body.topic_ids))).all()
    if len(topics) != len(set(body.topic_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown topic id.")
    # Topics that stay keep their module.
    modules = {
        link.topic_id: link.module_id
        for link in session.scalars(
            select(SubjectTopic).where(SubjectTopic.subject_id == subject.id)
        )
    }
    session.query(SubjectTopic).filter(SubjectTopic.subject_id == subject.id).delete()
    order = {tid: i for i, tid in enumerate(body.topic_ids)}
    for t in topics:
        session.add(
            SubjectTopic(
                subject_id=subject.id,
                topic_id=t.id,
                position=order[t.id],
                module_id=modules.get(t.id),
            )
        )
    session.commit()
    refresh_student(session, student.id, policy)
    return next(s for s in list_subjects(session) if s.id == subject.id)


def _editable_custom_subject(
    session: SessionDep, student_id: str, subject_id: str, what: str
) -> Subject:
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found.")
    if not subject.is_custom:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Curriculum subjects are configured in the curriculum files.",
        )
    # Custom subjects are shared rows; only the sole student using one may change it.
    others = session.scalar(
        select(AssessmentResult.id)
        .join(Assessment, AssessmentResult.assessment_id == Assessment.id)
        .where(AssessmentResult.subject_id == subject.id, Assessment.student_id != student_id)
        .limit(1)
    ) or session.scalar(
        select(ExamBreakdown.id)
        .where(ExamBreakdown.subject_id == subject.id, ExamBreakdown.student_id != student_id)
        .limit(1)
    )
    if others is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Another profile also uses this subject, so its {what} cannot be changed here.",
        )
    return subject


class ModuleIn(BaseModel):
    id: str | None = None
    number: int = Field(ge=1, le=99)
    name: str = Field(min_length=1, max_length=200)
    topic_ids: list[str] = Field(default_factory=list, max_length=50)


class ModuleMapping(BaseModel):
    modules: list[ModuleIn] = Field(max_length=30)


@router.put("/curriculum/subjects/{subject_id}/modules", response_model=SubjectWithTopics)
def set_custom_modules(
    subject_id: str,
    body: ModuleMapping,
    student: StudentDep,
    session: SessionDep,
    policy: PolicyDep,
) -> SubjectWithTopics:
    """Group a custom subject's topics into modules (syllabus units). Modules
    of curriculum subjects come from the curriculum files."""
    subject = _editable_custom_subject(session, student.id, subject_id, "modules")
    numbers = [m.number for m in body.modules]
    if len(numbers) != len(set(numbers)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Module numbers must differ.")
    links = {
        link.topic_id: link
        for link in session.scalars(
            select(SubjectTopic).where(SubjectTopic.subject_id == subject.id)
        )
    }
    assigned = [t for m in body.modules for t in m.topic_ids]
    if any(t not in links for t in assigned):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A module can only contain topics of this subject; add the topic first.",
        )
    if len(assigned) != len(set(assigned)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A topic can be in only one module."
        )
    existing = {
        m.id: m
        for m in session.scalars(
            select(SubjectModule).where(SubjectModule.subject_id == subject.id)
        )
    }
    if any(m.id and m.id not in existing for m in body.modules):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown module id.")
    keep = {m.id for m in body.modules if m.id}
    for mid, module in existing.items():
        if mid not in keep:
            session.delete(module)
        else:
            # Free numbers and slugs before renumbering (unique per subject).
            module.number += 1000
            module.slug = f"tmp-{module.id}"
    for link in links.values():
        link.module_id = None
    session.flush()
    for i, m in enumerate(body.modules):
        found = existing.get(m.id) if m.id else None
        module = found or SubjectModule(subject_id=subject.id, slug=f"new-{i}", number=m.number)
        session.add(module)
        module.number, module.name = m.number, m.name.strip()
        module.slug = f"{subject.slug}.m{m.number}"[:120]
        session.flush()
        for tid in m.topic_ids:
            links[tid].module_id = module.id
    session.commit()
    refresh_student(session, student.id, policy)
    return next(s for s in list_subjects(session) if s.id == subject.id)
