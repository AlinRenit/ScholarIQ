"""Transparent, rule-based topic classification.

Inputs are evidence items about one student and one topic. Output is one of
four labels with the reasons and evidence behind it.

Rules (policy.topics):
1. Count *topic-level* observations: topic exam items, exam questions mapped
   to the topic (exam breakdowns), diagnostic and practice answers. Subject
   marks and self-reports are not topic-level.
2. Fewer than ``min_direct_observations`` -> INSUFFICIENT_EVIDENCE. Asking a
   question about a topic is never evidence.
3. Otherwise take a weighted mean of all scored evidence. Each item weighs
   ``kind weight x sample size x recency``; the subject mark counts as at most
   one observation, so it can nudge but never decide the label.
4. Mean >= strong_at -> STRONG; < attention_below -> NEEDS_ATTENTION;
   otherwise DEVELOPING.

The weighted mean is an internal ranking value, not a probability or a
"mastery percentage", and is not shown as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from scholariq.analytics.policy import Policy
from scholariq.analytics.subjects import Band
from scholariq.domain.enums import EvidenceKind, MasteryClass

DIRECT_KINDS = {
    EvidenceKind.TOPIC_EXAM,
    EvidenceKind.EXAM_BREAKDOWN,
    EvidenceKind.DIAGNOSTIC,
    EvidenceKind.PRACTICE,
}
RULE_VERSION = "topic-rules/1"


@dataclass(frozen=True)
class EvidenceItem:
    id: str
    kind: EvidenceKind
    score: Decimal | None
    sample_size: int
    observed_at: datetime
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubjectSignal:
    subject_name: str
    band: Band
    sibling_topics: tuple[str, ...]  # other topic names in the subject, for the message


@dataclass
class Classification:
    label: MasteryClass
    direct_observations: int
    reasons: list[str]
    subject_messages: list[str]
    evidence_ids: list[str]
    next_action: str
    rule_version: str
    policy_version: str
    weighted_mean: float | None = None  # internal; not displayed as a percentage


def _weight(item: EvidenceItem, policy: Policy, now: datetime) -> float:
    w = policy.topics.weights
    per_kind = {
        EvidenceKind.TOPIC_EXAM: w.topic_exam,
        EvidenceKind.EXAM_BREAKDOWN: w.exam_breakdown,
        EvidenceKind.DIAGNOSTIC: w.diagnostic,
        EvidenceKind.PRACTICE: w.practice,
        EvidenceKind.SELF_REPORT: w.self_report,
        EvidenceKind.SUBJECT_SCORE_PRIOR: w.subject_score_prior,
    }[item.kind]
    size = 1 if item.kind is EvidenceKind.SUBJECT_SCORE_PRIOR else max(item.sample_size, 1)
    observed = item.observed_at if item.observed_at.tzinfo else item.observed_at.replace(tzinfo=UTC)
    age_days = max((now - observed).total_seconds() / 86400, 0)
    decay: float = 0.5 ** (age_days / policy.topics.half_life_days)
    return float(per_kind * size * decay)


def subject_message(signal: SubjectSignal, topic_name: str) -> str:
    s = signal.subject_name
    match signal.band:
        case Band.NEEDS_ATTENTION:
            names = [topic_name, *[t for t in signal.sibling_topics if t != topic_name]][:3]
            choice = ", ".join(names[:-1]) + f" or {names[-1]}" if len(names) > 1 else names[0]
            return (
                f"Your {s} score suggests this subject may need attention. We need topic-level "
                f"practice results to determine whether {choice} is the main difficulty."
            )
        case Band.DEVELOPING:
            return (
                f"Your {s} score is in the middle range. It does not show which of its topics "
                "are solid and which are not."
            )
        case Band.STRONG:
            return (
                f"Your {s} score is strong. That suggests, but does not prove, that this topic "
                "is understood."
            )
        case _:
            return (
                f"There is no usable {s} score yet (missing marks, absence or unconverted grade)."
            )


_NEXT = {
    MasteryClass.INSUFFICIENT_EVIDENCE: (
        "Take a diagnostic quiz on this topic, or add a topic test result."
    ),
    MasteryClass.NEEDS_ATTENTION: (
        "Work through this topic step by step, starting with its prerequisites, then "
        "check yourself again."
    ),
    MasteryClass.DEVELOPING: "Practise mixed questions to firm this topic up.",
    MasteryClass.STRONG: "Optional challenge questions; otherwise move on to weaker topics.",
}


_KIND_LABELS = {
    EvidenceKind.SUBJECT_SCORE_PRIOR: "Subject result",
    EvidenceKind.TOPIC_EXAM: "Topic test",
    EvidenceKind.EXAM_BREAKDOWN: "Exam questions",
    EvidenceKind.DIAGNOSTIC: "Diagnostic quiz",
    EvidenceKind.PRACTICE: "Practice",
    EvidenceKind.SELF_REPORT: "Self-assessment",
}


def describe(item: EvidenceItem) -> str:
    """One readable line per evidence item, used in reasons and evidence lists."""
    d = item.details
    label = _KIND_LABELS[item.kind]
    if "correct" in d and "total" in d:
        return f"{label}: {d['correct']} of {d['total']} correct"
    if item.kind is EvidenceKind.SELF_REPORT and "rating" in d:
        return f"{label}: confidence {d['rating']} of 5"
    if item.score is None:
        return label
    pct = f"{float(item.score * 100):.0f}%"
    if item.kind is EvidenceKind.SUBJECT_SCORE_PRIOR:
        return f"{label}: {pct} for the whole subject (counts as one weak observation)"
    if "obtained" in d and "maximum" in d:
        marks = f"{_trim(d['obtained'])} of {_trim(d['maximum'])} marks ({pct})"
        if item.kind is EvidenceKind.EXAM_BREAKDOWN:
            where = f" in {d['exam']}" if d.get("exam") else ""
            labels = d.get("questions") or []
            which = f" ({', '.join(labels)})" if labels else ""
            return f"{label}{where}: {marks}, {item.sample_size} question(s){which}"
        return f"{label}: {marks}, {item.sample_size} question(s)"
    return f"{label}: {pct} over {item.sample_size} question(s)"


def _trim(value: object) -> str:
    text = str(value)
    return text.rstrip("0").rstrip(".") if "." in text else text


def classify(
    topic_name: str,
    items: list[EvidenceItem],
    signals: list[SubjectSignal],
    policy: Policy,
    now: datetime | None = None,
) -> Classification:
    now = now or datetime.now(UTC)
    rules = policy.topics
    direct = [i for i in items if i.kind in DIRECT_KINDS and i.score is not None]
    n_direct = sum(max(i.sample_size, 1) for i in direct)
    subject_messages = [subject_message(s, topic_name) for s in signals]
    reasons: list[str] = []
    evidence_ids = [i.id for i in items]

    if n_direct < rules.min_direct_observations:
        reasons.append(
            f"{n_direct} topic-level observation(s) recorded; at least "
            f"{rules.min_direct_observations} are needed before this topic is classified."
        )
        if any(i.kind is EvidenceKind.SELF_REPORT for i in items):
            reasons.append("Your self-assessment is recorded but is not enough on its own.")
        label = MasteryClass.INSUFFICIENT_EVIDENCE
        return Classification(
            label,
            n_direct,
            reasons,
            subject_messages,
            evidence_ids,
            _NEXT[label],
            RULE_VERSION,
            policy.version,
        )

    scored = [i for i in items if i.score is not None]
    weights = [_weight(i, policy, now) for i in scored]
    total = sum(weights)
    mean = sum(w * float(i.score or 0) for w, i in zip(weights, scored, strict=True)) / total
    if mean >= rules.strong_at:
        label = MasteryClass.STRONG
    elif mean < rules.attention_below:
        label = MasteryClass.NEEDS_ATTENTION
    else:
        label = MasteryClass.DEVELOPING

    reasons.append(f"Based on {n_direct} topic-level observation(s):")
    reasons += [f"  {describe(i)}" for i in sorted(direct, key=lambda i: i.observed_at)]
    if any(i.kind is EvidenceKind.SUBJECT_SCORE_PRIOR for i in scored):
        reasons.append("The subject mark is included as a single observation (weak prior).")
    if any(i.kind is EvidenceKind.SELF_REPORT for i in scored):
        reasons.append("Your self-assessment is included with reduced weight.")
    direct_mean = sum(float(i.score or 0) * i.sample_size for i in direct) / n_direct
    for s in signals:
        if s.band is Band.STRONG and direct_mean < rules.attention_below:
            reasons.append(
                f"Your {s.subject_name} mark was strong, but topic-level answers show "
                "difficulty here. Topic-level evidence takes precedence."
            )
        elif s.band is Band.NEEDS_ATTENTION and direct_mean >= rules.strong_at:
            reasons.append(
                f"Your {s.subject_name} mark was low, but topic-level answers are strong here. "
                "Topic-level evidence takes precedence."
            )
    margin = min(abs(mean - rules.strong_at), abs(mean - rules.attention_below))
    if margin < 0.05:
        reasons.append("This is close to a boundary; a few more answers could change it.")
    return Classification(
        label,
        n_direct,
        reasons,
        subject_messages,
        evidence_ids,
        _NEXT[label],
        RULE_VERSION,
        policy.version,
        round(mean, 4),
    )
