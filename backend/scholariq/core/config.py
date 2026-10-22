"""Typed, validated application configuration.

Settings come from environment variables prefixed with ``SCHOLARIQ_`` (or a
``.env`` file). Invalid combinations fail at startup instead of at first use.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder accepted only outside production (see _consistent).
DEV_SECRET_KEY = "dev-insecure-change-me"  # noqa: S105


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class DeploymentMode(StrEnum):
    # Multi-user server backed by PostgreSQL.
    SERVER = "server"
    # Single-user offline install backed by SQLite.
    OFFLINE = "offline"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCHOLARIQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    deployment_mode: DeploymentMode = DeploymentMode.SERVER

    database_url: str = "postgresql+psycopg://scholariq:scholariq@localhost:5432/scholariq"

    # Uploaded documents are stored here, outside any web-served directory.
    upload_dir: Path = Path("./var/uploads")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    # Days to keep uploaded source files after import is confirmed. 0 deletes on confirm.
    upload_retention_days: int = Field(default=30, ge=0, le=3650)

    # Directory holding the versioned knowledge-base content (YAML/Markdown).
    content_dir: Path = Path("../content")

    # Optional explicit path to the tesseract binary; otherwise PATH is searched.
    tesseract_cmd: str | None = None

    # Origins allowed to call the API from a browser.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Required outside development/test; signs session cookies.
    secret_key: str = DEV_SECRET_KEY

    # Refuse to start when AI-provider credentials are present in the environment.
    strict_ai_env_check: bool = True
    # Whether knowledge-base entries that no person has reviewed yet may be used
    # by search, the tutor and quizzes. They are always labelled as unreviewed.
    allow_unreviewed_content: bool = True

    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _supported_database(cls, value: str) -> str:
        if not value.startswith(("postgresql", "sqlite")):
            raise ValueError("database_url must be a PostgreSQL or SQLite SQLAlchemy URL")
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        upper = value.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"unknown log level: {value}")
        return upper

    @model_validator(mode="after")
    def _consistent(self) -> Settings:
        if self.deployment_mode is DeploymentMode.OFFLINE and not self.is_sqlite:
            raise ValueError("offline deployment mode requires a SQLite database_url")
        if self.environment is Environment.PRODUCTION:
            if self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < 32:
                raise ValueError("production requires SCHOLARIQ_SECRET_KEY of at least 32 chars")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
