"""Concept search over the knowledge base.

One retrievable unit per concept, built from its name and aliases (weight 3),
definition (2), topic name and document titles (1.5) and document bodies (1),
ranked with BM25.

Two fixed re-ranking rules sit on top of BM25:

* Name match: if the question contains a concept's name or alias as a phrase
  ("binary search", "3NF"), that concept gets NAME_BONUS per matched word, so
  the concept being asked about outranks pages that merely mention its words.
* Compounds: adjacent question words are also tried joined ("quick sort" ->
  "quicksort") when the joined word exists in the knowledge base.

The index is rebuilt only when knowledge content changes.
"""

from __future__ import annotations

import hashlib
import threading
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from scholariq.db.models import Concept, KnowledgeDocument, Topic
from scholariq.domain.enums import TrustStatus
from scholariq.retrieval.bm25 import BM25Index
from scholariq.retrieval.text import analyse, query_terms, stem, words

FIELD_WEIGHTS = {"name": 3.0, "definition": 2.0, "title": 1.5, "body": 1.0}
NAME_BONUS = 4.0


def name_stems(text: str) -> tuple[str, ...]:
    """Stems of a concept name, or () when analysis would make it misleading.

    A name that loses words and keeps only one ("i-node" -> node, because "i"
    is a stopword) would claim an ordinary word. A hyphenated one is joined
    instead (inode), as the question normaliser does; any other is not used.
    """
    stems = tuple(analyse(text))
    if len(stems) == 1 and len(words(text)) > 1:
        return name_stems(text.replace("-", "")) if "-" in text else ()
    return stems


@dataclass(frozen=True)
class ConceptEntry:
    id: str
    slug: str
    name: str
    topic_id: str
    topic_slug: str
    topic_name: str
    trust: TrustStatus


@dataclass(frozen=True)
class SearchHit:
    concept: ConceptEntry
    score: float
    # surface word from the query -> BM25 contribution
    matched: dict[str, float]
    # The concept name or alias found as a phrase in the query, if any.
    name_match: str | None = None
    name_bonus: float = 0.0


@dataclass
class ConceptIndex:
    bm25: BM25Index
    concepts: dict[str, ConceptEntry]
    signature: tuple[object, ...]
    # concept id -> [(analysed name or alias, original text)]
    names: dict[str, list[tuple[tuple[str, ...], str]]]
    # Every word as written in the indexed text, with its frequency (for spelling).
    surface: Counter[str] = field(default_factory=Counter)

    def _terms(self, query: str) -> tuple[list[str], dict[str, str]]:
        """Ordered query stems, plus every searchable stem mapped to its surface text."""
        pairs = query_terms(query)
        seq = [s for s, _ in pairs]
        surface: dict[str, str] = {}
        for s, w in pairs:
            surface.setdefault(s, w)
        vocab = self.bm25.vocabulary
        for (_, w1), (_, w2) in zip(pairs, pairs[1:], strict=False):
            joined = stem(w1 + w2)
            if joined in vocab and joined not in surface:
                surface[joined] = f"{w1} {w2}"
        return seq, surface

    def search(self, query: str, k: int = 10) -> list[SearchHit]:
        seq, surface = self._terms(query)
        if not surface:
            return []
        hits = self.bm25.search(list(surface), k=len(self.concepts))
        compounds = {t for t, w in surface.items() if " " in w}
        results = []
        for h in hits:
            best: tuple[int, str] | None = None
            for phrase, text in self.names.get(h.doc_id, []):
                if _contains(seq, phrase) or (len(phrase) == 1 and phrase[0] in compounds):
                    if best is None or len(phrase) > best[0]:
                        best = (len(phrase), text)
            bonus = NAME_BONUS * best[0] if best else 0.0
            results.append(
                SearchHit(
                    self.concepts[h.doc_id],
                    round(h.score + bonus, 4),
                    {surface[t]: round(v, 4) for t, v in h.contributions.items()},
                    best[1] if best else None,
                    bonus,
                )
            )
        results.sort(key=lambda r: (-r.score, r.concept.slug))
        return results[:k]

    def unmatched_terms(self, query: str) -> list[str]:
        """Query words that appear nowhere in the knowledge base."""
        _, surface = self._terms(query)
        vocab = self.bm25.vocabulary
        covered = {w for t, ws in surface.items() if t in vocab for w in ws.split()}
        return [w for _, w in query_terms(query) if w not in covered]


