"""The AI-free tutor: questions, conversations and answer checking.

Every answer is computed by the local answer engine; see
``scholariq.answering.engine`` for the decision rules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from scholariq.answering.checking import BadResponse, mark
from scholariq.answering.model import RULES_VERSION, Answer
from scholariq.answering.solvers import SUPPORTED
from scholariq.api.deps import PolicyDep, SessionDep, SettingsDep, StudentDep, tutor_limiter
from scholariq.db.models import Conversation, Message, Question, VerifiedAnswer
from scholariq.domain.enums import MessageRole
from scholariq.knowledge.index import allowed_trust
from scholariq.nlu.intents import FollowUp
from scholariq.tutoring import service

router = APIRouter(prefix="/tutor", tags=["tutor"])

ACTIONS: dict[str, FollowUp] = {
    "simplify": FollowUp.SIMPLIFY,
    "example": FollowUp.EXAMPLE,
    "check": FollowUp.CHECK,
    "deeper": FollowUp.DEEPER,
}


class TutorInfo(BaseModel):
    retention_days: int
    rules_version: str
    solvers: list[str]
    allow_unreviewed: bool


@router.get("/info", response_model=TutorInfo)
def info(settings: SettingsDep) -> TutorInfo:
    """What the tutor can do and how long it keeps conversations. Needs no profile."""
    return TutorInfo(
        retention_days=settings.conversation_retention_days,
        rules_version=RULES_VERSION,
        solvers=SUPPORTED,
        allow_unreviewed=settings.allow_unreviewed_content,
    )


class AskIn(BaseModel):
    text: Annotated[str, Field(max_length=4000)] = ""
    conversation_id: str | None = None
    action: Literal["simplify", "example", "check", "deeper"] | None = None
    # The concept slug of a clarifying question's option, when one was picked.
    meaning: Annotated[str, Field(max_length=200)] | None = None

    @model_validator(mode="after")
    def _needs_something(self) -> AskIn:
        if not self.text.strip() and self.action is None:
            raise ValueError("Type a question.")
        if self.action is not None and not self.conversation_id:
            raise ValueError("Actions apply to an earlier answer in a conversation.")
        return self


class AskOut(BaseModel):
    conversation_id: str
    message_id: str
    answer: Answer


@router.post("/ask", response_model=AskOut)
def ask(
    body: AskIn, student: StudentDep, session: SessionDep, settings: SettingsDep, policy: PolicyDep
) -> AskOut:
    if not tutor_limiter.allow(student.id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many questions at once; wait a moment."
        )
    try:
        conv, reply, answer = service.ask(
            session,
            settings,
            policy,
            student.id,
            body.text,
            body.conversation_id,
            ACTIONS[body.action] if body.action else None,
            body.meaning,
        )
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.") from exc
    return AskOut(conversation_id=conv.id, message_id=reply.id, answer=answer)


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    last_message_at: datetime | None
    messages: int


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    student: StudentDep, session: SessionDep, settings: SettingsDep
) -> list[ConversationSummary]:
    service.purge_expired(session, settings, student.id)
    session.commit()
    rows = session.execute(
        select(Conversation, func.count(Message.id), func.max(Message.created_at))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.student_id == student.id)
        .group_by(Conversation.id)
        .order_by(func.max(Message.created_at).desc())
    ).all()
    return [
        ConversationSummary(
            id=c.id, title=c.title, created_at=c.created_at, last_message_at=last, messages=n
        )
        for c, n, last in rows
    ]


class MessageOut(BaseModel):
    id: str
    role: MessageRole
    text: str
    created_at: datetime
    answer: Answer | None = None


class ConversationOut(BaseModel):
    id: str
    title: str | None
    retention_days: int
    messages: list[MessageOut]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str, student: StudentDep, session: SessionDep, settings: SettingsDep
) -> ConversationOut:
    try:
        conv = service.owned(session, student.id, conversation_id)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.") from exc
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        retention_days=settings.conversation_retention_days,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                text=m.text,
                created_at=m.created_at,
                answer=Answer.model_validate(m.analysis["answer"])
                if "answer" in m.analysis
                else None,
            )
            for m in conv.messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, student: StudentDep, session: SessionDep) -> None:
    try:
        conv = service.owned(session, student.id, conversation_id)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.") from exc
    session.delete(conv)
    session.commit()


class CheckIn(BaseModel):
    question: Annotated[str, Field(max_length=200)]
    response: dict[str, Any]


class CheckOut(BaseModel):
    correct: bool
    expected: str
    explanation: str
    recorded_as_evidence: bool = False


@router.post("/check", response_model=CheckOut)
def check_answer(
    body: CheckIn, student: StudentDep, session: SessionDep, settings: SettingsDep
) -> CheckOut:
    del student  # a profile is required, but tutor self-checks are not stored
    row = session.execute(
        select(Question, VerifiedAnswer)
        .join(VerifiedAnswer, VerifiedAnswer.question_id == Question.id)
        .where(
            Question.slug == body.question,
            Question.trust_status.in_(allowed_trust(settings.allow_unreviewed_content)),
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found.")
    try:
        result = mark(row[0], row[1], body.response)
    except BadResponse as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return CheckOut(
        correct=result.correct, expected=result.expected, explanation=result.explanation
    )
