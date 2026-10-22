from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from scholariq.api.deps import SessionDep, StudentDep
from scholariq.db.models import Assessment, AssessmentResult
from scholariq.domain.enums import ExamType, ResultComponent, ResultStatus

router = APIRouter(prefix="/academics", tags=["academics"])


class ResultOut(BaseModel):
    id: str
    subject_id: str
    subject_name: str
    subject_code: str | None
    component: ResultComponent
    status: ResultStatus
    marks_obtained: Decimal | None
    max_marks: Decimal | None
    grade: str | None
    grade_points: Decimal | None
    credits: Decimal | None
    attempt_number: int
    grading_scale_id: str | None


class AssessmentOut(BaseModel):
    id: str
    document_id: str | None
    semester: int | None
    exam_type: ExamType
    exam_name: str | None
    results: list[ResultOut]


@router.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(student: StudentDep, session: SessionDep) -> list[AssessmentOut]:
    """Confirmed records only, exactly as the student approved them."""
    assessments = session.scalars(
        select(Assessment)
        .where(Assessment.student_id == student.id)
        .options(selectinload(Assessment.results).selectinload(AssessmentResult.subject))
        .order_by(Assessment.semester.is_(None), Assessment.semester, Assessment.created_at)
    ).all()
    return [
        AssessmentOut(
            id=a.id,
            document_id=a.document_id,
            semester=a.semester,
            exam_type=a.exam_type,
            exam_name=a.exam_name,
            results=[
                ResultOut(
                    id=r.id,
                    subject_id=r.subject_id,
                    subject_name=r.subject.name,
                    subject_code=r.subject.code,
                    component=r.component,
                    status=r.status,
                    marks_obtained=r.marks_obtained,
                    max_marks=r.max_marks,
                    grade=r.grade,
                    grade_points=r.grade_points,
                    credits=r.credits,
                    attempt_number=r.attempt_number,
                    grading_scale_id=r.grading_scale_id,
                )
                for r in sorted(a.results, key=lambda r: r.subject.name)
            ],
        )
        for a in assessments
    ]
