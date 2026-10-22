"""Build, store and update a student's study plan."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from scholariq.analytics.policy import Policy
from scholariq.analytics.service import refresh_student
from scholariq.analytics.subjects import Band
from scholariq.db.models import (
    Concept,
    ConceptRelationship,
    StudyPlan,
    StudyPlanItem,
    Topic,
)
from scholariq.domain.enums import (
    EvidenceKind,
    MasteryClass,
    RelationshipKind,
    StudyPlanItemStatus,
)
from scholariq.planning.plan import FORMULA_VERSION, TopicInput, build_plan

NEXT_STEP = {
    MasteryClass.NEEDS_ATTENTION: (
        "Work through it with the tutor step by step, then take a diagnostic quiz."
    ),
    MasteryClass.INSUFFICIENT_EVIDENCE: "Take a diagnostic quiz to find out where you stand.",
    MasteryClass.DEVELOPING: "Take a diagnostic quiz and review the questions you miss.",
    MasteryClass.STRONG: "Optional: take a quiz to confirm it is still solid.",
}


class NotFound(LookupError):
    pass


def topic_requires(session: Session) -> dict[str, set[str]]:
    """Topic A builds on topic B when a concept in A requires a concept in B."""
    src, dst = aliased(Concept), aliased(Concept)
    out: dict[str, set[str]] = {}
    for a, b in session.execute(
        select(src.topic_id, dst.topic_id)
        .select_from(ConceptRelationship)
        .join(src, src.id == ConceptRelationship.source_concept_id)
        .join(dst, dst.id == ConceptRelationship.target_concept_id)
        .where(ConceptRelationship.kind == RelationshipKind.REQUIRES)
    ).tuples():
        if a != b:
            out.setdefault(a, set()).add(b)
    return out


def latest(session: Session, student_id: str) -> StudyPlan | None:
    return session.scalar(
        select(StudyPlan)
        .where(StudyPlan.student_id == student_id)
        .order_by(StudyPlan.created_at.desc())
    )


def generate(
    session: Session,
    student_id: str,
    policy: Policy,
    goal_slugs: list[str],
    now: datetime | None = None,
) -> StudyPlan:
    now = now or datetime.now(UTC)
    goals_topics = (
        list(session.scalars(select(Topic).where(Topic.slug.in_(goal_slugs)))) if goal_slugs else []
    )
    unknown = set(goal_slugs) - {t.slug for t in goals_topics}
    if unknown:
        raise NotFound(", ".join(sorted(unknown)))
    goals = {t.id for t in goals_topics}

    views = {v.topic.id: v for v in refresh_student(session, student_id, policy)}
    inputs: list[TopicInput] = []
    for topic in [v.topic for v in views.values()] + [t for t in goals_topics if t.id not in views]:
        v = views.get(topic.id)
        bands: tuple[Band, ...] = ()
        last_quiz = None
        importance = None
        label = MasteryClass.INSUFFICIENT_EVIDENCE
        if v is not None:
            label = v.classification.label
            importance = max((imp for _, _, imp in v.subjects), default=None)
            bands = tuple(
                Band(e.details["band"])
                for e in v.evidence
                if e.kind is EvidenceKind.SUBJECT_SCORE_PRIOR and "band" in e.details
            )
            quizzes = [
                e for e in v.evidence if e.kind is EvidenceKind.DIAGNOSTIC and e.score is not None
            ]
            if quizzes:
                q = max(quizzes, key=lambda e: e.observed_at)
                when = q.observed_at if q.observed_at.tzinfo else q.observed_at.replace(tzinfo=UTC)
                last_quiz = (float(q.score or 0), when)
        inputs.append(
            TopicInput(
                topic.id,
                topic.name,
                label,
                importance,
                topic.estimated_study_minutes,
                bands,
                last_quiz,
            )
        )

    entries = build_plan(inputs, topic_requires(session), goals, policy.plan, now)
    names = {t.topic_id: t.name for t in inputs}
    previous = latest(session, student_id)
    statuses = {i.topic_id: i.status for i in previous.items} if previous else {}
    if previous is not None:
        session.delete(previous)
        session.flush()

    plan = StudyPlan(
        student_id=student_id,
        formula_version=FORMULA_VERSION,
        parameters={
            "goal_topics": sorted(t.slug for t in goals_topics),
            "weights": policy.plan.weights.model_dump(),
            "policy_version": policy.version,
            "left_out_strong": sorted(
                t.name
                for t in inputs
                if t.classification is MasteryClass.STRONG and t.topic_id not in goals
            ),
        },
    )
    for position, e in enumerate(entries):
        breakdown: dict[str, Any] = {
            "classification": e.topic.classification.value,
            "minutes": e.topic.minutes,
            "terms": {
                k: {
                    "value": round(t.value, 4),
                    "weight": t.weight,
                    "contribution": t.contribution,
                    "why": t.why,
                }
                for k, t in e.terms.items()
            },
            "after": [names[a] for a in e.after],
            "moved_for": names.get(e.moved_for) if e.moved_for else None,
            "goal": e.topic.topic_id in goals,
            "next_step": NEXT_STEP[e.topic.classification],
        }
        plan.items.append(
            StudyPlanItem(
                topic_id=e.topic.topic_id,
                position=position,
                priority_score=Decimal(str(e.priority)),
                score_breakdown=breakdown,
                status=statuses.get(e.topic.topic_id, StudyPlanItemStatus.PENDING),
            )
        )
    session.add(plan)
    session.commit()
    return plan


def set_status(
    session: Session, student_id: str, item_id: str, status: StudyPlanItemStatus
) -> StudyPlanItem:
    item = session.get(StudyPlanItem, item_id)
    if item is None or item.plan.student_id != student_id:
        raise NotFound(item_id)
    item.status = status
    session.commit()
    return item
