"""Configurable thresholds for analytics and topic classification.

Defaults live here; a deployment can override any value in
``content/policy.yaml``. Every classification stores the policy version it was
computed with, so changing thresholds is auditable.

These thresholds are teaching conventions, not calibrated probabilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Fraction = Annotated[float, Field(ge=0, le=1)]


class SubjectBands(BaseModel):
    """Exam-performance bands for a subject's score (fraction of maximum)."""

    model_config = ConfigDict(extra="forbid")

    strong_at: Fraction = 0.75
    attention_below: Fraction = 0.50

    @model_validator(mode="after")
    def _ordered(self) -> SubjectBands:
        if self.attention_below >= self.strong_at:
            raise ValueError("attention_below must be lower than strong_at")
        return self


class EvidenceWeights(BaseModel):
    """How many observations one evidence item counts as, per unit of sample size."""

    model_config = ConfigDict(extra="forbid")

    topic_exam: float = Field(1.0, ge=0)
    diagnostic: float = Field(1.0, ge=0)
    practice: float = Field(0.6, ge=0)
    self_report: float = Field(0.5, ge=0)
    # A subject mark says little about any single topic: it counts as one
    # observation at most, however large the exam was.
    subject_score_prior: float = Field(1.0, ge=0)


class TopicRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Topic-level observations (diagnostic/practice questions, topic exam items)
    # required before a topic can be classified at all.
    min_direct_observations: int = Field(5, ge=1)
    strong_at: Fraction = 0.75
    attention_below: Fraction = 0.50
    # Evidence older than this many days counts half as much.
    half_life_days: float = Field(180, gt=0)
    weights: EvidenceWeights = Field(default_factory=EvidenceWeights)

    @model_validator(mode="after")
    def _ordered(self) -> TopicRules:
        if self.attention_below >= self.strong_at:
            raise ValueError("attention_below must be lower than strong_at")
        return self


class TrendRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Change in semester score (percentage points) needed to call a trend.
    min_change_points: float = Field(3.0, ge=0)


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "policy/1"
    subject_bands: SubjectBands = Field(default_factory=SubjectBands)
    topics: TopicRules = Field(default_factory=TopicRules)
    trends: TrendRules = Field(default_factory=TrendRules)


DEFAULT_POLICY = Policy()


def load_policy(content_dir: Path) -> Policy:
    path = content_dir / "policy.yaml"
    if not path.exists():
        return DEFAULT_POLICY
    return Policy.model_validate(yaml.safe_load(path.read_text()) or {})
