"""Diagnostic quizzes: start, show, mark, and record the result as topic evidence.

A submitted quiz becomes one ``TopicEvidence`` row of kind DIAGNOSTIC (score =
fraction correct, sample size = number of questions) plus one
``DiagnosticAttempt`` per question. Topic classifications are then recomputed
with the usual rules, and the result reports the classification before and
after so the student can see what changed and why.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scholariq.analytics.policy import Policy
from scholariq.analytics.service import TopicView, refresh_student
from scholariq.answering.checking import mark
from scholariq.db.models import (
    Concept,
    DiagnosticAttempt,
    Question,
    QuizSession,
    Subject,
    SubjectTopic,
    Topic,
    TopicEvidence,
    TopicMastery,
    VerifiedAnswer,
)
from scholariq.diagnostics.quiz import Candidate, choose, option_order
from scholariq.domain.enums import EvidenceKind, MasteryClass, QuestionKind, TrustStatus


class NotFound(LookupError):
    pass


class QuizError(ValueError):
    pass


@dataclass
class ShownQuestion:
    slug: str
    prompt: str
    options: list[str]
    style: str
    difficulty: int
    concept: str | None
    trust: TrustStatus


@dataclass
class MarkedQuestion:
    question: ShownQuestion
    chosen: int
    correct_option: int
    correct: bool
    explanation: str


@dataclass
class Outcome:
    label: MasteryClass
    reasons: list[str]
    next_action: str
    direct_observations: int


@dataclass
class QuizView:
    id: str
    topic_slug: str
    topic_name: str
    created_at: datetime
    questions: list[ShownQuestion]
    available: int  # questions this topic has in total
    submitted_at: datetime | None = None
    marked: list[MarkedQuestion] = field(default_factory=list)
    correct: int | None = None
    before: Outcome | None = None
    after: Outcome | None = None


def _questions(
    session: Session, topic_id: str, allowed: tuple[TrustStatus, ...]
) -> list[tuple[Question, VerifiedAnswer, str | None]]:
    rows = session.execute(
        select(Question, VerifiedAnswer, Concept.canonical_name)
        .join(VerifiedAnswer, VerifiedAnswer.question_id == Question.id)
        .outerjoin(Concept, Concept.id == Question.concept_id)
        .where(
            Question.topic_id == topic_id,
            Question.trust_status.in_(allowed),
            Question.kind == QuestionKind.MULTIPLE_CHOICE,
        )
        .order_by(Question.slug)
    ).all()
    return [(q, a, name) for q, a, name in rows]


def _topic(session: Session, slug: str) -> Topic:
    topic = session.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None:
        raise NotFound(slug)
    return topic


def _shown(q: Question, concept: str | None, order: list[int]) -> ShownQuestion:
    return ShownQuestion(
        slug=q.slug,
        prompt=q.prompt,
        options=[q.options[i] for i in order],
        style=q.style,
        difficulty=q.difficulty,
        concept=concept,
        trust=q.trust_status,
    )


def start(
    session: Session,
    student_id: str,
    topic_slug: str,
    policy: Policy,
    allowed: tuple[TrustStatus, ...],
    now: datetime | None = None,
) -> QuizView:
    topic = _topic(session, topic_slug)
    pool = _questions(session, topic.id, allowed)
    if not pool:
        raise QuizError(f"{topic.name} has no quiz questions that may be used yet.")
    shown: dict[str, tuple[int, datetime]] = {}
    for past in session.scalars(
        select(QuizSession).where(
            QuizSession.student_id == student_id, QuizSession.topic_id == topic.id
        )
    ):
        for item in past.items:
            count, last = shown.get(item["slug"], (0, past.created_at))
            shown[item["slug"]] = (count + 1, max(last, past.created_at))
    quiz_id = str(uuid.uuid4())
    candidates = [
        Candidate(
            q.id,
            q.slug,
            q.style,
            q.difficulty,
            shown.get(q.slug, (0, None))[0],
            shown.get(q.slug, (0, None))[1],
        )
        for q, _, _ in pool
    ]
    picked = choose(candidates, policy.quizzes.size, quiz_id)
    n_options = {q.id: len(q.options) for q, _, _ in pool}
    items = [
        {
            "question_id": c.question_id,
            "slug": c.slug,
            "order": option_order(quiz_id, c.slug, n_options[c.question_id]),
        }
        for c in picked
    ]
    quiz = QuizSession(
        id=quiz_id,
        student_id=student_id,
        topic_id=topic.id,
        items=items,
        created_at=now or datetime.now(UTC),
    )
    session.add(quiz)
    session.commit()
    return view(session, student_id, quiz_id, allowed)


def _owned(session: Session, student_id: str, quiz_id: str) -> QuizSession:
    quiz = session.get(QuizSession, quiz_id)
    if quiz is None or quiz.student_id != student_id:
        raise NotFound(quiz_id)
    return quiz


def _outcome(views: list[TopicView], topic_id: str) -> Outcome:
    v = next((v for v in views if v.topic.id == topic_id), None)
    if v is None:
        return Outcome(MasteryClass.INSUFFICIENT_EVIDENCE, [], "", 0)
    c = v.classification
    return Outcome(c.label, c.reasons, c.next_action, c.direct_observations)


def view(
    session: Session, student_id: str, quiz_id: str, allowed: tuple[TrustStatus, ...]
) -> QuizView:
    quiz = _owned(session, student_id, quiz_id)
    topic = session.get(Topic, quiz.topic_id)
    assert topic is not None
    rows = {q.id: (q, a, name) for q, a, name in _questions(session, topic.id, allowed)}
    questions = []
    for item in quiz.items:
        row = rows.get(item["question_id"])
        if row is None:
            # Retired or no longer allowed since the quiz began.
            q = session.get(Question, item["question_id"])
            if q is None:
                continue
            questions.append(_shown(q, None, item["order"]))
        else:
            questions.append(_shown(row[0], row[2], item["order"]))
    result = QuizView(
        quiz.id,
        topic.slug,
        topic.name,
        quiz.created_at,
        questions,
        len(rows),
        quiz.submitted_at,
        correct=quiz.correct,
    )
    if quiz.submitted_at is not None:
        attempts = {
            a.question_id: a
            for a in session.scalars(
                select(DiagnosticAttempt).where(DiagnosticAttempt.quiz_session_id == quiz.id)
            )
        }
        for item, shown in zip(quiz.items, questions, strict=False):
            attempt = attempts.get(item["question_id"])
            answer = session.scalar(
                select(VerifiedAnswer).where(VerifiedAnswer.question_id == item["question_id"])
            )
            if attempt is None or answer is None:
                continue
            order: list[int] = item["order"]
            result.marked.append(
                MarkedQuestion(
                    shown,
                    int(attempt.response["shown_index"]),
                    order.index(int(answer.answer["option_index"])),
                    attempt.is_correct,
                    answer.explanation,
                )
            )
    return result


def submit(
    session: Session,
    student_id: str,
    quiz_id: str,
    answers: dict[str, int],
    policy: Policy,
    allowed: tuple[TrustStatus, ...],
    now: datetime | None = None,
) -> QuizView:
    """``answers`` maps question slug to the index of the option as displayed."""
    quiz = _owned(session, student_id, quiz_id)
    if quiz.submitted_at is not None:
        raise QuizError("This quiz has already been submitted. Start a new one to try again.")
    missing = [item["slug"] for item in quiz.items if item["slug"] not in answers]
    if missing:
        raise QuizError(f"Answer every question before submitting ({len(missing)} left).")
    now = now or datetime.now(UTC)

    before = _outcome(refresh_student(session, student_id, policy), quiz.topic_id)
    correct = 0
    for item in quiz.items:
        q = session.get(Question, item["question_id"])
        answer = session.scalar(
            select(VerifiedAnswer).where(VerifiedAnswer.question_id == item["question_id"])
        )
        if q is None or answer is None:
            raise QuizError("A question in this quiz was removed. Start a new quiz.")
        order: list[int] = item["order"]
        shown_index = answers[item["slug"]]
        if not 0 <= shown_index < len(order):
            raise QuizError("Choose one of the options for every question.")
        marked = mark(q, answer, {"option_index": order[shown_index]})
        correct += marked.correct
        session.add(
            DiagnosticAttempt(
                student_id=student_id,
                question_id=q.id,
                topic_id=quiz.topic_id,
                quiz_session_id=quiz.id,
                response={"shown_index": shown_index, "option_index": order[shown_index]},
                is_correct=marked.correct,
                attempted_at=now,
            )
        )
    total = len(quiz.items)
    quiz.submitted_at, quiz.correct = now, correct
    session.add(
        TopicEvidence(
            student_id=student_id,
            topic_id=quiz.topic_id,
            kind=EvidenceKind.DIAGNOSTIC,
            score=Decimal(correct) / Decimal(total),
            sample_size=total,
            details={"correct": correct, "total": total, "quiz_id": quiz.id},
            observed_at=now,
        )
    )
    session.flush()
    after = _outcome(refresh_student(session, student_id, policy), quiz.topic_id)
    result = view(session, student_id, quiz.id, allowed)
    result.before, result.after = before, after
    return result


@dataclass
class TopicPractice:
    topic: Topic
    subjects: list[str]
    questions: int
    classification: MasteryClass
    quizzes: list[dict[str, Any]]  # submitted quizzes, newest first
    open_quiz: str | None


def overview(
    session: Session, student_id: str, allowed: tuple[TrustStatus, ...]
) -> list[TopicPractice]:
    """Every topic with quiz questions, with this student's quiz history."""
    counts: dict[str, int] = {}
    for q in session.scalars(
        select(Question).where(
            Question.trust_status.in_(allowed), Question.kind == QuestionKind.MULTIPLE_CHOICE
        )
    ):
        counts[q.topic_id] = counts.get(q.topic_id, 0) + 1
    mastery = {
        m.topic_id: m.classification
        for m in session.scalars(select(TopicMastery).where(TopicMastery.student_id == student_id))
    }
    quizzes: dict[str, list[QuizSession]] = {}
    for qz in session.scalars(
        select(QuizSession)
        .where(QuizSession.student_id == student_id)
        .order_by(QuizSession.created_at.desc())
    ):
        quizzes.setdefault(qz.topic_id, []).append(qz)
    subjects: dict[str, list[str]] = {}
    for link, subject in session.execute(
        select(SubjectTopic, Subject)
        .join(Subject, Subject.id == SubjectTopic.subject_id)
        .where(Subject.is_custom.is_(False))
        .order_by(Subject.name, SubjectTopic.position)
    ).tuples():
        subjects.setdefault(link.topic_id, []).append(subject.name)
    out = []
    for topic in session.scalars(select(Topic).order_by(Topic.name)):
        if topic.id not in counts:
            continue
        mine = quizzes.get(topic.id, [])
        out.append(
            TopicPractice(
                topic,
                subjects.get(topic.id, []),
                counts[topic.id],
                mastery.get(topic.id, MasteryClass.INSUFFICIENT_EVIDENCE),
                [
                    {
                        "id": q.id,
                        "submitted_at": q.submitted_at,
                        "correct": q.correct,
                        "total": len(q.items),
                    }
                    for q in mine
                    if q.submitted_at is not None
                ],
                next((q.id for q in mine if q.submitted_at is None), None),
            )
        )
    return out
