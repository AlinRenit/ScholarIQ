"""Import workflow: upload -> extract -> interpret -> review -> confirm.

Only ``confirm_import`` writes academic records, and only from values the
student approved.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from scholariq.analytics.policy import load_policy
from scholariq.analytics.service import refresh_student
from scholariq.core.config import Settings
from scholariq.curriculum.matching import match_subject
from scholariq.curriculum.schema import normalise_name
from scholariq.db.models import (
    Assessment,
    AssessmentResult,
    Document,
    ExtractedRecord,
    GradingScale,
    Student,
    Subject,
)
from scholariq.domain.enums import DocumentStatus, ExamType, GradingScaleKind
from scholariq.domain.imports import ConfirmImport, GradingChoice
from scholariq.ingestion.extract import ExtractionError, extract
from scholariq.ingestion.grade_scales import TEMPLATES
from scholariq.ingestion.interpret import REVIEW_THRESHOLD, interpret
from scholariq.ingestion.storage import FileStore
from scholariq.ingestion.validation import validate_upload

logger = logging.getLogger(__name__)


class ImportProblem(Exception):
    """A user-facing import problem."""


class DuplicateUpload(ImportProblem):
    def __init__(self, document: Document) -> None:
        super().__init__("This file has already been uploaded.")
        self.document = document


class InvalidState(ImportProblem):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def import_document(
    session: Session,
    settings: Settings,
    store: FileStore,
    student: Student,
    filename: str | None,
    data: bytes,
) -> Document:
    upload = validate_upload(filename, data, settings.max_upload_bytes)
    digest = hashlib.sha256(upload.data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.student_id == student.id, Document.sha256 == digest)
    )
    if existing is not None:
        raise DuplicateUpload(existing)

    doc = Document(
        student_id=student.id,
        original_filename=upload.filename,
        media_type=upload.media_type,
        size_bytes=len(upload.data),
        sha256=digest,
        storage_key=store.save(upload.data),
        status=DocumentStatus.UPLOADED,
        retain_until=_utcnow() + timedelta(days=settings.upload_retention_days),
    )
    session.add(doc)
    session.flush()

    try:
        content = extract(upload, settings.tesseract_cmd)
    except ExtractionError as exc:
        doc.status = DocumentStatus.FAILED
        doc.error = str(exc)
        # A file we cannot read is not worth keeping.
        store.delete(doc.storage_key)
        doc.storage_key = None
        session.commit()
        return doc

    result = interpret(content)
    doc.parser_name = result.parser
    doc.analysis = {
        "source": content.source.value,
        "pages": content.pages,
        "notes": content.notes,
        "warnings": result.warnings,
        "grades_seen": result.grades_seen,
        "context": {
            "semester": result.context.semester,
            "exam_type": result.context.exam_type.value,
            "exam_name": result.context.exam_name,
        },
        "review_threshold": REVIEW_THRESHOLD,
    }
    for i, cand in enumerate(result.candidates):
        session.add(
            ExtractedRecord(
                document_id=doc.id,
                row_index=i,
                source_text=cand.source_text[:500],
                fields=cand.fields,
                field_confidence=cand.confidence,
                warnings=cand.warnings,
            )
        )
    doc.status = DocumentStatus.EXTRACTED
    session.commit()
    logger.info("document %s extracted with %s (%d rows)", doc.id, result.parser,
                len(result.candidates))  # fmt: skip
    return doc


def _slugify(name: str) -> str:
    return normalise_name(name).replace(" ", "-")[:70] or "subject"


def resolve_subject(session: Session, name: str, code: str | None) -> Subject:
    """Find a known subject by code, name, alias or close spelling; otherwise
    create a custom subject that the student can map later."""
    subjects = session.scalars(select(Subject)).all()
    if (found := match_subject(subjects, name, code)) is not None:
        if code and not found.code and found.is_custom:
            found.code = code
        return found
    slug = base = f"custom-{_slugify(name)}"
    n = 2
    while session.scalar(select(Subject.id).where(Subject.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    subject = Subject(slug=slug, name=name.strip(), code=code, aliases=[], is_custom=True)
    session.add(subject)
    session.flush()
    return subject


def _grading_scale(
    session: Session, student: Student, choice: GradingChoice
) -> tuple[GradingScale, dict[str, Decimal]]:
    if choice.template is not None:
        tpl = TEMPLATES.get(choice.template)
        if tpl is None:
            raise ImportProblem(f"Unknown grading scale template '{choice.template}'.")
        scale = session.scalar(select(GradingScale).where(GradingScale.template_key == tpl.key))
        if scale is None:
            scale = GradingScale(
                template_key=tpl.key,
                name=tpl.name,
                kind=GradingScaleKind.LETTER,
                definition={k: str(v) for k, v in tpl.points.items()},
                max_grade_points=tpl.max_points,
                verified=True,
            )
            session.add(scale)
            session.flush()
        return scale, dict(tpl.points)
    assert choice.custom is not None
    scale = GradingScale(
        student_id=student.id,
        name=choice.custom.name,
        kind=GradingScaleKind.LETTER,
        definition={k: str(v) for k, v in choice.custom.points.items()},
        max_grade_points=choice.custom.max_points,
        verified=True,
    )
    session.add(scale)
    session.flush()
    return scale, dict(choice.custom.points)


def confirm_import(
    session: Session, settings: Settings, store: FileStore, student: Student, doc: Document,
    payload: ConfirmImport,
) -> list[AssessmentResult]:  # fmt: skip
    if doc.status is not DocumentStatus.EXTRACTED:
        raise InvalidState(f"This document is {doc.status.value} and cannot be confirmed.")
    if (doc.analysis or {}).get("kind") == "question_paper":
        raise InvalidState("This is a question paper; it is used by an exam breakdown.")

    scale: GradingScale | None = None
    points: dict[str, Decimal] = {}
    if payload.grading is not None:
        scale, points = _grading_scale(session, student, payload.grading)
        unknown = sorted({r.grade for r in payload.results if r.grade and r.grade not in points})
        if unknown:
            raise ImportProblem(
                "These grades are not in the selected scale: " + ", ".join(unknown) + "."
            )

    assessments: dict[tuple[int | None, ExamType, str | None], Assessment] = {}
    saved: list[AssessmentResult] = []
    for row in payload.results:
        key = (row.semester, row.exam_type, row.exam_name)
        if key not in assessments:
            assessments[key] = Assessment(
                student_id=student.id,
                document_id=doc.id,
                semester=row.semester,
                exam_type=row.exam_type,
                exam_name=row.exam_name,
            )
            session.add(assessments[key])
        subject = resolve_subject(session, row.subject_name, row.subject_code)
        # Attempts from earlier imports, plus rows already added in this one.
        prior = (
            session.scalar(
                select(func.count(AssessmentResult.id))
                .join(Assessment)
                .where(
                    Assessment.student_id == student.id,
                    or_(Assessment.document_id.is_(None), Assessment.document_id != doc.id),
                    AssessmentResult.subject_id == subject.id,
                    AssessmentResult.component == row.component,
                )
            )
            or 0
        )
        prior += sum(
            1 for r in saved if r.subject_id == subject.id and r.component == row.component
        )
        grade_points = row.grade_points
        if grade_points is None and row.grade and row.grade in points:
            grade_points = points[row.grade]
        result = AssessmentResult(
            assessment=assessments[key],
            subject_id=subject.id,
            component=row.component,
            status=row.status,
            marks_obtained=row.marks_obtained,
            max_marks=row.max_marks,
            grade=row.grade,
            grade_points=grade_points,
            credits=row.credits,
            grading_scale_id=scale.id if scale and row.grade else None,
            attempt_number=prior + 1,
            subject_label_as_printed=row.subject_name,
            verified_by_student=True,
        )
        session.add(result)
        saved.append(result)

    doc.status = DocumentStatus.CONFIRMED
    # Raw extraction text is no longer needed once the student has confirmed.
    session.execute(delete(ExtractedRecord).where(ExtractedRecord.document_id == doc.id))
    if settings.upload_retention_days == 0:
        store.delete(doc.storage_key)
        doc.storage_key = None
    session.commit()
    refresh_student(session, student.id, load_policy(settings.content_dir))
    return saved


def delete_document(session: Session, settings: Settings, store: FileStore, doc: Document) -> None:
    """Delete an upload together with every result imported from it."""
    student_id = doc.student_id
    session.execute(delete(Assessment).where(Assessment.document_id == doc.id))
    store.delete(doc.storage_key)
    session.delete(doc)
    session.commit()
    refresh_student(session, student_id, load_policy(settings.content_dir))


def delete_student_data(session: Session, store: FileStore, student: Student) -> None:
    for doc in session.scalars(select(Document).where(Document.student_id == student.id)):
        store.delete(doc.storage_key)
    session.delete(student)
    session.commit()


def purge_expired_files(session: Session, store: FileStore, now: datetime | None = None) -> int:
    now = now or _utcnow()
    expired = session.scalars(
        select(Document).where(Document.storage_key.is_not(None), Document.retain_until <= now)
    ).all()
    for doc in expired:
        store.delete(doc.storage_key)
        doc.storage_key = None
    session.commit()
    return len(expired)
