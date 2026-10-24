"""Exam breakdown workflow: create -> question paper -> review and marks ->
confirm -> topic evidence -> analysis.

Only a confirmed breakdown produces topic evidence, one item per topic per
breakdown, tagged with the breakdown's id. Saving again deletes and rebuilds
that breakdown's evidence (and nothing else), so repeated saves never
duplicate it, and deleting a breakdown removes exactly its evidence. Topic
classifications are then recomputed by the existing ``refresh_student``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from scholariq.analytics.policy import Policy
from scholariq.analytics.service import refresh_student
from scholariq.core.config import Settings
from scholariq.db.models import (
    Assessment,
    AssessmentResult,
    Document,
    ExamBreakdown,
    ExamQuestion,
    ExamQuestionMapping,
    Student,
    StudyPlan,
    Subject,
    SubjectModule,
    SubjectTopic,
    Topic,
    TopicEvidence,
    TopicMastery,
)
from scholariq.domain.enums import (
    AttemptStatus,
    BreakdownStatus,
    DocumentStatus,
    EvidenceKind,
)
from scholariq.domain.exams import BreakdownUpdate, NewBreakdown
from scholariq.exams.analysis import (
    Breakdown,
    MappingInput,
    QuestionInput,
    Tally,
    analyse,
)
from scholariq.ingestion.extract import ExtractionError, extract
from scholariq.ingestion.question_paper import PARSER_NAME, PaperParse, parse_question_paper
from scholariq.ingestion.storage import FileStore
from scholariq.ingestion.validation import FileKind, UploadRejected, validate_upload

logger = logging.getLogger(__name__)

QUESTION_PAPER = "question_paper"
CENT = Decimal("0.01")
SHARE_STEP = Decimal("0.0001")
Band = Literal["strong", "developing", "needs_attention"]
PAPER_KINDS = {FileKind.PDF, FileKind.PNG, FileKind.JPEG, FileKind.TEXT}


class BreakdownProblem(ValueError):
    """A user-facing problem with the request (HTTP 422)."""


class BreakdownConflict(Exception):
    def __init__(self, message: str, existing_id: str | None = None) -> None:
        super().__init__(message)
        self.existing_id = existing_id


class NotFound(LookupError):
    pass


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def owned(session: Session, student_id: str, breakdown_id: str) -> ExamBreakdown:
    b = session.scalar(
        select(ExamBreakdown)
        .where(ExamBreakdown.id == breakdown_id)
        .options(selectinload(ExamBreakdown.questions).selectinload(ExamQuestion.mappings))
    )
    # Same answer for "missing" and "not yours", so ids cannot be probed.
    if b is None or b.student_id != student_id:
        raise NotFound(breakdown_id)
    return b


@dataclass
class SubjectStructure:
    subject: Subject
    modules: list[SubjectModule]
    # topic id -> (topic, module id or None), in curriculum order
    topics: dict[str, tuple[Topic, str | None]]

    @property
    def topic_module(self) -> dict[str, str | None]:
        return {tid: mid for tid, (_, mid) in self.topics.items()}


def structure(session: Session, subject_id: str) -> SubjectStructure:
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise NotFound(subject_id)
    modules = list(
        session.scalars(
            select(SubjectModule)
            .where(SubjectModule.subject_id == subject_id)
            .order_by(SubjectModule.number)
        )
    )
    topics = {
        t.id: (t, link.module_id)
        for link, t in session.execute(
            select(SubjectTopic, Topic)
            .join(Topic, SubjectTopic.topic_id == Topic.id)
            .where(SubjectTopic.subject_id == subject_id)
            .order_by(SubjectTopic.position)
        ).all()
    }
    return SubjectStructure(subject, modules, topics)


def _assessment(session: Session, student_id: str, assessment_id: str | None) -> Assessment | None:
    if assessment_id is None:
        return None
    a = session.get(Assessment, assessment_id)
    if a is None or a.student_id != student_id:
        raise BreakdownProblem("That exam is not in your results.")
    return a


def _check_unique(
    session: Session, assessment_id: str | None, subject_id: str, own_id: str | None
) -> None:
    if assessment_id is None:
        return
    other = session.scalar(
        select(ExamBreakdown.id).where(
            ExamBreakdown.assessment_id == assessment_id,
            ExamBreakdown.subject_id == subject_id,
        )
    )
    if other is not None and other != own_id:
        raise BreakdownConflict(
            "There is already a breakdown of this subject for that exam.", existing_id=other
        )


# --------------------------------------------------------------------------- #
# Create, paper, update
# --------------------------------------------------------------------------- #


def _marks(value: Decimal | None) -> Decimal | None:
    """Marks as the database stores them (two decimal places)."""
    return value.quantize(CENT) if value is not None else None


def _default_title(subject: Subject, assessment: Assessment | None) -> str:
    if assessment is not None:
        if assessment.exam_name:
            return f"{subject.name}: {assessment.exam_name}"[:200]
        if assessment.semester:
            return f"{subject.name}: semester {assessment.semester}"
    return f"{subject.name} exam"


def create(session: Session, student: Student, body: NewBreakdown) -> ExamBreakdown:
    subject = session.get(Subject, body.subject_id)
    if subject is None:
        raise BreakdownProblem("Unknown subject.")
    assessment = _assessment(session, student.id, body.assessment_id)
    _check_unique(session, body.assessment_id, subject.id, None)
    b = ExamBreakdown(
        student_id=student.id,
        subject_id=subject.id,
        assessment_id=body.assessment_id,
        title=body.title or _default_title(subject, assessment),
        held_on=body.held_on or (assessment.held_on if assessment else None),
        declared_total=_marks(body.declared_total),
        status=BreakdownStatus.DRAFT,
        choice_rules={},
    )
    session.add(b)
    session.commit()
    return b


def _paper_document(
    session: Session, settings: Settings, store: FileStore, student: Student,
    filename: str | None, data: bytes,
) -> tuple[Document, PaperParse | None]:  # fmt: skip
    """Store the paper as a Document (validated, retained and purged like any
    upload) and parse it. Re-uploading the same paper reuses the earlier
    reading, so a repeat attempt with the same paper needs no second upload."""
    upload = validate_upload(filename, data, settings.max_upload_bytes)
    if upload.kind not in PAPER_KINDS:
        raise UploadRejected("Upload the question paper as a PDF, PNG, JPEG or text file.")
    digest = hashlib.sha256(upload.data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.student_id == student.id, Document.sha256 == digest)
    )
    if existing is not None:
        if (existing.analysis or {}).get("kind") != QUESTION_PAPER:
            raise BreakdownProblem("This file was uploaded as a marksheet, not a question paper.")
        if existing.status is not DocumentStatus.FAILED:
            return existing, _stored_parse(existing)
        # A paper that failed before (e.g. OCR not installed then) is read again.
        session.delete(existing)
        session.flush()

    doc = Document(
        student_id=student.id,
        original_filename=upload.filename,
        media_type=upload.media_type,
        size_bytes=len(upload.data),
        sha256=digest,
        storage_key=store.save(upload.data),
        status=DocumentStatus.UPLOADED,
        parser_name=PARSER_NAME,
        analysis={"kind": QUESTION_PAPER},
        retain_until=datetime.now(UTC) + timedelta(days=settings.upload_retention_days),
    )
    session.add(doc)
    session.flush()
    try:
        content = extract(upload, settings.tesseract_cmd)
    except ExtractionError as exc:
        doc.status = DocumentStatus.FAILED
        doc.error = str(exc)
        store.delete(doc.storage_key)
        doc.storage_key = None
        session.flush()
        return doc, None
    parsed = parse_question_paper(content)
    doc.status = DocumentStatus.EXTRACTED
    doc.analysis = {
        "kind": QUESTION_PAPER,
        "source": content.source.value,
        "pages": content.pages,
        "notes": content.notes,
        "warnings": parsed.warnings,
        "declared_total": str(parsed.declared_total) if parsed.declared_total else None,
        "choice_rules": parsed.choice_rules,
        "questions": [_parsed_dict(q) for q in parsed.questions],
    }
    session.flush()
    return doc, parsed


def _parsed_dict(q: Any) -> dict[str, Any]:
    return {
        "label": q.label,
        "text": q.text,
        "context": q.context,
        "section": q.section,
        "paper_module": q.paper_module,
        "page": q.page,
        "max_marks": str(q.max_marks) if q.max_marks is not None else None,
        "confidence": q.confidence,
        "is_optional": q.is_optional,
        "choice_group": q.choice_group,
        "needs_review": q.needs_review,
        "source_text": q.source_text,
        "notes": q.notes,
    }


def _stored_parse(doc: Document) -> PaperParse:
    from scholariq.ingestion.question_paper import ParsedQuestion

    a = doc.analysis or {}
    questions = [
        ParsedQuestion(
            label=q["label"],
            text=q["text"],
            context=q.get("context"),
            section=q.get("section"),
            paper_module=q.get("paper_module"),
            page=q.get("page"),
            max_marks=Decimal(q["max_marks"]) if q.get("max_marks") else None,
            confidence=q.get("confidence", 0.0),
            is_optional=q.get("is_optional", False),
            choice_group=q.get("choice_group"),
            needs_review=q.get("needs_review", False),
            source_text=q.get("source_text", ""),
            notes=q.get("notes", []),
        )
        for q in a.get("questions", [])
    ]
    total = a.get("declared_total")
    return PaperParse(
        questions, Decimal(total) if total else None, a.get("choice_rules", {}),
        a.get("warnings", []),
    )  # fmt: skip


@dataclass
class PaperOutcome:
    questions_found: int
    warnings: list[str]
    error: str | None
    source: str | None


def attach_paper(
    session: Session, settings: Settings, store: FileStore, policy: Policy, student: Student,
    b: ExamBreakdown, filename: str | None, data: bytes, replace: bool,
) -> PaperOutcome:  # fmt: skip
    if b.questions and not replace:
        raise BreakdownConflict("This breakdown already has questions. Replace them?")
    doc, parsed = _paper_document(session, settings, store, student, filename, data)
    previous = b.document_id
    b.document_id = doc.id
    if parsed is None:
        session.commit()
        return PaperOutcome(0, [], doc.error, None)
    was_confirmed = b.status is BreakdownStatus.CONFIRMED
    b.questions.clear()
    session.flush()
    for position, q in enumerate(parsed.questions):
        b.questions.append(
            ExamQuestion(
                position=position,
                label=q.label,
                section=q.section,
                context=q.context,
                text=q.text,
                page=q.page,
                max_marks=_marks(q.max_marks),
                attempt_status=AttemptStatus.UNKNOWN,
                is_optional=q.is_optional,
                choice_group=q.choice_group,
                needs_review=q.needs_review,
                parse_confidence=Decimal(str(q.confidence)).quantize(Decimal("0.001")),
                paper_module=q.paper_module,
                source_text=q.source_text or None,
            )
        )
    if parsed.declared_total is not None and b.declared_total is None:
        b.declared_total = _marks(parsed.declared_total)
    b.choice_rules = dict(parsed.choice_rules)
    # New questions have no marks yet: a confirmed breakdown goes back to draft.
    b.status = BreakdownStatus.DRAFT
    b.confirmed_at = None
    _drop_unused_paper(session, store, previous, b.id)
    session.commit()
    if was_confirmed:
        sync_evidence(session, b)
        session.commit()
        refresh_student(session, student.id, policy)
    a = doc.analysis or {}
    return PaperOutcome(len(parsed.questions), parsed.warnings, None, a.get("source"))


def _drop_unused_paper(
    session: Session, store: FileStore, document_id: str | None, except_id: str
) -> None:
    if document_id is None:
        return
    doc = session.get(Document, document_id)
    if doc is None or (doc.analysis or {}).get("kind") != QUESTION_PAPER:
        return
    used = session.scalar(
        select(ExamBreakdown.id).where(
            ExamBreakdown.document_id == document_id, ExamBreakdown.id != except_id
        )
    )
    if used is None:
        store.delete(doc.storage_key)
        session.delete(doc)


def update(
    session: Session, policy: Policy, student: Student, b: ExamBreakdown, body: BreakdownUpdate
) -> ExamBreakdown:
    s = structure(session, b.subject_id)
    module_ids = {m.id for m in s.modules}
    _assessment(session, student.id, body.assessment_id)
    _check_unique(session, body.assessment_id, b.subject_id, b.id)
    for q in body.questions:
        for m in q.mappings:
            if m.topic_id is not None and m.topic_id not in s.topics:
                raise BreakdownProblem(
                    f"Q{q.label}: that topic is not part of {s.subject.name}. "
                    "Topics come from the subject's curriculum."
                )
            if m.module_id is not None and m.module_id not in module_ids:
                raise BreakdownProblem(f"Q{q.label}: that module is not part of {s.subject.name}.")
    unknown_groups = {q.choice_group for q in body.questions if q.choice_group} - set(
        body.choice_rules
    )
    rules = dict(body.choice_rules)
    for g in unknown_groups:
        if g is not None:
            rules.setdefault(g, 1)

    existing = {q.id: q for q in b.questions}
    # Remove old mappings first: re-adding the same topic in one flush would
    # trip the unique (question, topic) constraint.
    for old in existing.values():
        old.mappings.clear()
    session.flush()
    keep: list[ExamQuestion] = []
    for position, q in enumerate(body.questions):
        found = existing.get(q.id) if q.id else None
        if q.id and found is None:
            raise BreakdownProblem(f"Q{q.label}: unknown question id.")
        row = found if found is not None else ExamQuestion(breakdown_id=b.id)
        row.position = position
        row.label = q.label
        row.section = q.section or None
        row.context = q.context or None
        row.text = q.text
        row.page = q.page
        row.max_marks = _marks(q.max_marks)
        row.marks_obtained = _marks(q.marks_obtained)
        row.attempt_status = q.attempt_status
        row.is_optional = q.is_optional
        row.choice_group = q.choice_group
        row.needs_review = q.needs_review
        for m, share in zip(q.mappings, q.shares(), strict=True):
            row.mappings.append(
                ExamQuestionMapping(
                    topic_id=m.topic_id, module_id=m.module_id, share=share.quantize(SHARE_STEP)
                )
            )
        keep.append(row)
    b.questions[:] = keep
    b.title = body.title
    b.held_on = body.held_on
    b.declared_total = _marks(body.declared_total)
    b.assessment_id = body.assessment_id
    b.choice_rules = rules
    b.updated_at = datetime.now(UTC)
    session.flush()
    if b.status is BreakdownStatus.CONFIRMED:
        if not _counted_any(b):
            raise BreakdownProblem(
                "A confirmed breakdown needs at least one question with maximum marks and a "
                "mark. Return it to draft first if you want to clear the marks."
            )
        sync_evidence(session, b)
    session.commit()
    if b.status is BreakdownStatus.CONFIRMED:
        refresh_student(session, student.id, policy)
    return b


def _inputs(b: ExamBreakdown) -> list[QuestionInput]:
    return [
        QuestionInput(
            id=q.id,
            label=q.label,
            max_marks=q.max_marks,
            marks_obtained=q.marks_obtained,
            attempt_status=q.attempt_status,
            is_optional=q.is_optional,
            needs_review=q.needs_review,
            mappings=tuple(MappingInput(m.topic_id, m.module_id, m.share) for m in q.mappings),
        )
        for q in b.questions
    ]


def compute(session: Session, b: ExamBreakdown) -> tuple[Breakdown, SubjectStructure]:
    s = structure(session, b.subject_id)
    return analyse(_inputs(b), s.topic_module), s


def _counted_any(b: ExamBreakdown) -> bool:
    return any(r.counted for r in analyse(_inputs(b), {}).questions)


# --------------------------------------------------------------------------- #
# Confirm, evidence, delete
# --------------------------------------------------------------------------- #


def confirm(session: Session, policy: Policy, student: Student, b: ExamBreakdown) -> None:
    if not _counted_any(b):
        raise BreakdownProblem(
            "Nothing can be counted yet: enter at least one question with its maximum marks "
            "and the marks you obtained (or mark it as not attempted)."
        )
    b.status = BreakdownStatus.CONFIRMED
    b.confirmed_at = datetime.now(UTC)
    sync_evidence(session, b)
    session.commit()
    refresh_student(session, student.id, policy)


def reopen(session: Session, policy: Policy, student: Student, b: ExamBreakdown) -> None:
    b.status = BreakdownStatus.DRAFT
    b.confirmed_at = None
    sync_evidence(session, b)
    session.commit()
    refresh_student(session, student.id, policy)


def sync_evidence(session: Session, b: ExamBreakdown) -> int:
    """Replace this breakdown's topic evidence with what it currently says."""
    session.execute(delete(TopicEvidence).where(TopicEvidence.exam_breakdown_id == b.id))
    if b.status is not BreakdownStatus.CONFIRMED:
        session.flush()
        return 0
    result, _ = compute(session, b)
    observed = (
        datetime.combine(b.held_on, time(12), tzinfo=UTC)
        if b.held_on
        else (b.confirmed_at or datetime.now(UTC))
    )
    added = 0
    for topic_id, t in result.topics.items():
        if t.possible <= 0:
            continue
        session.add(
            TopicEvidence(
                student_id=b.student_id,
                topic_id=topic_id,
                kind=EvidenceKind.EXAM_BREAKDOWN,
                score=(t.earned / t.possible).quantize(Decimal("0.0001")),
                sample_size=max(len(t.questions), 1),
                exam_breakdown_id=b.id,
                details={
                    "breakdown_id": b.id,
                    "exam": b.title,
                    "assessment_id": b.assessment_id,
                    "subject_id": b.subject_id,
                    "obtained": str(t.earned.quantize(Decimal("0.01"))),
                    "maximum": str(t.possible.quantize(Decimal("0.01"))),
                    "questions": [f"Q{label}" for label in t.questions],
                    "partial": t.partial,
                },
                observed_at=observed,
            )
        )
        added += 1
    session.flush()
    return added


