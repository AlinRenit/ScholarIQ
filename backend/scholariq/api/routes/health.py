from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine

from scholariq.core import health
from scholariq.core.config import Settings, get_settings
from scholariq.db.session import get_engine

router = APIRouter(prefix="/health", tags=["health"])


class CheckOut(BaseModel):
    name: str
    status: health.CheckStatus
    detail: str
    required: bool


class ReadinessOut(BaseModel):
    status: health.CheckStatus
    checks: list[CheckOut]


@router.get("/live")
def live() -> dict[str, str]:
    """Process is up. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/ready", response_model=ReadinessOut)
def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    engine: Annotated[Engine, Depends(get_engine)],
) -> ReadinessOut:
    results = [
        health.check_database(engine),
        health.check_upload_dir(settings),
        health.check_content_dir(settings),
        health.check_ocr(settings),
        health.check_ai_compliance(),
    ]
    state = health.overall(results)
    if state is health.CheckStatus.FAILED:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessOut(
        status=state,
        checks=[CheckOut(**r.__dict__) for r in results],
    )
