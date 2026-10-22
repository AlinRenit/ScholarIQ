"""Spelling correction against the knowledge base's own vocabulary.

A word is corrected only when it is unknown, alphabetic and long enough for a
match to mean something: five letters or more for one edit, eight or more for
two. A four-letter word gets one edit only towards a whole concept or topic
name, and only when exactly one such name is that close ("stak" -> stack).
Edits are Damerau-Levenshtein (insert, delete, substitute, swap adjacent
letters). Among candidates at the smallest distance, a word that is a whole
concept or topic name wins ("thred" -> thread, not three), then words used more
often in names, then the most frequent word overall, then the alphabetically
first, so results never depend on dictionary order.

Lookup uses symmetric deletes: every word is indexed under the strings made by
deleting up to two letters, and a typo meets its correction at a shared
deletion. Candidates are then checked with the true edit distance.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

MAX_EDITS = 2


def edit_distance(a: str, b: str) -> int:
    """Optimal string alignment distance (Damerau-Levenshtein, adjacent swaps)."""
    if a == b:
        return 0
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = ca != cb
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


def _deletes(word: str, depth: int) -> set[str]:
    out = {word}
    frontier = {word}
    for _ in range(depth):
        frontier = {w[:i] + w[i + 1 :] for w in frontier for i in range(len(w))}
        out |= frontier
    return out


def allowed_edits(word: str) -> int:
    if len(word) >= 8:
        return 2
    if len(word) >= 4:
        return 1
    return 0


@dataclass(frozen=True)
class Correction:
    typed: str
    corrected: str
    distance: int


class SpellingCorrector:
    def __init__(
        self, words: Iterable[str], name_words: Iterable[str] = (), names: Iterable[str] = ()
    ) -> None:
        self.freq: Counter[str] = Counter(w for w in words if w.isalpha())
        self.name_freq: Counter[str] = Counter(name_words)
        self.names = frozenset(names)
        self._index: dict[str, list[str]] = {}
        for w in self.freq:
            if len(w) >= 4:
                for d in _deletes(w, MAX_EDITS):
                    self._index.setdefault(d, []).append(w)

    def known(self, word: str) -> bool:
        return word in self.freq

    @lru_cache(maxsize=4096)  # noqa: B019  (one corrector per index; bounded)
    def correct(self, word: str) -> Correction | None:
        word = word.lower()
        limit = allowed_edits(word)
        if not word.isalpha() or limit == 0 or word in self.freq:
            return None
        candidates: set[str] = set()
        for d in _deletes(word, limit):
            candidates.update(self._index.get(d, ()))
        scored = [
            (dist, c not in self.names, -self.name_freq[c], -self.freq[c], c)
            for c in candidates
            if abs(len(c) - len(word)) <= limit and (dist := edit_distance(word, c)) <= limit
        ]
        if len(word) == 4:
            # Short words: only an unambiguous whole name counts.
            scored = [t for t in scored if not t[1]]
            if len(scored) != 1:
                return None
        if not scored:
            return None
        dist, *_, best = min(scored)
        return Correction(word, best, dist)
