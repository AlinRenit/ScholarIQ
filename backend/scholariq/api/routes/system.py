from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from scholariq import __version__
from scholariq.core.capabilities import CAPABILITIES, Capability
from scholariq.core.config import DeploymentMode, Settings, get_settings

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfo(BaseModel):
    name: str
    version: str
    deployment_mode: DeploymentMode
    intelligence: str
    uses_external_ai: bool
    capabilities: list[Capability]


@router.get("/info", response_model=SystemInfo)
def info(settings: Annotated[Settings, Depends(get_settings)]) -> SystemInfo:
    return SystemInfo(
        name="ScholarIQ",
        version=__version__,
        deployment_mode=settings.deployment_mode,
        intelligence="local deterministic algorithms and a curated knowledge base",
        uses_external_ai=False,
        capabilities=CAPABILITIES,
    )
