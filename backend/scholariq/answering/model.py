"""The structured answer every handler returns.

Text inside a section is either copied from the knowledge base (and names the
concept and document it came from) or produced by a named solver. Headings and
connecting sentences come from fixed templates in the handlers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from scholariq.domain.enums import TrustStatus

RULES_VERSION = "tutor-rules/1"

SectionKind = Literal[
    "definition",
    "facts",
    "explanation",
    "procedure",
    "example",
    "misconception",
    "check",
    "table",
    "list",
    "steps",
    "code",
    "note",
    "summary",
]


class Origin(BaseModel):
    """Where a section's content came from."""

    kind: Literal["knowledge", "solver", "analysis", "template"]
    concept: str | None = None  # concept slug
    document: str | None = None  # knowledge document slug
    solver: str | None = None
    trust: TrustStatus | None = None


class Item(BaseModel):
    text: str
    detail: str | None = None
    concept: str | None = None  # link target (concept slug)
    topic: str | None = None  # link target (topic slug)


class CheckQuestion(BaseModel):
    slug: str
    prompt: str
    kind: str
    options: list[str] = Field(default_factory=list)


class Section(BaseModel):
    kind: SectionKind
    title: str
    text: str | None = None
    steps: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    items: list[Item] = Field(default_factory=list)
    code: str | None = None
    question: CheckQuestion | None = None
    origin: Origin


class ConceptRef(BaseModel):
    slug: str
    name: str
    topic_slug: str
    topic_name: str
    trust: TrustStatus


class Reading(BaseModel):
    title: str
    authors: str | None = None
    citation: str | None = None
    url: str | None = None


class Suggestion(BaseModel):
    label: str
    # Either a canned action on the current answer, or a new question to ask.
    action: Literal["simplify", "example", "check", "deeper", "ask"]
    query: str | None = None
    # For a clarifying question's options: the meaning this option stands for.
    concept: str | None = None


class Clarification(BaseModel):
    question: str
    options: list[Suggestion]


class Personalisation(BaseModel):
    topic: str | None = None
    classification: str | None = None
    level: Literal["overview", "balanced", "guided", "deeper"] = "balanced"
    explanation: str


class Review(BaseModel):
    all_reviewed: bool
    label: str | None = None
    unreviewed: list[str] = Field(default_factory=list)


class Answer(BaseModel):
    status: Literal["answered", "clarify", "abstained"]
    handler: str
    handler_label: str
    intent: str
    concepts: list[ConceptRef] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    review: Review = Field(default_factory=lambda: Review(all_reviewed=True))
    personalisation: Personalisation | None = None
    interpretation: list[str] = Field(default_factory=list)
    clarification: Clarification | None = None
    missing: str | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)
    further_reading: list[Reading] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    rules_version: str = RULES_VERSION
