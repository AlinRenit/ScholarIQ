from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.base import RequestResponseEndpoint

from scholariq import __version__
from scholariq.api.routes import (
    academics,
    analytics,
    curriculum,
    documents,
    health,
    knowledge,
    plan,
    practice,
    profile,
    system,
    topics,
    tutor,
)
from scholariq.compliance.runtime import enforce_environment
from scholariq.core.config import Environment, Settings, get_settings
from scholariq.core.logging import configure_logging
from scholariq.db.session import get_engine
from scholariq.tutoring.service import warm_up

logger = logging.getLogger("scholariq")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    found = enforce_environment(settings.strict_ai_env_check)
    if found:
        logger.warning("AI provider variables present and ignored: %s", ", ".join(found))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        if settings.warm_caches_on_start:
            engine = app.dependency_overrides.get(get_engine, get_engine)()
            try:
                with Session(engine) as session:
                    warm_up(session, settings)
            except Exception:  # an unmigrated or empty database must not stop start-up
                logger.warning("Could not prepare the tutor index at start-up", exc_info=True)
        yield

    app = FastAPI(
        title="ScholarIQ API",
        version=__version__,
        description="Deterministic academic analysis and tutoring. No external AI services.",
        lifespan=lifespan,
        # Interactive API docs only outside production.
        docs_url=None if settings.environment is Environment.PRODUCTION else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment is Environment.PRODUCTION else "/openapi.json",
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # API responses hold personal data; never let a shared cache keep them.
        response.headers.setdefault("Cache-Control", "no-store")
        return response

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
    app.include_router(analytics.router, prefix="/api")
    app.include_router(curriculum.router, prefix="/api")
    app.include_router(topics.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(tutor.router, prefix="/api")
    app.include_router(practice.router, prefix="/api")
    app.include_router(plan.router, prefix="/api")
    return app
