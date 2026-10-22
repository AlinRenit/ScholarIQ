"""Intent grammar: ordered, weighted patterns over the normalised question.

Every rule that matches adds a candidate with its weight; the strongest
candidate wins and ties go to the rule listed first. The matched words are kept
so the tutor can say why it read a question the way it did. Rules are plain
regular expressions, reviewed like any other code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    DEFINITION = "definition"
    EXPLANATION = "explanation"
    COMPARISON = "comparison"
    PROCEDURE = "procedure"
    WORKED_PROBLEM = "worked_problem"
    REASONING = "reasoning"
    PREREQUISITES = "prerequisites"
    PRACTICE = "practice"
    STUDY_ADVICE = "study_advice"
    CODE = "code"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class FollowUp(StrEnum):
    """What a follow-up asks to do with the previous answer."""

    REPEAT_STEP = "repeat_step"
    SIMPLIFY = "simplify"
    DEEPER = "deeper"
    EXAMPLE = "example"
    CHECK = "check"
    CONTINUE = "continue"


class Depth(StrEnum):
    SIMPLER = "simpler"
    STANDARD = "standard"
    DEEPER = "deeper"


@dataclass(frozen=True)
class Rule:
    intent: Intent
    pattern: re.Pattern[str]
    weight: float
    label: str


def _r(intent: Intent, pattern: str, weight: float, label: str) -> Rule:
    return Rule(intent, re.compile(pattern, re.I), weight, label)


W = r"[a-z0-9+#'-]+"

RULES: tuple[Rule, ...] = (
    # Asking for a plan from their own results.
    _r(
        Intent.STUDY_ADVICE,
        r"\bwhat (should|do) i (study|learn|revise|focus on|work on|practi[cs]e)\b"
        r"|\bwhere (should|do) i (start|begin)\b|\bbased on my (results|marks|grades|scores)\b"
        r"|\bmy weak(est)? (topics?|subjects?|areas?)\b|\bwhat (am i|i am) weak (at|in)\b"
        r"|\b(study|revise|learn) first\b",
        3.0,
        "asks what to study based on their results",
    ),
    _r(
        Intent.PREREQUISITES,
        r"\bprerequisites?\b|\b(learn|know|study|understand|cover) (first )?before\b"
        r"|\bbefore (i )?(learn|study|start|studying|learning|starting|tackling|doing)\b"
        r"|\bwhat (do i need|should i know) (to know )?(for|before)\b|\bfoundations? (for|of)\b",
        3.2,
        "asks what to learn first",
    ),
    _r(
        Intent.PRACTICE,
        r"\b(practi[cs]e|quiz me|test me|exercises?|mcqs?)\b"
        r"|\b(give|show|ask) me (some |a few |more )?(questions?|problems?)\b"
        r"|\bquestions? (on|about|for|from)\b",
        2.8,
        "asks for practice questions",
    ),
    _r(
        Intent.COMPARISON,
        r"\bdifferen(ce|ces|t|tiate)\b|\bcompar(e|ed|ing|ison)\b|\bcontrast\b"
        rf"|\bversus\b|\bvs\.?(?=\s)|\b{W} or {W}\b.*\b(better|faster|prefer|choose|which)\b"
        r"|\bwhich is (better|faster|preferred)\b|\bsimilarit(y|ies)\b",
        2.6,
        "asks how two things differ",
    ),
    _r(
        Intent.PROCEDURE,
        r"\bhow (do|can|should|would|to)( i| you| we| one)? (calculate|compute|find|determine"
        r"|derive|convert|normali[sz]e|implement|apply|perform|draw|construct|decompose|check"
        r"|identify|analy[sz]e|design|write|choose|reverse|insert|delete|traverse|detect)\b"
        r"|\bsteps? (to|for|of|in)\b|\bprocedure\b|\bstep[- ]by[- ]step\b|\balgorithm (to|for)\b"
        r"|\bmethod (to|for)\b",
        2.4,
        "asks for a procedure",
    ),
    _r(
        Intent.WORKED_PROBLEM,
        r"^\s*(please )?(solve|evaluate|compute|calculate|work out|simplify)\b|\bsolve\b"
        r"|\btruth table (for|of)\b|\b(find|what is) the (value|result|answer|output)\b",
        2.3,
        "asks to solve a problem",
    ),
    _r(
        Intent.REASONING,
        r"^\s*why\b|\bwhy (do|does|is|are|can|can't|cannot|would|should|did|must)\b"
        r"|\bwhat causes\b|\bfor what reason\b|\bhow come\b|\bwhat happens (if|when)\b",
        2.2,
        "asks why",
    ),
    _r(
        Intent.EXPLANATION,
        r"\bexplain\b|\bhow (does|do|is|are) .+ (work|works|working|done|used|implemented)\b"
        r"|\bdescribe\b|\btell me (about|more)\b|\bwalk me through\b|\belaborate\b"
        r"|\bworking of\b|\bteach me\b|\bhelp me understand\b|\boverview of\b|\bhow (does|do)\b",
        2.0,
        "asks for an explanation",
    ),
    _r(
        Intent.DEFINITION,
        r"^\s*(what|whats|what's) (is|are|was|were|does)\b|\bdefine\b|\bdefinition\b"
        r"|\bmeaning of\b|\bstands? for\b|\bwhat do (you|we) mean by\b|\bwhat is meant by\b"
        r"|\bmeans\b",
        1.8,
        "asks what something is",
    ),
)

FOLLOW_UP_RULES: tuple[tuple[FollowUp, re.Pattern[str], str], ...] = (
    (
        FollowUp.REPEAT_STEP,
        re.compile(
            r"\b(the )?(first|second|third|fourth|fifth|last|\d+(st|nd|rd|th)?) step\b"
            r"|\bstep (\d+|one|two|three|four|five)\b",
            re.I,
        ),
        "refers to a step of the last answer",
    ),
    (
        FollowUp.SIMPLIFY,
        re.compile(
            r"\bsimplif(y|ied)\b|\bsimpler\b|\bin simple (terms|words)\b|\beli5\b"
            r"|\bi (still )?(don't|do not|didn't|did not) (get|understand)\b|\bmore simply\b"
            r"|\bmore basic\b|\bconfus(ed|ing)\b",
            re.I,
        ),
        "asks for a simpler explanation",
    ),
    (
        FollowUp.DEEPER,
        re.compile(
            r"\bgo deeper\b|\bmore (detail|depth|advanced)\b|\bin (more )?(detail|depth)\b"
            r"|\bdeeper\b|\badvanced\b|\belaborate\b|\btell me more\b",
            re.I,
        ),
        "asks for more depth",
    ),
    (
        FollowUp.EXAMPLE,
        re.compile(
            r"\b(an?|another|one more) (worked )?example\b|\bworked example\b"
            r"|\bshow (me )?an? example\b"
            r"|\bexample (of|for) (it|this|that)\b|\bgive (me )?an? example\b",
            re.I,
        ),
        "asks for an example",
    ),
    (
        FollowUp.CHECK,
        re.compile(
            r"\btest my understanding\b|\bcheck my understanding\b|\bquiz me\b|\btest me\b",
            re.I,
        ),
        "asks to be tested",
    ),
)

REFERENCE = re.compile(
    r"^\s*(and|also|so|then|ok(ay)?|what about|how about)\b"
    r"|\b(it|this|that|these|those|them|they)\b"
    r"|\bagain\b",
    re.I,
)

DEPTH_RULES: tuple[tuple[Depth, re.Pattern[str]], ...] = (
    (
        Depth.SIMPLER,
        re.compile(
            r"\b(simple|simply|simpler|basic|basics|beginner|briefly|brief|short|in short"
            r"|quickly|eli5|layman|plain (english|words))\b",
            re.I,
        ),
    ),
    (
        Depth.DEEPER,
        re.compile(
            r"\b(in detail|detailed|in depth|in-depth|thorough(ly)?|deeper|advanced|rigorous"
            r"|formal(ly)?|elaborate)\b",
            re.I,
        ),
    ),
)

ORDINALS = {
    "first": 1,
    "one": 1,
    "second": 2,
    "two": 2,
    "third": 3,
    "three": 3,
    "fourth": 4,
    "four": 4,
    "fifth": 5,
    "five": 5,
}


@dataclass(frozen=True)
class IntentMatch:
    intent: Intent
    weight: float
    label: str
    matched: str


def match_intents(text: str) -> list[IntentMatch]:
    """All intents whose rules match, strongest first (one entry per intent)."""
    best: dict[Intent, IntentMatch] = {}
    for rule in RULES:
        m = rule.pattern.search(text)
        if m and (rule.intent not in best or best[rule.intent].weight < rule.weight):
            best[rule.intent] = IntentMatch(
                rule.intent, rule.weight, rule.label, m.group(0).strip()
            )
    order = {r.intent: i for i, r in enumerate(RULES)}
    return sorted(best.values(), key=lambda m: (-m.weight, order[m.intent]))


def match_follow_up(text: str) -> tuple[FollowUp, str, str] | None:
    for kind, pattern, label in FOLLOW_UP_RULES:
        m = pattern.search(text)
        if m:
            return kind, label, m.group(0).strip()
    return None


def step_number(text: str) -> int | None:
    """Which step a follow-up refers to (1-based), or -1 for 'last'."""
    m = re.search(r"\b(first|second|third|fourth|fifth|last|\d+)(st|nd|rd|th)? step\b", text, re.I)
    m = m or re.search(r"\bstep (\d+|one|two|three|four|five)\b", text, re.I)
    if not m:
        return None
    word = m.group(1).lower()
    if word == "last":
        return -1
    return int(word) if word.isdigit() else ORDINALS.get(word)


def requested_depth(text: str) -> Depth:
    for depth, pattern in DEPTH_RULES:
        if pattern.search(text):
            return depth
    return Depth.STANDARD
