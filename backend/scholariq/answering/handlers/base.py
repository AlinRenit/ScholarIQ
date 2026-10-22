"""What every handler receives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from scholariq.answering.content import ConceptBundle, load_bundle
from scholariq.answering.model import Personalisation
from scholariq.domain.enums import TrustStatus
from scholariq.nlu.parser import ParsedQuery
from scholariq.tutoring.policy import TeachingPlan


@dataclass
class HandlerContext:
    session: Session
    allowed: tuple[TrustStatus, ...]
    parsed: ParsedQuery
    # Teaching plan for a topic slug (uses the student's evidence when there is a profile).
    plan_for: Callable[[str | None], tuple[TeachingPlan, Personalisation]]
    # Question slugs already shown in this conversation, so checks do not repeat.
    asked: set[str] = field(default_factory=set)
    student_id: str | None = None

    def bundle(self, slug: str) -> ConceptBundle | None:
        return load_bundle(self.session, slug, self.allowed)