def delete_breakdown(
    session: Session, store: FileStore, policy: Policy, student: Student, b: ExamBreakdown
) -> None:
    session.execute(delete(TopicEvidence).where(TopicEvidence.exam_breakdown_id == b.id))
    _drop_unused_paper(session, store, b.document_id, b.id)
    session.delete(b)
    session.commit()
    refresh_student(session, student.id, policy)


# --------------------------------------------------------------------------- #
# Reconciliation and checks
# --------------------------------------------------------------------------- #


def overall_result(session: Session, b: ExamBreakdown) -> AssessmentResult | None:
    if b.assessment_id is None:
        return None
    return session.scalar(
        select(AssessmentResult)
        .where(
            AssessmentResult.assessment_id == b.assessment_id,
            AssessmentResult.subject_id == b.subject_id,
        )
        .order_by(AssessmentResult.created_at)
    )


def checks(session: Session, b: ExamBreakdown, result: Breakdown) -> list[str]:
    """Warnings for the review and analysis screens. Nothing is overwritten."""
    out: list[str] = []
    attempted: dict[str, set[str]] = {}
    for q in b.questions:
        if q.choice_group and q.attempt_status is AttemptStatus.ATTEMPTED:
            attempted.setdefault(q.choice_group, set()).add(_choice_unit(q.label, q.choice_group))
    for group, units in sorted(attempted.items()):
        allowed = b.choice_rules.get(group)
        if allowed is not None and len(units) > allowed:
            out.append(
                f"{group}: {len(units)} questions are marked attempted but only {allowed} "
                "count. If the examiner counted only some, mark the others as not attempted."
            )
    paper = _paper_total(b)
    if b.declared_total is not None and paper is not None and paper != b.declared_total:
        out.append(
            f"The questions add up to {_fmt(paper)} marks, but the total marks are "
            f"{_fmt(b.declared_total)}. Check the maximum marks and the choice rules."
        )
    official = overall_result(session, b)
    if official is not None and official.marks_obtained is not None:
        o = result.overall
        parts = []
        if official.max_marks is not None and o.possible != official.max_marks:
            parts.append(f"out of {_fmt(o.possible)} instead of {_fmt(official.max_marks)}")
        if o.earned != official.marks_obtained:
            parts.append(f"{_fmt(o.earned)} marks instead of {_fmt(official.marks_obtained)}")
        if parts:
            note = (
                ""
                if result.complete
                else " Some questions are not counted yet, which can explain the difference."
            )
            out.append(
                "The question marks add up to " + " and ".join(parts) + " recorded in your "
                "results for this exam. Your recorded result is unchanged; check the marks "
                "(internal marks or moderation can also explain a difference)." + note
            )
    return out


