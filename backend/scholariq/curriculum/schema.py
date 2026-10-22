"""Schema for curriculum files in content/curriculum/*.yaml."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]*$", max_length=120)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TopicSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Name
    importance: int = Field(default=3, ge=1, le=5)
    minutes: int | None = Field(default=None, gt=0, le=10_000)
    summary: str | None = None


class SubjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Name
    codes: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    topics: list[TopicSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_topics(self) -> SubjectSpec:
        slugs = [t.slug for t in self.topics]
        if len(slugs) != len(set(slugs)):
            raise ValueError(f"{self.slug}: duplicate topic slugs")
        return self


class CurriculumMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Name
    version: Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z.\-]+$")]


class CurriculumFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum: CurriculumMeta
    subjects: list[SubjectSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> CurriculumFile:
        slugs = [s.slug for s in self.subjects]
        if len(slugs) != len(set(slugs)):
            raise ValueError("duplicate subject slugs")
        names: dict[str, str] = {}
        for subject in self.subjects:
            for t in subject.topics:
                if names.setdefault(t.slug, t.name) != t.name:
                    raise ValueError(f"topic {t.slug} has two different names")
        return self


def normalise_name(name: str) -> str:
    text = name.lower().replace(".", "").replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
