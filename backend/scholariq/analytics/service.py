"""Database-facing analytics: load confirmed results, maintain topic evidence
derived from them, and recompute topic classifications."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scholariq.analytics.policy import Policy
from scholariq.analytics.subjects import (
    ResultRow,
    SubjectSummary,
    summarise_subjects,
)
from scholariq.analytics.topics import Classification, EvidenceItem, SubjectSignal, classify
from scholariq.db.models import (
    Assessment,
    AssessmentResult,
    GradingScale,
    Subject,
    SubjectTopic,
    Topic,
    TopicEvidence,
    TopicMastery,
)
from scholariq.domain.enums import EvidenceKind


def load_result_rows(session: Session, student_id: str) -> list[ResultRow]:
    stmt = (
        select(AssessmentResult, Assessment, Subject, GradingScale)
        .join(Assessment, AssessmentResult.assessment_id == Assessment.id)
        .join(Subject, AssessmentResult.subject_id == Subject.id)
        .outerjoin(GradingScale, AssessmentResult.grading_scale_id == GradingScale.id)
        .where(Assessment.student_id == student_id)
        .order_by(Assessment.created_at, AssessmentResult.created_at)
    )
    sequence: dict[str, int] = {}
    rows = []
    for result, assessment, subject, scale in session.execute(stmt).all():
        seq = sequence.setdefault(assessment.id, len(sequence))
        rows.append(
            ResultRow(
                result_id=result.id,
                assessment_id=assessment.id,
                sequence=seq,
                subject_id=subject.id,
                subject_name=subject.name,
                semester=assessment.semester,
                exam_type=assessment.exam_type.value,
                component=result.component.value,
                status=result.status,
                attempt_number=result.attempt_number,
                obtained=result.marks_obtained,
                maximum=result.max_marks,
                grade=result.grade,
                grade_points=result.grade_points,
                credits=result.credits,
                scale_id=scale.id if scale else None,
                scale_max=scale.max_grade_points if scale else None,
            )
        )
    return rows


def topic_links(session: Session, subject_ids: set[str]) -> dict[str, list[tuple[Topic, int]]]:
    """subject id -> [(topic, importance)] in curriculum order."""
    if not subject_ids:
        return {}
    stmt = (
        select(SubjectTopic, Topic)
        .join(Topic, SubjectTopic.topic_id == Topic.id)
        .where(SubjectTopic.subject_id.in_(subject_ids))
        .order_by(SubjectTopic.subject_id, SubjectTopic.position)
    )
    out: dict[str, list[tuple[Topic, int]]] = defaultdict(list)
    for link, topic in session.execute(stmt).all():
        out[link.subject_id].append((topic, link.importance))
    return out


def rebuild_subject_priors(
    session: Session, student_id: str, summaries: list[SubjectSummary], rows: list[ResultRow]
) -> None:
    """Subject-score priors are derived data: replace them from current results.

    When a confirmed exam breakdown of the same sitting already gives
    question-level marks for a topic, the subject mark of that sitting is not
    added to the topic again: it is the same marks, summed.
    """
    session.execute(
        delete(TopicEvidence).where(
            TopicEvidence.student_id == student_id,
            TopicEvidence.kind == EvidenceKind.SUBJECT_SCORE_PRIOR,
        )
    )
    links = topic_links(session, {s.subject_id for s in summaries})
    latest_result: dict[str, str] = {}
    for s in summaries:
        last = s.sittings[-1].assessment_id
        latest_result[s.subject_id] = next(
            r.result_id for r in rows if r.subject_id == s.subject_id and r.assessment_id == last
        )
    covered = {
        (ev.details.get("assessment_id"), ev.details.get("subject_id"), ev.topic_id)
        for ev in session.scalars(
            select(TopicEvidence).where(
                TopicEvidence.student_id == student_id,
                TopicEvidence.kind == EvidenceKind.EXAM_BREAKDOWN,
            )
        )
    }
    for s in summaries:
        if s.latest is None:
            continue
        sitting = s.sittings[-1].assessment_id
        for topic, _ in links.get(s.subject_id, []):
            if (sitting, s.subject_id, topic.id) in covered:
                continue
            session.add(
                TopicEvidence(
                    student_id=student_id,
                    topic_id=topic.id,
                    kind=EvidenceKind.SUBJECT_SCORE_PRIOR,
                    score=s.latest.value,
                    sample_size=1,
                    assessment_result_id=latest_result[s.subject_id],
                    details={
                        "subject_id": s.subject_id,
                        "subject_name": s.subject_name,
                        "basis": s.latest.basis.value,
                        "band": s.band.value,
                    },
                )
            )
    session.flush()


@dataclass
class TopicView:
    topic: Topic
    subjects: list[tuple[str, str, int]]  # (subject id, subject name, importance)
    classification: Classification
    evidence: list[TopicEvidence]


def compute_topics(
    session: Session,
    student_id: str,
    policy: Policy,
    summaries: list[SubjectSummary],
    now: datetime | None = None,
) -> list[TopicView]:
    links = topic_links(session, {s.subject_id for s in summaries})
    by_subject = {s.subject_id: s for s in summaries}
    topic_subjects: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    topics: dict[str, Topic] = {}
    for subject_id, linked in links.items():
        for topic, importance in linked:
            topics[topic.id] = topic
            topic_subjects[topic.id].append(
                (subject_id, by_subject[subject_id].subject_name, importance)
            )
    evidence: dict[str, list[TopicEvidence]] = defaultdict(list)
    for ev in session.scalars(
        select(TopicEvidence)
        .where(TopicEvidence.student_id == student_id)
        .order_by(TopicEvidence.observed_at)
    ):
        evidence[ev.topic_id].append(ev)
    for topic_id in evidence.keys() - topics.keys():
        if (t := session.get(Topic, topic_id)) is not None:
            topics[topic_id] = t

    views = []
    for topic_id, topic in topics.items():
        signals = []
        for subject_id, _name, _ in topic_subjects.get(topic_id, []):
            s = by_subject[subject_id]
            siblings = tuple(t.name for t, _ in links.get(subject_id, []))
            signals.append(SubjectSignal(s.subject_name, s.band, siblings))
        items = [
            EvidenceItem(
                id=e.id,
                kind=e.kind,
                score=Decimal(e.score) if e.score is not None else None,
                sample_size=e.sample_size,
                observed_at=e.observed_at,
                details=e.details,
            )
            for e in evidence.get(topic_id, [])
        ]
        views.append(
            TopicView(
                topic,
                topic_subjects.get(topic_id, []),
                classify(topic.name, items, signals, policy, now),
                evidence.get(topic_id, []),
            )
        )
    return views


def refresh_student(session: Session, student_id: str, policy: Policy) -> list[TopicView]:
    """Recompute derived evidence and store classifications. Idempotent."""
    rows = load_result_rows(session, student_id)
    summaries = summarise_subjects(rows, policy)
    rebuild_subject_priors(session, student_id, summaries, rows)
    views = compute_topics(session, student_id, policy, summaries)
    session.execute(delete(TopicMastery).where(TopicMastery.student_id == student_id))
    now = datetime.now(UTC)
    for v in views:
        c = v.classification
        session.add(
            TopicMastery(
                student_id=student_id,
                topic_id=v.topic.id,
                classification=c.label,
                rationale={
                    "reasons": c.reasons,
                    "subject_messages": c.subject_messages,
                    "evidence_ids": c.evidence_ids,
                    "direct_observations": c.direct_observations,
                    "next_action": c.next_action,
                    "policy_version": c.policy_version,
                },
                rule_version=c.rule_version,
                computed_at=now,
            )
        )
    session.commit()
    return views
