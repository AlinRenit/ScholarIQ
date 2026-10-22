"""Turn a question into a structured reading the answer engine can act on.

Stages, each recorded in ``trace`` so the tutor can show its working:

1. normalise text and expand shorthand (``diff b/w`` -> ``difference between``)
2. correct misspellings against the knowledge base's vocabulary
3. match the intent grammar, the requested depth and follow-up phrases
4. link concept, topic and subject names (longest phrase wins)
5. retrieve and score candidate concepts with BM25 for questions that do not
   name a concept, and measure how much of the question the knowledge base covers
6. resolve follow-ups against the previous answer in the same conversation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scholariq.knowledge.index import SearchHit
from scholariq.nlu.intents import (
    REFERENCE,
    Depth,
    FollowUp,
    Intent,
    IntentMatch,
    match_follow_up,
    match_intents,
    requested_depth,
    step_number,
)
from scholariq.nlu.lexicon import Lexicon, Phrase
from scholariq.nlu.normalise import CodeBlock, normalise
from scholariq.nlu.spelling import Correction
from scholariq.retrieval.text import QUERY_STOPWORDS, STOPWORDS, stem, words


@dataclass(frozen=True)
class Mention:
    kind: str  # concept | topic | subject
    refs: tuple[str, ...]  # several when one phrase names more than one thing
    text: str  # the name as written in the knowledge base
    start: int  # position in the analysed word sequence


@dataclass
class Context:
    """What the previous tutor answer in this conversation was about."""

    concepts: list[str] = field(default_factory=list)
    topic: str | None = None
    intent: str | None = None
    depth: str = Depth.STANDARD.value
    steps: list[str] = field(default_factory=list)


@dataclass
class ParsedQuery:
    original: str
    text: str
    corrected: str
    code: list[CodeBlock]
    expansions: list[tuple[str, str]]
    corrections: list[Correction]
    intents: list[IntentMatch]
    intent: Intent
    depth: Depth
    follow_up: FollowUp | None
    step: int | None
    mentions: list[Mention]
    candidates: list[SearchHit]
    content_words: list[str]
    unmatched: list[str]
    used_context: bool = False
    trace: list[str] = field(default_factory=list)
    # Set by the answer engine when an ambiguous name was settled on one concept.
    resolved: str | None = None

    @property
    def coverage(self) -> float:
        """Share of the question's subject words that the knowledge base contains."""
        if not self.content_words:
            return 0.0
        return 1 - len(self.unmatched) / len(self.content_words)

    def concepts(self) -> list[Mention]:
        return [m for m in self.mentions if m.kind == "concept"]

    def topics(self) -> list[Mention]:
        return [m for m in self.mentions if m.kind == "topic"]

    def subjects(self) -> list[Mention]:
        return [m for m in self.mentions if m.kind == "subject"]


def _correct(text: str, lex: Lexicon) -> tuple[str, list[Correction]]:
    corrections: list[Correction] = []
    seen: set[str] = set()
    for w in words(text):
        if w in seen or lex.is_ordinary(w) or lex.corrector.known(w):
            continue
        if stem(w) in lex.index.bm25.idf:  # another form of a known word ("occur", "occurs")
            continue
        seen.add(w)
        c = lex.corrector.correct(w)
        if c is not None:
            corrections.append(c)
    for c in corrections:
        text = re.sub(
            rf"(?<![A-Za-z]){re.escape(c.typed)}(?![A-Za-z])", c.corrected, text, flags=re.I
        )
    return text, corrections


