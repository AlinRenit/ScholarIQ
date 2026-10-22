"""Typed models for the import review and confirmation flow."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from scholariq.domain.enums import ExamType, ResultComponent, ResultStatus

Mark = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=2)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
GradeText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8)]


class ConfirmedResult(BaseModel):
    """One row as the student approved it on the review screen."""

    model_config = ConfigDict(extra="forbid")

    subject_name: ShortText
    subject_code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = (
        None
    )
    component: ResultComponent = ResultComponent.COMBINED
    status: ResultStatus = ResultStatus.PRESENT
    marks_obtained: Mark | None = None
    max_marks: Mark | None = None
    grade: GradeText | None = None
    grade_points: Mark | None = None
    credits: Annotated[Decimal, Field(ge=0, le=30, max_digits=5, decimal_places=2)] | None = None
    semester: Annotated[int, Field(ge=1, le=12)] | None = None
    exam_type: ExamType = ExamType.UNKNOWN
    exam_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = (
        None
    )

    @model_validator(mode="after")
    def _consistent(self) -> ConfirmedResult:
        if self.status is ResultStatus.PRESENT:
            if self.marks_obtained is None and self.grade is None:
                raise ValueError(
                    f"{self.subject_name}: a present result needs marks or a grade; "
                    "mark it as missing if neither is known"
                )
        elif self.marks_obtained is not None:
            raise ValueError(
                f"{self.subject_name}: marks cannot be recorded for a {self.status.value} result"
            )
        if self.max_marks is not None and self.max_marks <= 0:
            raise ValueError(f"{self.subject_name}: maximum marks must be greater than zero")
        if (
            self.marks_obtained is not None
            and self.max_marks is not None
            and self.marks_obtained > self.max_marks
        ):
            raise ValueError(f"{self.subject_name}: marks obtained exceed maximum marks")
        if self.grade is not None:
            self.grade = self.grade.upper()
        return self


class CustomScale(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ShortText
    max_points: Annotated[Decimal, Field(gt=0, le=100)]
    points: dict[GradeText, Annotated[Decimal, Field(ge=0, le=100)]] = Field(min_length=1)

    @model_validator(mode="after")
    def _within_max(self) -> CustomScale:
        self.points = {k.upper(): v for k, v in self.points.items()}
        if any(v > self.max_points for v in self.points.values()):
            raise ValueError("grade points cannot exceed the scale maximum")
        return self


class GradingChoice(BaseModel):
    """How the student says this document's grades should be read."""

    model_config = ConfigDict(extra="forbid")

    template: str | None = None
    custom: CustomScale | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> GradingChoice:
        if (self.template is None) == (self.custom is None):
            raise ValueError("choose a template or define a custom scale, not both")
        return self


class ConfirmImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[ConfirmedResult] = Field(min_length=1, max_length=500)
    # Optional: without it grades are stored as printed and never converted.
    grading: GradingChoice | None = None
