from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, StringConstraints

from scholariq.api.deps import SessionDep, SettingsDep, StoreDep, StudentDep
from scholariq.core.config import Environment
from scholariq.core.security import COOKIE_MAX_AGE, COOKIE_NAME, sign
from scholariq.db.models import Student
from scholariq.ingestion.service import delete_student_data

router = APIRouter(tags=["profile"])


class CreateProfile(BaseModel):
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    # The student must accept the privacy notice to store academic data.
    consent: Literal[True]


class ProfileOut(BaseModel):
    id: str
    display_name: str
    consented_at: datetime | None


def _out(s: Student) -> ProfileOut:
    return ProfileOut(id=s.id, display_name=s.display_name, consented_at=s.consented_at)


@router.post("/profile", status_code=status.HTTP_201_CREATED, response_model=ProfileOut)
def create_profile(
    body: CreateProfile, response: Response, session: SessionDep, settings: SettingsDep
) -> ProfileOut:
    student = Student(display_name=body.display_name, consented_at=datetime.now(UTC), goals=[])
    session.add(student)
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        sign(settings.secret_key, student.id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.environment is Environment.PRODUCTION,
        path="/",
    )
    return _out(student)


@router.get("/profile", response_model=ProfileOut)
def get_profile(student: StudentDep) -> ProfileOut:
    return _out(student)


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_data(
    student: StudentDep, session: SessionDep, store: StoreDep, response: Response
) -> None:
    """Delete the profile, every uploaded file, and all derived records."""
    delete_student_data(session, store, student)
    response.delete_cookie(COOKIE_NAME, path="/")
