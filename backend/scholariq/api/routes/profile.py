from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select

from scholariq.api.deps import (
    SessionDep,
    SettingsDep,
    StoreDep,
    StudentDep,
    login_limiter,
    login_limiter_total,
)
from scholariq.core.config import Environment, Settings
from scholariq.core.security import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    hash_password,
    sign,
    verify_password,
)
from scholariq.db.models import Student
from scholariq.ingestion.service import delete_student_data

router = APIRouter(tags=["profile"])

Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
Password = Annotated[str, StringConstraints(min_length=10, max_length=200)]


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
    # Sign-in name, when the student has set a password.
    email: str | None = None
    has_password: bool = False


def _out(s: Student) -> ProfileOut:
    return ProfileOut(
        id=s.id,
        display_name=s.display_name,
        consented_at=s.consented_at,
        email=s.email,
        has_password=s.password_hash is not None,
    )


def _set_cookie(response: Response, settings: Settings, student: Student) -> None:
    response.set_cookie(
        COOKIE_NAME,
        sign(settings.secret_key, student.id, student.session_version),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.environment is Environment.PRODUCTION,
        path="/",
    )


@router.post("/profile", status_code=status.HTTP_201_CREATED, response_model=ProfileOut)
def create_profile(
    body: CreateProfile, response: Response, session: SessionDep, settings: SettingsDep
) -> ProfileOut:
    student = Student(display_name=body.display_name, consented_at=datetime.now(UTC), goals=[])
    session.add(student)
    session.commit()
    _set_cookie(response, settings, student)
    return _out(student)


@router.get("/profile", response_model=ProfileOut)
def get_profile(student: StudentDep) -> ProfileOut:
    return _out(student)


class CredentialsIn(BaseModel):
    email: Email
    password: Password
    # Required when the profile already has a password.
    current_password: Annotated[str, StringConstraints(max_length=200)] | None = None


@router.put("/profile/credentials", response_model=ProfileOut)
def set_credentials(
    body: CredentialsIn,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> ProfileOut:
    """Set or change the sign-in email and password. Other browsers are signed out."""
    if student.password_hash is not None and not verify_password(
        body.current_password or "", student.password_hash
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your current password is not correct.")
    taken = session.scalar(
        select(Student.id).where(func.lower(Student.email) == body.email, Student.id != student.id)
    )
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is used by another profile.")
    student.email = body.email
    student.password_hash = hash_password(body.password)
    student.session_version += 1
    session.commit()
    _set_cookie(response, settings, student)
    return _out(student)


class LoginIn(BaseModel):
    email: Email
    password: Annotated[str, StringConstraints(max_length=200)]


@router.post("/profile/login", response_model=ProfileOut)
def login(
    body: LoginIn, session: SessionDep, settings: SettingsDep, response: Response
) -> ProfileOut:
    if not (login_limiter.allow(body.email) and login_limiter_total.allow("all")):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many sign-in attempts. Try again later."
        )
    student = session.scalar(select(Student).where(func.lower(Student.email) == body.email))
    if not verify_password(body.password, student.password_hash if student else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is not correct.")
    assert student is not None
    _set_cookie(response, settings, student)
    return _out(student)


class LogoutIn(BaseModel):
    # Also invalidate every other browser's session for this profile.
    everywhere: bool = False


@router.post("/profile/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutIn, student: StudentDep, session: SessionDep, response: Response) -> None:
    if student.password_hash is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set a password first; without one you could not get back into this profile.",
        )
    if body.everywhere:
        student.session_version += 1
        session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.delete("/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_data(
    student: StudentDep, session: SessionDep, store: StoreDep, response: Response
) -> None:
    """Delete the profile, every uploaded file, and all derived records."""
    delete_student_data(session, store, student)
    response.delete_cookie(COOKIE_NAME, path="/")
