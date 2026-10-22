"""Diagnostic quizzes. Results are recorded as topic evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from scholariq.api.deps import PolicyDep, SessionDep, SettingsDep, StudentDep
from scholariq.diagnostics import service
from scholariq.domain.enums import MasteryClass, TrustStatus
from scholariq.knowledge.index import allowed_trust

router = APIRouter(prefix="/practice", tags=["practice"])


class QuizSummary(BaseModel):
    id: str
    submitted_at: datetime
    correct: int
    total: int


class PracticeTopic(BaseModel):
    slug: str
    name: str
    subjects: list[str]
    questions: int
    classification: MasteryClass
    quizzes: list[QuizSummary]
    open_quiz: str | None


@router.get("/topics", response_model=list[PracticeTopic])
def topics(student: StudentDep, session: SessionDep, settings: SettingsDep) -> list[PracticeTopic]:
    return [
        PracticeTopic(
            slug=t.topic.slug,
            name=t.topic.name,
            subjects=t.subjects,
            questions=t.questions,
            classification=t.classification,
            quizzes=[QuizSummary(**q) for q in t.quizzes],
            open_quiz=t.open_quiz,
        )
        for t in service.overview(
            session, student.id, allowed_trust(settings.allow_unreviewed_content)
        )
    ]


class QuestionOut(BaseModel):
    slug: str
    prompt: str
    options: list[str]
    style: str
    difficulty: int
    concept: str | None
    trust: TrustStatus


class MarkedOut(BaseModel):
    slug: str
    chosen: int
    correct_option: int
    correct: bool
    explanation: str


class OutcomeOut(BaseModel):
    classification: MasteryClass
    reasons: list[str]
    next_action: str
    direct_observations: int


class QuizOut(BaseModel):
    id: str
    topic_slug: str
    topic_name: str
    created_at: datetime
    available: int
    questions: list[QuestionOut]
    submitted_at: datetime | None
    correct: int | None
    marked: list[MarkedOut]
    before: OutcomeOut | None
    after: OutcomeOut | None
    recorded_as_evidence: bool


def _out(v: service.QuizView) -> QuizOut:
    def outcome(o: service.Outcome | None) -> OutcomeOut | None:
        if o is None:
            return None
        return OutcomeOut(
            classification=o.label,
            reasons=o.reasons,
            next_action=o.next_action,
            direct_observations=o.direct_observations,
        )

    return QuizOut(
        id=v.id,
        topic_slug=v.topic_slug,
        topic_name=v.topic_name,
        created_at=v.created_at,
        available=v.available,
        questions=[QuestionOut(**q.__dict__) for q in v.questions],
        submitted_at=v.submitted_at,
        correct=v.correct,
        marked=[
            MarkedOut(
                slug=m.question.slug,
                chosen=m.chosen,
                correct_option=m.correct_option,
                correct=m.correct,
                explanation=m.explanation,
            )
            for m in v.marked
        ],
        before=outcome(v.before),
        after=outcome(v.after),
        recorded_as_evidence=v.submitted_at is not None,
    )


class StartIn(BaseModel):
    topic: Annotated[str, Field(max_length=120)]


@router.post("/quizzes", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
def start_quiz(
    body: StartIn,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    policy: PolicyDep,
) -> QuizOut:
    allowed = allowed_trust(settings.allow_unreviewed_content)
    try:
        return _out(service.start(session, student.id, body.topic, policy, allowed))
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found.") from exc
    except service.QuizError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
def get_quiz(
    quiz_id: str, student: StudentDep, session: SessionDep, settings: SettingsDep
) -> QuizOut:
    try:
        return _out(
            service.view(
                session, student.id, quiz_id, allowed_trust(settings.allow_unreviewed_content)
            )
        )
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found.") from exc


class SubmitIn(BaseModel):
    # Question slug -> index of the chosen option, as displayed.
    answers: dict[Annotated[str, Field(max_length=200)], Annotated[int, Field(ge=0, le=20)]]


@router.post("/quizzes/{quiz_id}/submit", response_model=QuizOut)
def submit_quiz(
    quiz_id: str,
    body: SubmitIn,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    policy: PolicyDep,
) -> QuizOut:
    allowed = allowed_trust(settings.allow_unreviewed_content)
    try:
        return _out(service.submit(session, student.id, quiz_id, body.answers, policy, allowed))
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quiz not found.") from exc
    except service.QuizError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
