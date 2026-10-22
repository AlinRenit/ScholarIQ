from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from scholariq.analytics.policy import Policy, load_policy
from scholariq.core.config import Settings, get_settings
from scholariq.core.ratelimit import RateLimiter
from scholariq.core.security import COOKIE_NAME, unsign
from scholariq.db.models import Student
from scholariq.db.session import get_session
from scholariq.ingestion.storage import FileStore

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]

# Uploads run parsers and OCR locally; cap them per student.
upload_limiter = RateLimiter(limit=20, window_seconds=600)


def get_store(settings: SettingsDep) -> Iterator[FileStore]:
    yield FileStore(settings.upload_dir)


StoreDep = Annotated[FileStore, Depends(get_store)]


def get_policy(settings: SettingsDep) -> Policy:
    return load_policy(settings.content_dir)


PolicyDep = Annotated[Policy, Depends(get_policy)]


def current_student(
    settings: SettingsDep,
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Student:
    student_id = unsign(settings.secret_key, token)
    student = session.get(Student, student_id) if student_id else None
    if student is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No profile. Create one to continue.")
    return student


StudentDep = Annotated[Student, Depends(current_student)]
