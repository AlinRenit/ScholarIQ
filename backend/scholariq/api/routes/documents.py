from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from scholariq.api.deps import SessionDep, SettingsDep, StoreDep, StudentDep, upload_limiter
from scholariq.db.models import Document, ExtractedRecord
from scholariq.domain.enums import DocumentStatus
from scholariq.domain.imports import ConfirmImport
from scholariq.ingestion.grade_scales import TEMPLATES
from scholariq.ingestion.service import (
    DuplicateUpload,
    ImportProblem,
    InvalidState,
    confirm_import,
    delete_document,
    import_document,
    purge_expired_files,
)
from scholariq.ingestion.validation import UploadRejected

router = APIRouter(prefix="/documents", tags=["import"])


class RecordOut(BaseModel):
    id: str
    row_index: int
    source_text: str | None
    fields: dict[str, Any]
    confidence: dict[str, float]
    warnings: list[str]


class DocumentOut(BaseModel):
    id: str
    original_filename: str
    media_type: str
    size_bytes: int
    status: DocumentStatus
    parser_name: str | None
    error: str | None
    created_at: datetime
    file_retained: bool
    analysis: dict[str, Any]


class DocumentDetail(DocumentOut):
    records: list[RecordOut]


class ScaleTemplateOut(BaseModel):
    key: str
    name: str
    description: str
    max_points: Decimal
    points: dict[str, Decimal]


class ConfirmOut(BaseModel):
    document_id: str
    results_saved: int


def _doc_out(doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        original_filename=doc.original_filename,
        media_type=doc.media_type,
        size_bytes=doc.size_bytes,
        status=doc.status,
        parser_name=doc.parser_name,
        error=doc.error,
        created_at=doc.created_at,
        file_retained=doc.storage_key is not None,
        analysis=doc.analysis or {},
    )


def _detail(session: SessionDep, doc: Document) -> DocumentDetail:
    records = session.scalars(
        select(ExtractedRecord)
        .where(ExtractedRecord.document_id == doc.id)
        .order_by(ExtractedRecord.row_index)
    ).all()
    return DocumentDetail(
        **_doc_out(doc).model_dump(),
        records=[
            RecordOut(
                id=r.id,
                row_index=r.row_index,
                source_text=r.source_text,
                fields=r.fields,
                confidence=r.field_confidence,
                warnings=r.warnings,
            )
            for r in records
        ],
    )


def _owned(session: SessionDep, student_id: str, document_id: str) -> Document:
    doc = session.get(Document, document_id)
    # Same response for "missing" and "not yours", so ids cannot be probed.
    if doc is None or doc.student_id != student_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return doc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentDetail)
async def upload(
    file: UploadFile,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> DocumentDetail:
    if not upload_limiter.allow(student.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many uploads; try later.")
    # Read one byte past the limit so oversize files are rejected without
    # buffering arbitrarily large bodies.
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        doc = import_document(session, settings, store, student, file.filename, data)
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except DuplicateUpload as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": str(exc), "document_id": exc.document.id},
        ) from exc
    purge_expired_files(session, store)
    return _detail(session, doc)


@router.get("", response_model=list[DocumentOut])
def list_documents(student: StudentDep, session: SessionDep) -> list[DocumentOut]:
    docs = session.scalars(
        select(Document)
        .where(Document.student_id == student.id)
        .order_by(Document.created_at.desc())
    ).all()
    # Question papers belong to exam breakdowns and are managed there.
    return [_doc_out(d) for d in docs if (d.analysis or {}).get("kind") != "question_paper"]


@router.get("/grading-scales", response_model=list[ScaleTemplateOut])
def grading_scale_templates() -> list[ScaleTemplateOut]:
    return [
        ScaleTemplateOut(
            key=t.key,
            name=t.name,
            description=t.description,
            max_points=t.max_points,
            points=t.points,
        )  # fmt: skip
        for t in TEMPLATES.values()
    ]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, student: StudentDep, session: SessionDep) -> DocumentDetail:
    return _detail(session, _owned(session, student.id, document_id))


@router.post("/{document_id}/confirm", response_model=ConfirmOut)
def confirm(
    document_id: str,
    body: ConfirmImport,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> ConfirmOut:
    doc = _owned(session, student.id, document_id)
    try:
        saved = confirm_import(session, settings, store, student, doc, body)
    except InvalidState as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ImportProblem as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return ConfirmOut(document_id=doc.id, results_saved=len(saved))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    document_id: str,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
) -> None:
    delete_document(session, settings, store, _owned(session, student.id, document_id))
