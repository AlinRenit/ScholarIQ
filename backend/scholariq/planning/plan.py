"""Study-plan ordering with a published priority formula (``plan-formula/1``).

For every candidate topic::

    priority = w_need * need + w_importance * importance + w_goal * goal
             + w_unlocks * unlocks + w_recent * recent_result - w_time * study_time

* need: from the topic's classification (``policy.plan.need``); an
  unclassified topic gets ``weak_subject_bonus`` more when one of its
  subjects' marks is in the "may need attention" band.
* importance: the curriculum's importance for the topic (1 to 5) divided by 5.
* goal: 1 when the student picked the topic (or its subject) as a goal.
* unlocks: how many other topics in the plan build on this one, capped at 3,
  divided by 3.
* recent_result: 1 minus the latest topic-level result (fraction correct in a
  diagnostic quiz, or fraction of marks on the topic's questions in a
  confirmed exam breakdown), when it is within ``recent_days``; otherwise 0.
* study_time: estimated minutes divided by ``long_topic_minutes``, capped at 1.

Topics classified Strong are left out unless they are a goal. Topics are then
taken in priority order, but a topic's prerequisites that are also in the
plan are placed before it. Each term is kept so the plan can show why a topic
is where it is. The score orders topics; it is not a measure of anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from scholariq.analytics.policy import PlanRules
from scholariq.analytics.subjects import Band
from scholariq.domain.enums import MasteryClass

FORMULA_VERSION = "plan-formula/1"


@dataclass(frozen=True)
class TopicInput:
    topic_id: str
    name: str
    classification: MasteryClass
    importance: int | None  # 1..5 from the curriculum, None when not in the student's subjects
    minutes: int | None
    subject_bands: tuple[Band, ...] = ()
    last_quiz: tuple[float, datetime] | None = None  # (fraction correct, when)
    last_source: str = "quiz"  # what last_quiz came from, for the explanation


@dataclass
class Term:
    value: float
    weight: float
    why: str

    @property
    def contribution(self) -> float:
        return round(self.value * self.weight, 4)


@dataclass
class PlanEntry:
    topic: TopicInput
    priority: float
    terms: dict[str, Term]
    # Prerequisite topics (by id) that come earlier in this plan.
    after: list[str] = field(default_factory=list)
    # Set when this topic was moved forward because a later topic builds on it.
    moved_for: str | None = None


def _terms(
    t: TopicInput,
    rules: PlanRules,
    goal: bool,
    unlocks: int,
    now: datetime,
) -> dict[str, Term]:
    w = rules.weights
    need = rules.need[t.classification.value]
    need_why = f"Classified {t.classification.value.replace('_', ' ')}"
    if t.classification is MasteryClass.INSUFFICIENT_EVIDENCE and Band.NEEDS_ATTENTION in (
        t.subject_bands
    ):
        need = min(1.0, need + rules.weak_subject_bonus)
        need_why += "; a subject mark that includes it may need attention"
    importance = (t.importance or 0) / 5
    recent = 0.0
    recent_why = f"No diagnostic quiz or exam result in the last {rules.recent_days} days"
    if t.last_quiz is not None:
        score, when = t.last_quiz
        if (now - when).days <= rules.recent_days:
            recent = 1 - score
            recent_why = (
                f"Latest quiz: {score:.0%} correct"
                if t.last_source == "quiz"
                else f"Latest {t.last_source}: {score:.0%} of the marks"
            )
    minutes = t.minutes or 0
    return {
        "need": Term(need, w.need, need_why),
        "importance": Term(
            importance,
            w.importance,
            f"Curriculum importance {t.importance} of 5"
            if t.importance
            else "Not in your subjects",
        ),
        "goal": Term(
            1.0 if goal else 0.0, w.goal, "You chose it as a goal" if goal else "Not a goal"
        ),
        "unlocks": Term(
            min(unlocks, 3) / 3,
            w.unlocks,
            f"{unlocks} other planned topic(s) build on it"
            if unlocks
            else "No planned topic builds on it",
        ),
        "recent_result": Term(recent, w.recent_result, recent_why),
        "study_time": Term(
            min(minutes / rules.long_topic_minutes, 1.0),
            -w.study_time,
            f"About {minutes} minutes of study" if minutes else "No time estimate",
        ),
    }


def build_plan(
    topics: list[TopicInput],
    requires: Mapping[str, set[str]],
    goals: set[str],
    rules: PlanRules,
    now: datetime,
) -> list[PlanEntry]:
    """``requires[a]`` holds the topics that topic ``a`` builds on."""
    included = {
        t.topic_id: t
        for t in topics
        if t.classification is not MasteryClass.STRONG or t.topic_id in goals
    }
    unlocks = {
        tid: sum(1 for other in included if other != tid and tid in requires.get(other, set()))
        for tid in included
    }
    entries = {}
    for tid, t in included.items():
        terms = _terms(t, rules, tid in goals, unlocks[tid], now)
        priority = round(sum(term.contribution for term in terms.values()), 4)
        entries[tid] = PlanEntry(t, priority, terms)
    ranked = sorted(entries.values(), key=lambda e: (-e.priority, e.topic.name))
    rank = {e.topic.topic_id: i for i, e in enumerate(ranked)}

    ordered: list[PlanEntry] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def place(tid: str, needed_by: str | None) -> None:
        if tid in placed or tid in visiting:  # a prerequisite cycle is cut here
            return
        visiting.add(tid)
        entry = entries[tid]
        for pre in sorted(requires.get(tid, set()) & entries.keys(), key=lambda p: rank[p]):
            place(pre, tid)
        visiting.discard(tid)
        if needed_by is not None and rank[tid] > rank[needed_by]:
            entry.moved_for = needed_by
        entry.after = sorted(requires.get(tid, set()) & placed, key=lambda p: rank[p])
        ordered.append(entry)
        placed.add(tid)

    for e in ranked:
        place(e.topic.topic_id, None)
    return ordered
