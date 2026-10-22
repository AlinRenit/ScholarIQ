"""Tutor conversations: ask, store, list, delete, and expire old ones.

Stored per student: the question text and the structured answer, so the
conversation can be shown again and follow-ups can refer back. Nothing is
logged. Conversations older than ``conversation_retention_days`` (counted from
their last message) are deleted whenever the student uses the tutor.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from scholariq.analytics.policy import Policy
from scholariq.answering.engine import Engine, Request
from scholariq.answering.model import Answer
from scholariq.core.config import Settings
from scholariq.db.models import Conversation, KnowledgeDocument, Message, MessageSource
from scholariq.domain.enums import MessageRole
from scholariq.knowledge.index import get_index
from scholariq.nlu.intents import FollowUp
from scholariq.nlu.lexicon import get_lexicon
from scholariq.nlu.parser import Context

MAX_TITLE = 80


class NotFound(LookupError):
    pass


def _context(analysis: dict[str, Any]) -> Context | None:
    raw = analysis.get("context")
    if not isinstance(raw, dict):
        return None
    return Context(
        concepts=list(raw.get("concepts", [])),
        topic=raw.get("topic"),
        intent=raw.get("intent"),
        depth=raw.get("depth", "standard"),
        steps=list(raw.get("steps", [])),
    )


def purge_expired(
    session: Session, settings: Settings, student_id: str, now: datetime | None = None
) -> int:
    if settings.conversation_retention_days == 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=settings.conversation_retention_days)
    last = (
        select(Message.conversation_id, func.max(Message.created_at).label("last"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    stale = session.scalars(
        select(Conversation.id)
        .outerjoin(last, last.c.conversation_id == Conversation.id)
        .where(
            Conversation.student_id == student_id,
            func.coalesce(last.c.last, Conversation.created_at) < cutoff,
        )
    ).all()
    if stale:
        session.execute(delete(Conversation).where(Conversation.id.in_(stale)))
    return len(stale)


def owned(session: Session, student_id: str, conversation_id: str) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None or conv.student_id != student_id:
        raise NotFound(conversation_id)
    return conv


def ask(
    session: Session,
    settings: Settings,
    policy: Policy,
    student_id: str,
    text: str,
    conversation_id: str | None,
    action: FollowUp | None,
    meaning: str | None = None,
) -> tuple[Conversation, Message, Answer]:
    purge_expired(session, settings, student_id)
    if conversation_id:
        conv = owned(session, student_id, conversation_id)
    else:
        conv = Conversation(
            student_id=student_id, title=(text.strip() or "Tutor session")[:MAX_TITLE]
        )
        session.add(conv)
        session.flush()

    previous = session.scalars(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.role == MessageRole.TUTOR)
        .order_by(Message.created_at.desc())
    ).all()
    context = _context(previous[0].analysis) if previous else None
    asked = {slug for m in previous for slug in m.analysis.get("asked", [])}

    index = get_index(session, settings.allow_unreviewed_content)
    lexicon = get_lexicon(session, index, settings.content_dir)
    engine = Engine(
        session,
        lexicon,
        allow_unreviewed=settings.allow_unreviewed_content,
        student_id=student_id,
        policy=policy,
    )
    outcome = engine.answer(Request(text, context, action, asked, meaning))
    answer = outcome.answer

    shown = [s.question.slug for s in answer.sections if s.question is not None]
    session.add(
        Message(
            conversation_id=conv.id,
            role=MessageRole.STUDENT,
            text=text if text.strip() else f"[{action.value if action else 'continue'}]",
            analysis={"action": action.value if action else None},
        )
    )
    session.flush()
    reply = Message(
        conversation_id=conv.id,
        role=MessageRole.TUTOR,
        text=_summary(answer),
        analysis={
            "answer": answer.model_dump(mode="json"),
            "context": asdict(outcome.context),
            "asked": shown,
        },
    )
    session.add(reply)
    session.flush()
    doc_slugs = [s.origin.document for s in answer.sections if s.origin.document]
    if doc_slugs:
        ids = dict(
            session.execute(
                select(KnowledgeDocument.slug, KnowledgeDocument.id).where(
                    KnowledgeDocument.slug.in_(doc_slugs)
                )
            )
            .tuples()
            .all()
        )
        for rank, slug in enumerate(dict.fromkeys(doc_slugs), 1):
            if slug in ids:
                session.add(
                    MessageSource(message_id=reply.id, knowledge_document_id=ids[slug], rank=rank)
                )
    session.commit()
    return conv, reply, answer


def _summary(answer: Answer) -> str:
    if answer.status == "clarify" and answer.clarification:
        return answer.clarification.question
    if answer.status == "abstained":
        return answer.missing or "Not covered."
    names = ", ".join(c.name for c in answer.concepts[:3])
    return f"{answer.handler_label}: {names}" if names else answer.handler_label
