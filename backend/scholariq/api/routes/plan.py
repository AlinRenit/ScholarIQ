"""Study plan: generate with the published formula, read, and mark progress."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from scholariq.api.deps import PolicyDep, SessionDep, StudentDep
from scholariq.db.models import StudyPlan, Topic
from scholariq.domain.enums import StudyPlanItemStatus
from scholariq.planning import service

router = APIRouter(prefix="/study-plan", tags=["study plan"])


class PlanItemOut(BaseModel):
    id: str
    topic_slug: str
    topic_name: str
    position: int
    priority: Decimal
    status: StudyPlanItemStatus
    breakdown: dict[str, Any]


class PlanOut(BaseModel):
    id: str
    created_at: datetime
    formula_version: str
    parameters: dict[str, Any]
    items: list[PlanItemOut]


def _out(session: SessionDep, plan: StudyPlan) -> PlanOut:
    topics = {
        t.id: t for t in session.query(Topic).filter(Topic.id.in_([i.topic_id for i in plan.items]))
    }
    return PlanOut(
        id=plan.id,
        created_at=plan.created_at,
        formula_version=plan.formula_version,
        parameters=plan.parameters,
        items=[
            PlanItemOut(
                id=i.id,
                topic_slug=topics[i.topic_id].slug,
                topic_name=topics[i.topic_id].name,
                position=i.position,
                priority=i.priority_score,
                status=i.status,
                breakdown=i.score_breakdown,
            )
            for i in plan.items
        ],
    )


@router.get("", response_model=PlanOut | None)
def get_plan(student: StudentDep, session: SessionDep) -> PlanOut | None:
    plan = service.latest(session, student.id)
    return _out(session, plan) if plan else None


class GenerateIn(BaseModel):
    goal_topics: Annotated[list[Annotated[str, Field(max_length=120)]], Field(max_length=60)] = []


@router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def generate_plan(
    body: GenerateIn, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> PlanOut:
    try:
        plan = service.generate(session, student.id, policy, body.goal_topics)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown topic: {exc}") from exc
    return _out(session, plan)


class StatusIn(BaseModel):
    status: Literal["pending", "lesson_completed", "skipped"]


@router.patch("/items/{item_id}", response_model=PlanItemOut)
def update_item(
    item_id: str, body: StatusIn, student: StudentDep, session: SessionDep
) -> PlanItemOut:
    try:
        item = service.set_status(session, student.id, item_id, StudyPlanItemStatus(body.status))
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan item not found.") from exc
    topic = session.get(Topic, item.topic_id)
    assert topic is not None
    return PlanItemOut(
        id=item.id,
        topic_slug=topic.slug,
        topic_name=topic.name,
        position=item.position,
        priority=item.priority_score,
        status=item.status,
        breakdown=item.score_breakdown,
    )
