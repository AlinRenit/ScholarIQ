from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scholariq import __version__
from scholariq.api.routes import academics, documents, health, profile, system
from scholariq.compliance.runtime import enforce_environment
from scholariq.core.config import Settings, get_settings
from scholariq.core.logging import configure_logging

logger = logging.getLogger("scholariq")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    found = enforce_environment(settings.strict_ai_env_check)
    if found:
        logger.warning("AI provider variables present and ignored: %s", ", ".join(found))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(
        title="ScholarIQ API",
        version=__version__,
        description="Deterministic academic analysis and tutoring. No external AI services.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(academics.router, prefix="/api")
    return app