def _contains(seq: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return n > 0 and any(tuple(seq[i : i + n]) == phrase for i in range(len(seq) - n + 1))


def allowed_trust(allow_unreviewed: bool) -> tuple[TrustStatus, ...]:
    if allow_unreviewed:
        return (TrustStatus.VERIFIED, TrustStatus.IMPORTED)
    return (TrustStatus.VERIFIED,)


def _signature(session: Session, allowed: tuple[TrustStatus, ...]) -> tuple[object, ...]:
    """Fingerprint of the indexed content; it changes whenever a sync changes anything."""
    digest = hashlib.sha256()
    for row in session.execute(
        select(
            Concept.slug, Concept.trust_status, Concept.canonical_name, Concept.definition
        ).order_by(Concept.slug)
    ):
        digest.update(repr(tuple(row)).encode())
    for doc_row in session.execute(
        select(
            KnowledgeDocument.slug, KnowledgeDocument.trust_status, KnowledgeDocument.content_hash
        ).order_by(KnowledgeDocument.slug)
    ):
        digest.update(repr(tuple(doc_row)).encode())
    # The database URL keeps indexes for different databases (e.g. in tests) apart.
    return (str(session.get_bind().engine.url), allowed, digest.hexdigest())


def build_index(session: Session, allow_unreviewed: bool) -> ConceptIndex:
    allowed = allowed_trust(allow_unreviewed)
    signature = _signature(session, allowed)
    rows = session.execute(
        select(Concept, Topic)
        .join(Topic, Concept.topic_id == Topic.id)
        .where(Concept.trust_status.in_(allowed))
        .order_by(Concept.slug)
    ).all()
    docs_by_concept: dict[str, list[KnowledgeDocument]] = {}
    for d in session.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.trust_status.in_(allowed))
    ).all():
        if d.concept_id:
            docs_by_concept.setdefault(d.concept_id, []).append(d)

    entries: dict[str, ConceptEntry] = {}
    names: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    corpus = []
    surface: Counter[str] = Counter()
    w = FIELD_WEIGHTS
    for c, t in rows:
        entries[c.id] = ConceptEntry(
            c.id, c.slug, c.canonical_name, t.id, t.slug, t.name, c.trust_status
        )
        fields = [
            (c.canonical_name, w["name"]),
            (c.definition, w["definition"]),
            (t.name, w["title"]),
        ]
        fields += [(a, w["name"]) for a in c.aliases]
        names[c.id] = [
            (phrase, text)
            for text in (c.canonical_name, *c.aliases)
            if (phrase := name_stems(text))
        ]
        for d in docs_by_concept.get(c.id, []):
            fields += [
                (d.title, w["title"]),
                (d.body, w["body"]),
                *((s, w["body"]) for s in d.steps),
            ]
        corpus.append((c.id, fields))
        for text, _ in fields:
            surface.update(words(text))
    return ConceptIndex(BM25Index(corpus), entries, signature, names, surface)


_cache: dict[bool, ConceptIndex] = {}
_lock = threading.Lock()


def get_index(session: Session, allow_unreviewed: bool) -> ConceptIndex:
    """Return the cached index, rebuilding it if the knowledge base changed."""
    signature = _signature(session, allowed_trust(allow_unreviewed))
    with _lock:
        cached = _cache.get(allow_unreviewed)
        if cached is None or cached.signature != signature:
            cached = build_index(session, allow_unreviewed)
            _cache[allow_unreviewed] = cached
        return cached