def _choice_unit(label: str, group: str) -> str:
    """The alternative a question belongs to: its top number, or its part for
    an OR between parts ("Q11(a) or Q11(b)")."""
    if "(" in group:
        return label.split(")")[0] + ")" if ")" in label else label
    digits = ""
    for ch in label:
        if not ch.isdigit():
            break
        digits += ch
    return digits or label


def _paper_total(b: ExamBreakdown) -> Decimal | None:
    """Marks a complete script can earn under the choice rules."""
    if not b.questions or any(q.max_marks is None for q in b.questions):
        return None
    total = sum((q.max_marks or Decimal(0) for q in b.questions if not q.is_optional), Decimal(0))
    groups: dict[str, dict[str, Decimal]] = {}
    for q in b.questions:
        if q.is_optional:
            key = q.choice_group or f"Q{q.label}"
            unit = _choice_unit(q.label, key)
            groups.setdefault(key, {})
            groups[key][unit] = groups[key].get(unit, Decimal(0)) + (q.max_marks or Decimal(0))
    for key, units in groups.items():
        values = set(units.values())
        if len(values) != 1:
            return None
        choose = b.choice_rules.get(key, 1 if key.startswith("Q") else len(units))
        total += values.pop() * min(choose, len(units))
    return total


def _fmt(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")).normalize(), "f")


# --------------------------------------------------------------------------- #
# Views shared by the API
# --------------------------------------------------------------------------- #


def mastery(session: Session, student_id: str) -> dict[str, TopicMastery]:
    return {
        m.topic_id: m
        for m in session.scalars(select(TopicMastery).where(TopicMastery.student_id == student_id))
    }


def plan_positions(session: Session, student_id: str) -> dict[str, int]:
    plan = session.scalar(
        select(StudyPlan)
        .where(StudyPlan.student_id == student_id)
        .order_by(StudyPlan.created_at.desc())
    )
    return {i.topic_id: i.position + 1 for i in plan.items} if plan else {}


def performance_band(t: Tally, policy: Policy) -> Band | None:
    """Exam-performance band (same thresholds as subject marks). Not mastery."""
    f = t.fraction
    if f is None:
        return None
    bands = policy.subject_bands
    if f >= Decimal(str(bands.strong_at)):
        return "strong"
    if f < Decimal(str(bands.attention_below)):
        return "needs_attention"
    return "developing"


def confirmed_breakdowns(session: Session, student_id: str) -> list[ExamBreakdown]:
    return list(
        session.scalars(
            select(ExamBreakdown)
            .where(
                ExamBreakdown.student_id == student_id,
                ExamBreakdown.status == BreakdownStatus.CONFIRMED,
            )
            .options(selectinload(ExamBreakdown.questions).selectinload(ExamQuestion.mappings))
            .order_by(
                ExamBreakdown.held_on.is_(None), ExamBreakdown.held_on, ExamBreakdown.created_at
            )
        )
    )
