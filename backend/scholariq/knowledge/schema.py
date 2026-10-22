"""Schema for knowledge-base files.

Layout::

    content/sources.yaml                     further-reading references
    content/knowledge/<subject>/<topic>.yaml one file per curriculum topic

Each topic file lists concepts. A concept carries its definition, comparison
attributes, graph edges, explanatory documents and quiz questions. Review is
recorded per concept and covers everything inside it: a reviewer records their
name, the date and the concept's content hash. If the content changes after
review, the hash no longer matches and the concept is treated as unreviewed
again (see ``knowledge.review``).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from scholariq.domain.enums import KnowledgeDocumentKind, QuestionKind, QuestionPurpose

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]*$", max_length=160)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpec(Strict):
    slug: Slug
    title: Short
    authors: str | None = None
    citation: str | None = None
    url: str | None = None
    license: str | None = None


class SourcesFile(Strict):
    sources: list[SourceSpec]


class Review(Strict):
    status: Literal["unreviewed", "verified", "retired"] = "unreviewed"
    by: Short | None = None
    on: date | None = None
    # First 12 hex characters of the concept's content hash at review time.
    hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{12}$")] | None = None

    @model_validator(mode="after")
    def _complete(self) -> Review:
        if self.status == "verified" and not (self.by and self.on and self.hash):
            raise ValueError("a verified review needs by, on and hash")
        return self


class DocumentSpec(Strict):
    kind: KnowledgeDocumentKind
    title: Short
    body: Text
    steps: list[Text] = Field(default_factory=list)
    # 1 = first explanation, 2 = more detail, 3 = advanced.
    depth: int = Field(1, ge=1, le=3)


class QuestionSpec(Strict):
    slug: Slug
    kind: QuestionKind
    purpose: QuestionPurpose = QuestionPurpose.DIAGNOSTIC
    style: Literal["conceptual", "application"] = "conceptual"
    difficulty: int = Field(2, ge=1, le=5)
    prompt: Text
    options: list[Text] = Field(default_factory=list)
    answer: dict[str, Any]
    explanation: Text

    @model_validator(mode="after")
    def _answer_shape(self) -> QuestionSpec:
        a = self.answer
        if self.kind is QuestionKind.MULTIPLE_CHOICE:
            # More than six usually means a YAML flow list split an option at a comma.
            if not 2 <= len(self.options) <= 6:
                raise ValueError(f"{self.slug}: a multiple-choice question needs 2 to 6 options")
            if len(set(self.options)) != len(self.options):
                raise ValueError(f"{self.slug}: duplicate options")
            idx = a.get("option_index")
            if set(a) != {"option_index"} or not isinstance(idx, int):
                raise ValueError(f"{self.slug}: answer must be {{option_index: n}}")
            if not 0 <= idx < len(self.options):
                raise ValueError(f"{self.slug}: option_index out of range")
        elif self.kind is QuestionKind.NUMERIC:
            if self.options or not isinstance(a.get("value"), int | float):
                raise ValueError(f"{self.slug}: answer must be {{value: x, tolerance: t}}")
            if set(a) - {"value", "tolerance"}:
                raise ValueError(f"{self.slug}: unexpected answer keys")
        else:
            accepted = a.get("accepted")
            if set(a) != {"accepted"} or not accepted or not isinstance(accepted, list):
                raise ValueError(f"{self.slug}: answer must be {{accepted: [...]}}")
        return self


class ConceptSpec(Strict):
    slug: Slug
    name: Short
    aliases: list[Short] = Field(default_factory=list)
    difficulty: int = Field(2, ge=1, le=5)
    definition: Text
    # Structured facts used for comparisons, e.g. {"ordering": "LIFO"}.
    attributes: dict[str, str] = Field(default_factory=dict)
    requires: list[Slug] = Field(default_factory=list)
    related: list[Slug] = Field(default_factory=list)
    contrasts: list[Slug] = Field(default_factory=list)
    part_of: list[Slug] = Field(default_factory=list)
    further_reading: list[Slug] = Field(default_factory=list)
    documents: list[DocumentSpec] = Field(default_factory=list)
    questions: list[QuestionSpec] = Field(default_factory=list)
    review: Review = Field(default_factory=Review)

    def content_hash(self) -> str:
        """Hash of everything a reviewer vouches for (all fields except review)."""
        payload = self.model_dump(mode="json", exclude={"review"})
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()


class TopicFile(Strict):
    topic: Slug
    version: Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z.\-]+$")]
    concepts: list[ConceptSpec] = Field(min_length=1)
