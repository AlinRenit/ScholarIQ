"""Okapi BM25 over weighted fields.

Each document is a list of (text, weight) fields. A field's tokens count
``weight`` times toward term frequency and length, a simple form of BM25F that
lets a concept's name outweigh a passing mention in an explanation.

    score(q, d) = sum over query terms t of
        idf(t) * tf(t, d) * (k1 + 1) / (tf(t, d) + k1 * (1 - b + b * len(d) / avglen))
    idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))

Every hit reports each matched term's contribution, so a ranking can be
explained term by term.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from scholariq.retrieval.text import analyse


@dataclass(frozen=True)
class Hit:
    doc_id: str
    score: float
    # stem -> contribution to the score
    contributions: dict[str, float]


class BM25Index:
    def __init__(
        self,
        docs: Sequence[tuple[str, Sequence[tuple[str, float]]]],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self.k1, self.b = k1, b
        self.tf: dict[str, dict[str, float]] = {}
        self.length: dict[str, float] = {}
        df: Counter[str] = Counter()
        self.postings: dict[str, list[str]] = defaultdict(list)
        for doc_id, fields in docs:
            counts: dict[str, float] = defaultdict(float)
            for text, weight in fields:
                for term in analyse(text):
                    counts[term] += weight
            self.tf[doc_id] = dict(counts)
            self.length[doc_id] = sum(counts.values())
            for term in counts:
                df[term] += 1
                self.postings[term].append(doc_id)
        self.n = len(self.tf)
        self.avglen = (sum(self.length.values()) / self.n) if self.n else 0.0
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @property
    def vocabulary(self) -> set[str]:
        return set(self.idf)

    def search(self, terms: Sequence[str], k: int = 10) -> list[Hit]:
        scores: dict[str, dict[str, float]] = defaultdict(dict)
        for term in dict.fromkeys(terms):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for doc_id in self.postings[term]:
                tf = self.tf[doc_id][term]
                norm = 1 - self.b + self.b * self.length[doc_id] / self.avglen
                scores[doc_id][term] = idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        hits = [Hit(d, sum(c.values()), c) for d, c in scores.items()]
        hits.sort(key=lambda h: (-h.score, h.doc_id))
        return hits[:k]
