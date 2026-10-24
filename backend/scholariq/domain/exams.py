"""Typed input for creating and editing exam breakdowns."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from scholariq.domain.enums import AttemptStatus

Mark = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=2)]
Share = Annotated[Decimal, Field(gt=0, le=1, max_digits=5, decimal_places=4)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Group = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Id = Annotated[str, StringConstraints(min_length=1, max_length=36)]

MAX_QUESTIONS = 300
# Shares of one question must add up to 1 within this tolerance (1/3 + 1/3 + 1/3).
SHARE_TOLERANCE = Decimal("0.005")


class NewBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: Id
    # An exam sitting already in the student's results, when there is one.
    assessment_id: Id | None = None
    title: Title | None = None
    held_on: date | None = None
    declared_total: Mark | None = None

    @model_validator(mode="after")
    def _positive_total(self) -> NewBreakdown:
        if self.declared_total is not None and self.declared_total <= 0:
            raise ValueError("total marks must be greater than zero")
        return self


class MappingIn(BaseModel):
    """A topic, or only a module when the topic is not known."""

    model_config = ConfigDict(extra="forbid")

    topic_id: Id | None = None
    module_id: Id | None = None
    # Share of the question; omitted shares are split equally.
    share: Share | None = None

    @model_validator(mode="after")
    def _one_target(self) -> MappingIn:
        if (self.topic_id is None) == (self.module_id is None):
            raise ValueError("a mapping names either a topic or a module")
        return self


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Id | None = None
    label: Label
    section: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    context: Annotated[str, StringConstraints(max_length=4000)] | None = None
    text: Annotated[str, StringConstraints(max_length=4000)] = ""
    page: Annotated[int, Field(ge=1, le=500)] | None = None
    # Blank means unknown; it never becomes zero.
    max_marks: Mark | None = None
    marks_obtained: Mark | None = None
    attempt_status: AttemptStatus = AttemptStatus.UNKNOWN
    is_optional: bool = False
    choice_group: Group | None = None
    needs_review: bool = False
    mappings: list[MappingIn] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _consistent(self) -> QuestionIn:
        q = f"Q{self.label}"
        if self.max_marks is not None and self.max_marks <= 0:
            raise ValueError(f"{q}: maximum marks must be greater than zero")
        if self.marks_obtained is not None:
            if self.max_marks is None:
                raise ValueError(f"{q}: enter the maximum marks before the marks obtained")
            if self.marks_obtained > self.max_marks:
                raise ValueError(f"{q}: marks obtained exceed the maximum marks")
            if self.attempt_status is AttemptStatus.UNKNOWN:
                # Entering a mark says the question was attempted.
                self.attempt_status = AttemptStatus.ATTEMPTED
            elif self.attempt_status is AttemptStatus.NOT_ATTEMPTED:
                if self.marks_obtained > 0:
                    raise ValueError(f"{q}: a question that was not attempted cannot earn marks")
                self.marks_obtained = None
        targets = [m.topic_id or m.module_id for m in self.mappings]
        if len(targets) != len(set(targets)):
            raise ValueError(f"{q}: the same topic or module is mapped twice")
        given = [m.share for m in self.mappings if m.share is not None]
        if self.mappings and len(given) == len(self.mappings):
            if abs(sum(given, Decimal(0)) - 1) > SHARE_TOLERANCE:
                raise ValueError(f"{q}: the topic shares must add up to 100%")
        elif given:
            raise ValueError(f"{q}: give a share for every mapping, or for none")
        return self

    def shares(self) -> list[Decimal]:
        """Each mapping's share; equal shares when none were given."""
        n = len(self.mappings)
        if n == 0:
            return []
        if all(m.share is not None for m in self.mappings):
            return [m.share for m in self.mappings if m.share is not None]
        each = (Decimal(1) / n).quantize(Decimal("0.0001"))
        return [each] * (n - 1) + [Decimal(1) - each * (n - 1)]


class BreakdownUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    held_on: date | None = None
    declared_total: Mark | None = None
    assessment_id: Id | None = None
    choice_rules: dict[Group, Annotated[int, Field(ge=1, le=50)]] = Field(default_factory=dict)
    questions: list[QuestionIn] = Field(max_length=MAX_QUESTIONS)

    @model_validator(mode="after")
    def _unique_labels(self) -> BreakdownUpdate:
        if self.declared_total is not None and self.declared_total <= 0:
            raise ValueError("total marks must be greater than zero")
        labels = [q.label.lower() for q in self.questions]
        dupes = sorted({x for x in labels if labels.count(x) > 1})
        if dupes:
            raise ValueError("question numbers must be unique: " + ", ".join(dupes))
        return self