def find_mentions(text: str, lex: Lexicon) -> list[Mention]:
    """Longest non-overlapping name matches, in question order."""
    surface = [w for w in words(text) if w not in STOPWORDS and w not in QUERY_STOPWORDS]
    seq = [stem(w) for w in surface]
    found: list[tuple[int, int, Phrase]] = []  # (start, length in words, phrase)
    for i, s in enumerate(seq):
        for p in lex.phrases.get(s, []):
            n = len(p.stems)
            if tuple(seq[i : i + n]) == p.stems:
                found.append((i, n, p))
    # Two typed words that form one known name: "quick sort" -> quicksort.
    for i in range(len(surface) - 1):
        for p in lex.single_stems.get(stem(surface[i] + surface[i + 1]), []):
            found.append((i, 2, p))

    # Merge phrases that cover the same span and kind (e.g. one alias, two concepts).
    spans: dict[tuple[int, int, str], list[Phrase]] = {}
    for start, n, p in found:
        spans.setdefault((start, n, p.kind), []).append(p)

    # For the same words: a concept's own name, then a topic name, then a concept
    # alias, then a subject. "Normalization" is the topic, not a concept that lists
    # it as an alias.
    # A topic name made of two concept names ("Processes and threads") gives way to
    # the concepts, so "process and thread" reads as two concepts.
    def inner_concepts(start: int, n: int) -> int:
        return len(
            {
                p.ref
                for (s0, n0, k), ps in spans.items()
                for p in ps
                if k == "concept" and p.primary and start <= s0 and s0 + n0 <= start + n
            }
        )

    topic_names = {
        (start, n): p.ref for (start, n, k), ps in spans.items() if k == "topic" for p in ps
    }

    def key(item: tuple[tuple[int, int, str], list[Phrase]]) -> tuple[int, int, int]:
        (start, n, kind), phrases = item
        if kind == "concept":
            if any(p.primary for p in phrases):
                return (0, -n, 0)
            # An alias that is the name of the concept's own topic ("virtual memory" for
            # "Virtual memory and demand paging") names the concept, not the topic.
            topic = topic_names.get((start, n))
            own = topic is not None and any(lex.concept_topic.get(p.ref) == topic for p in phrases)
            return (0, -n, 0 if own else 2)
        if inner_concepts(start, n) >= 2:
            return (1, -n, 0)
        return (0, -n, 1 if kind == "topic" else 3)

    ordered = sorted(spans.items(), key=lambda kv: (*key(kv), kv[0][0]))
    taken: set[int] = set()
    mentions: list[Mention] = []
    for (start, n, kind), phrases in ordered:
        cells = set(range(start, start + n))
        if cells & taken:
            # A topic or subject name may share words with a concept name; keep the concept.
            continue
        taken |= cells
        refs = tuple(sorted({p.ref for p in phrases}))
        text_shown = min((p.text for p in phrases), key=len)
        mentions.append(Mention(kind, refs, text_shown, start))
    mentions.sort(key=lambda m: m.start)
    return mentions


def parse(text: str, lex: Lexicon, context: Context | None = None) -> ParsedQuery:
    trace: list[str] = []
    norm = normalise(text, lex.abbreviations)
    for typed, full in norm.expansions:
        trace.append(f'Read "{typed}" as "{full}".')
    if norm.code:
        trace.append(f"Found {len(norm.code)} block(s) of code.")

    corrected, corrections = _correct(norm.text, lex)
    for c in corrections:
        trace.append(f'Corrected "{c.typed}" to "{c.corrected}" ({c.distance} letter change(s)).')

    intents = match_intents(corrected)
    depth = requested_depth(corrected)
    fu = match_follow_up(corrected)
    mentions = find_mentions(corrected, lex)
    candidates = lex.index.search(corrected, k=5)

    content_words = [
        w
        for w in dict.fromkeys(words(corrected))
        if not lex.is_ordinary(w) and not w.isdigit() and len(w) > 1
    ]
    unmatched_all = set(lex.index.unmatched_terms(corrected))
    unmatched = [w for w in content_words if w in unmatched_all]

    intent = intents[0].intent if intents else Intent.UNKNOWN
    if norm.code:
        intent = Intent.CODE
    follow_up: FollowUp | None = None
    used_context = False
    has_concept = any(m.kind == "concept" for m in mentions)
    if context and context.concepts:
        refers_back = bool(REFERENCE.search(corrected)) and not has_concept
        if fu is not None and (not has_concept or fu[0] is not FollowUp.DEEPER):
            follow_up = fu[0]
        elif refers_back and intent in (Intent.UNKNOWN, Intent.EXPLANATION, Intent.DEFINITION):
            follow_up = FollowUp.CONTINUE
        elif not intents and not has_concept and not content_words:
            follow_up = FollowUp.CONTINUE
        if follow_up is not None:
            intent = Intent.FOLLOW_UP
            used_context = True
            trace.append(
                f"Follow-up ({fu[1] if fu else 'refers to the previous answer'}): "
                f"applies to {', '.join(context.concepts)}."
            )

    if intents and intent is not Intent.FOLLOW_UP:
        m = intents[0]
        trace.append(f'Question type: {intent.value.replace("_", " ")} ("{m.matched}" {m.label}).')
    elif intent is Intent.UNKNOWN:
        trace.append("No question pattern matched; treating it as a request for an explanation.")
    for mention in mentions:
        names = ", ".join(mention.refs)
        trace.append(f'Recognised {mention.kind} "{mention.text}" ({names}).')
    if depth is not Depth.STANDARD:
        trace.append(f"Requested depth: {depth.value}.")

    return ParsedQuery(
        original=text,
        text=norm.text,
        corrected=corrected,
        code=norm.code,
        expansions=norm.expansions,
        corrections=corrections,
        intents=intents,
        intent=intent,
        depth=depth,
        follow_up=follow_up,
        step=step_number(corrected),
        mentions=mentions,
        candidates=candidates,
        content_words=content_words,
        unmatched=unmatched,
        used_context=used_context,
        trace=trace,
    )


def split_parts(text: str) -> list[str]:
    """Split a multi-part question ("What is a stack? And how is it used?")."""
    parts = [p.strip() for p in re.split(r"(?<=\?)\s+|;\s+|\s+and also\s+", text) if p.strip()]
    return parts if len(parts) > 1 else [text]
