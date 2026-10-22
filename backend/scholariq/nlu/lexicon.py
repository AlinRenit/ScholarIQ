"""Everything the parser knows by name: concepts, topics, subjects, shorthand.

Built from the knowledge base and curriculum in the database, so new content
is understood as soon as it is synced. Cached per knowledge-base fingerprint.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scholariq.db.models import Subject, SubjectTopic, Topic
from scholariq.knowledge.index import ConceptIndex, name_stems
from scholariq.nlu.intents import DEPTH_RULES, FOLLOW_UP_RULES, REFERENCE, RULES
from scholariq.nlu.normalise import load_abbreviations
from scholariq.nlu.spelling import SpellingCorrector
from scholariq.retrieval.text import QUERY_STOPWORDS, STOPWORDS, words

Kind = Literal["concept", "topic", "subject"]

# Ordinary words students use around a question. They are never "corrected"
# into knowledge-base terms, and they do not count against coverage.
COMMON_WORDS = frozenset(
    """able actually after again all already always am another anyone anything
    away back bad because before best better big both bring called came case
    cases come comes common could course day different doing done down during
    each easy else end enough even ever every example examples exam exams fast
    faster few find first following good got great happen happens hard here
    idea important instead keep kind kinds last later least less let like little
    long look lot lots made main make makes making many matter maybe might mind
    much must name need needs never new next nice nothing now number often okay
    old once one ones part people place point possible pretty probably put quite
    rather real really reason right said same say says see seem seems sense
    several short since small something sometimes soon sorry still stuff sure
    take takes talk tell than thank thanks thing things think though thought
    three through time times today together topic topics total true try trying
    turn two type types under until upon use used useful uses using usually
    want wants way ways well went whether within without word words work worked
    working works world write wrong year years yes yet""".split()
)


@dataclass(frozen=True)
class Phrase:
    stems: tuple[str, ...]
    text: str
    kind: Kind
    ref: str  # concept slug, topic slug or subject slug
    primary: bool = True  # the canonical name rather than an alias


@dataclass
class Lexicon:
    index: ConceptIndex
    corrector: SpellingCorrector
    abbreviations: dict[str, str]
    phrases: dict[str, list[Phrase]] = field(default_factory=dict)  # first stem -> phrases
    single_stems: dict[str, list[Phrase]] = field(default_factory=dict)  # for compounds
    topic_names: dict[str, str] = field(default_factory=dict)
    subject_names: dict[str, str] = field(default_factory=dict)
    topic_subjects: dict[str, list[str]] = field(default_factory=dict)
    concept_topic: dict[str, str] = field(default_factory=dict)
    grammar_words: frozenset[str] = frozenset()

    def add(self, text: str, kind: Kind, ref: str, primary: bool = True) -> None:
        stems = name_stems(text)
        if not stems:
            return
        p = Phrase(stems, text, kind, ref, primary)
        bucket = self.phrases.setdefault(stems[0], [])
        if all((q.stems, q.kind, q.ref) != (stems, kind, ref) for q in bucket):
            bucket.append(p)
            if len(stems) == 1:
                self.single_stems.setdefault(stems[0], []).append(p)

    def is_ordinary(self, word: str) -> bool:
        return word in STOPWORDS or word in QUERY_STOPWORDS or word in self.grammar_words


def _grammar_words() -> frozenset[str]:
    """Every literal word in the intent grammar, plus common conversational words."""
    sources = [r.pattern.pattern for r in RULES]
    sources += [p.pattern for _, p, _ in FOLLOW_UP_RULES]
    sources += [p.pattern for _, p in DEPTH_RULES] + [REFERENCE.pattern]
    # Drop regex escapes (\b, \s) first so "\bprerequisites" yields "prerequisites".
    found = {w for s in sources for w in re.findall(r"[a-z]{3,}", re.sub(r"\\[a-zA-Z]", " ", s))}
    return frozenset(found | COMMON_WORDS)


def build_lexicon(session: Session, index: ConceptIndex, content_dir: Path) -> Lexicon:
    abbreviations = load_abbreviations(content_dir)
    grammar = _grammar_words()
    vocabulary = list(index.surface.elements())
    vocabulary += list(STOPWORDS | QUERY_STOPWORDS | grammar)
    topics = session.scalars(select(Topic)).all()
    name_texts = [t for names in index.names.values() for _, t in names]
    name_texts += [t.name for t in topics]
    name_words = [w for text in name_texts for w in words(text)]
    whole_names = [ws[0] for text in name_texts if len(ws := words(text)) == 1]
    lex = Lexicon(
        index=index,
        corrector=SpellingCorrector(vocabulary, name_words, whole_names),
        abbreviations=abbreviations,
        grammar_words=grammar,
    )
    for concept_id, names in index.names.items():
        concept = index.concepts[concept_id]
        lex.concept_topic[concept.slug] = concept.topic_slug
        for _, text in names:
            lex.add(text, "concept", concept.slug, primary=text == concept.name)
    for topic in topics:
        lex.topic_names[topic.slug] = topic.name
        lex.add(topic.name, "topic", topic.slug)
    for subject, link in session.execute(
        select(Subject, SubjectTopic)
        .join(SubjectTopic, SubjectTopic.subject_id == Subject.id)
        .where(Subject.is_custom.is_(False))
    ).tuples():
        linked = session.get(Topic, link.topic_id)
        if linked is None:
            continue
        lex.subject_names[subject.slug] = subject.name
        lex.topic_subjects.setdefault(linked.slug, []).append(subject.slug)
        for text in (subject.name, *subject.aliases):
            lex.add(text, "subject", subject.slug)
    return lex


_cache: dict[object, Lexicon] = {}
_lock = threading.Lock()


def get_lexicon(session: Session, index: ConceptIndex, content_dir: Path) -> Lexicon:
    # Curriculum edits do not change the index fingerprint, so count them in too.
    curriculum = session.execute(
        select(func.count(SubjectTopic.topic_id), func.count(func.distinct(Topic.id)))
        .select_from(Topic)
        .outerjoin(SubjectTopic, SubjectTopic.topic_id == Topic.id)
    ).one()
    key = (index.signature, str(content_dir), tuple(curriculum))
    with _lock:
        lex = _cache.get(key)
        if lex is None:
            _cache.clear()
            lex = _cache[key] = build_lexicon(session, index, content_dir)
        return lex
