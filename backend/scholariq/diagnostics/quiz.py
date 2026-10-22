"""Choosing and shuffling diagnostic quiz questions. Pure functions, no I/O.

Selection (``choose``):
1. Questions shown to the student least often come first, then those shown
   longest ago, so a retake uses different questions whenever the topic has
   enough of them.
2. Remaining ties are broken by a hash of the quiz seed and the question slug:
   fixed for a given quiz, different between quizzes.
3. If the pick has no application question (or no conceptual one) and the
   topic has one, the last-ranked question of the other style is swapped for it.
4. The chosen questions are shown easiest first.

Option order (``option_order``) is a permutation fixed by the quiz seed and the
question slug, so the correct answer is not always in the same place and the
same quiz always shows the same order.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candidate:
    question_id: str
    slug: str
    style: str  # "conceptual" | "application"
    difficulty: int
    times_shown: int = 0
    last_shown: datetime | None = None


def _hash(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def choose(candidates: list[Candidate], size: int, seed: str) -> list[Candidate]:
    def rank(c: Candidate) -> tuple[int, float, str]:
        last = c.last_shown.timestamp() if c.last_shown else 0.0
        return (c.times_shown, last, _hash(seed, c.slug))

    ranked = sorted(candidates, key=rank)
    picked = ranked[:size]
    rest = ranked[size:]
    for style in ("application", "conceptual"):
        if picked and not any(c.style == style for c in picked):
            extra = next((c for c in rest if c.style == style), None)
            if extra is not None:
                # Replace the lowest-ranked question of the over-represented style.
                drop = max((i for i, c in enumerate(picked) if c.style != style), default=None)
                if drop is not None:
                    rest.remove(extra)
                    picked[drop] = extra
    return sorted(picked, key=lambda c: (c.difficulty, _hash(seed, c.slug)))


def option_order(seed: str, slug: str, n: int) -> list[int]:
    """Displayed position i shows original option ``order[i]``."""
    return sorted(range(n), key=lambda i: _hash(seed, slug, str(i)))
