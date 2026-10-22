"""Choose how an answer is taught from the student's topic evidence.

The policy picks which knowledge-base sections to include, in what order and
at what depth. It never changes the content of a section: a student marked
"needs attention" and one marked "strong" get the same facts from the same
entries, only more or fewer of them. A question about a topic is not evidence
about the student and never changes their classification.

* overview (topic classified Strong): definition, key facts, one explanation,
  one example, connections, a challenge question.
* balanced (Developing, Insufficient evidence, or no profile): definition, key
  facts, explanations up to depth 2, one example, common mistakes, a check
  question.
* guided (Needs attention, or the student asks for simpler): prerequisites
  first, explanations from basic to advanced, all examples, common mistakes,
  an easy check question, a summary, and what comes next.
* deeper (the student asks for more depth): everything, including advanced
  explanations, connections and a challenge question.

A depth the student asks for in the question ("simply", "in detail") or with
the buttons overrides the level chosen from evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scholariq.domain.enums import MasteryClass
from scholariq.nlu.intents import Depth

POLICY_VERSION = "teaching-policy/1"

Level = Literal["overview", "balanced", "guided", "deeper"]


@dataclass(frozen=True)
class TeachingPlan:
    level: Level
    max_depth: int  # deepest knowledge document depth to include (1-3)
    explanations: int  # how many explanation documents at most
    examples: int  # how many worked examples at most
    prerequisites: bool
    misconceptions: bool
    connections: bool
    summary: bool
    next_topics: bool
    check: Literal["easy", "medium", "challenge"]
    offer_diagnostic: bool
    reason: str


PLANS: dict[Level, TeachingPlan] = {
    "overview": TeachingPlan(
        "overview", 3, 1, 1, False, False, True, False, False, "challenge", False, ""
    ),
    "balanced": TeachingPlan(
        "balanced", 2, 2, 1, False, True, False, False, False, "medium", False, ""
    ),
    "guided": TeachingPlan("guided", 3, 9, 9, True, True, False, True, True, "easy", False, ""),
    "deeper": TeachingPlan(
        "deeper", 3, 9, 9, False, True, True, False, True, "challenge", False, ""
    ),
}


def plan_for(
    classification: MasteryClass | None, requested: Depth, topic_name: str | None
) -> TeachingPlan:
    topic = topic_name or "this topic"
    if requested is Depth.SIMPLER:
        return _with(
            PLANS["guided"], "You asked for a simpler explanation, so this starts from basics."
        )
    if requested is Depth.DEEPER:
        return _with(PLANS["deeper"], "You asked for more depth, so advanced material is included.")
    if classification is MasteryClass.STRONG:
        return _with(
            PLANS["overview"],
            f"Your evidence for {topic} is Strong, so this is a concise overview with a "
            "challenge question. Ask for more detail at any time.",
        )
    if classification is MasteryClass.NEEDS_ATTENTION:
        return _with(
            PLANS["guided"],
            f"Your evidence for {topic} says it needs attention, so this goes step by step "
            "from the basics, with prerequisites and a check question.",
        )
    if classification is MasteryClass.DEVELOPING:
        return _with(PLANS["balanced"], f"Your evidence for {topic} is Developing.")
    if classification is MasteryClass.INSUFFICIENT_EVIDENCE:
        plan = _with(
            PLANS["balanced"],
            f"There is not enough evidence yet to judge {topic}, so this is a balanced "
            "explanation. Asking about a topic does not change how it is classified.",
        )
        return TeachingPlan(**{**plan.__dict__, "offer_diagnostic": True})
    return _with(PLANS["balanced"], "Balanced explanation (no profile or topic evidence used).")


def _with(plan: TeachingPlan, reason: str) -> TeachingPlan:
    return TeachingPlan(**{**plan.__dict__, "reason": reason})
