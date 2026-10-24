"""Suggest the topic (and so the module) an exam question is about.

Each topic of the exam's subject becomes one BM25 document built from the
curriculum and the knowledge base: the topic name, its concepts' names and
aliases (weighted up), the topic summary and the concept definitions. A
question's text is the query. Concept and topic names found as a phrase in
the question add a fixed bonus, as in the tutor's concept search.

Suggestions are only offered; nothing is mapped until the student confirms.
A weak best match gives no suggestion, and close scores give several
candidates instead of one. A module heading printed on the paper ("Module II")
is used only when the subject has a module with that number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from scholariq.db.models import Concept, SubjectModule, SubjectTopic, Topic
from scholariq.knowledge.index import allowed_trust
from scholariq.retrieval.bm25 import BM25Index
from scholariq.retrieval.text import analyse, query_terms

FIELD_WEIGHTS = {"topic": 4.0, "concept": 3.0, "summary": 1.0, "definition": 1.0}
NAME_BONUS = 1.5  # per word of a name found as a phrase in the question
# Per topic-name word found in the question, scaled by the share of the name
# covered ("binary search tree" covers all of "Trees and binary search trees").
TOPIC_WORD_BONUS = 1.5
# Light length normalisation: a topic with many concepts is not "about" a
# word less than a topic with few.
BM25_B = 0.3
# Higher than the tutor's 1.2 so that a word in many concept names of a topic
# counts for more than one passing mention in another topic's definitions.
BM25_K1 = 3.0
MIN_SCORE = 2.5  # below this the best match is too weak to suggest
CLOSE_RATIO = 0.75  # a runner-up this close makes the suggestion ambiguous
KEEP_RATIO = 0.5  # candidates scoring under this share of the best are dropped
PAPER_MODULE_BOOST = 1.25

Status = Literal["clear", "ambiguous", "none"]


@dataclass(frozen=True)
class Candidate:
    topic_id: str
    topic_name: str
    module_id: str | None
    score: float
    matched: tuple[str, ...]


@dataclass
class Suggestion:
    status: Status
    candidates: list[Candidate] = field(default_factory=list)
    # Module named on the paper and found in the subject, if any.
    paper_module_id: str | None = None


@dataclass
class _TopicDoc:
    topic: Topic
    module_id: str | None
    names: list[tuple[str, ...]]
    topic_words: frozenset[str]


class TopicSuggester:
    def __init__(self, session: Session, subject_id: str, allow_unreviewed: bool) -> None:
        links = session.execute(
            select(SubjectTopic, Topic)
            .join(Topic, SubjectTopic.topic_id == Topic.id)
            .where(SubjectTopic.subject_id == subject_id)
            .order_by(SubjectTopic.position)
        ).all()
        self.modules = {
            m.number: m.id
            for m in session.scalars(
                select(SubjectModule).where(SubjectModule.subject_id == subject_id)
            )
        }
        concepts: dict[str, list[Concept]] = {}
        topic_ids = [t.id for _, t in links]
        for c in session.scalars(
            select(Concept).where(
                Concept.topic_id.in_(topic_ids),
                Concept.trust_status.in_(allowed_trust(allow_unreviewed)),
            )
        ):
            concepts.setdefault(c.topic_id, []).append(c)
        w = FIELD_WEIGHTS
        corpus = []
        self.docs: dict[str, _TopicDoc] = {}
        for link, topic in links:
            fields = [(topic.name, w["topic"]), (topic.summary or "", w["summary"])]
            names = [topic.name]
            for c in concepts.get(topic.id, []):
                fields += [(c.canonical_name, w["concept"]), (c.definition, w["definition"])]
                fields += [(a, w["concept"]) for a in c.aliases]
                names += [c.canonical_name, *c.aliases]
            corpus.append((topic.id, fields))
            phrases = [p for n in names if (p := tuple(analyse(n)))]
            words = frozenset(analyse(topic.name))
            self.docs[topic.id] = _TopicDoc(topic, link.module_id, phrases, words)
        self.index = BM25Index(corpus, k1=BM25_K1, b=BM25_B) if corpus else None

    def paper_module(self, heading: str | None) -> str | None:
        if not heading:
            return None
        m = re.search(r"(\d+)\s*$", heading)
        return self.modules.get(int(m.group(1))) if m else None

    def suggest(self, text: str, paper_module: str | None = None) -> Suggestion:
        module_hint = self.paper_module(paper_module)
        # Single letters in exam questions are variables ("A+B*C"), not topics.
        pairs = [(st, w) for st, w in query_terms(text) if len(w) > 1]
        if self.index is None or not pairs:
            return Suggestion("none", paper_module_id=module_hint)
        seq = [s for s, _ in pairs]
        surface = dict(reversed(pairs))
        hits = self.index.search(seq, k=len(self.docs))
        scored = []
        for h in hits:
            doc = self.docs[h.doc_id]
            longest = max((len(p) for p in doc.names if _contains(seq, p)), default=0)
            covered = doc.topic_words & set(seq)
            coverage = len(covered) / len(doc.topic_words) if doc.topic_words else 0.0
            score = h.score + NAME_BONUS * longest + TOPIC_WORD_BONUS * len(covered) * coverage
            if module_hint and doc.module_id == module_hint:
                score *= PAPER_MODULE_BOOST
            matched = tuple(dict.fromkeys(surface.get(t, t) for t in h.contributions))
            scored.append(
                Candidate(doc.topic.id, doc.topic.name, doc.module_id, round(score, 3), matched)
            )
        scored.sort(key=lambda c: (-c.score, c.topic_name))
        if not scored or scored[0].score < MIN_SCORE:
            return Suggestion("none", paper_module_id=module_hint)
        best = scored[0].score
        kept = [c for c in scored if c.score >= best * KEEP_RATIO][:3]
        close = len(kept) > 1 and kept[1].score >= best * CLOSE_RATIO
        return Suggestion("ambiguous" if close else "clear", kept, module_hint)


def _contains(seq: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return n > 0 and any(tuple(seq[i : i + n]) == phrase for i in range(len(seq) - n + 1))
