"""Match a subject name printed on a marksheet to a known subject."""

from __future__ import annotations

import re
from collections.abc import Sequence

from rapidfuzz import fuzz

from scholariq.curriculum.schema import normalise_name
from scholariq.db.models import Subject

_LAB_SUFFIX = re.compile(r"\s+(lab|laboratory|practical|practicals)$")
# Edit-distance similarity required to accept a near match (typos, OCR slips).
FUZZY_MIN = 92


def _names(subject: Subject) -> set[str]:
    names = {normalise_name(subject.name), *(normalise_name(a) for a in subject.aliases)}
    if subject.code:
        names.add(normalise_name(subject.code))
    return {n for n in names if n}


def match_subject(subjects: Sequence[Subject], name: str, code: str | None) -> Subject | None:
    """Exact code, then exact name/alias (with and without a lab suffix), then a
    close spelling match. Curriculum subjects win over custom ones."""
    ordered = sorted(subjects, key=lambda s: s.is_custom)
    if code:
        c = normalise_name(code)
        for s in ordered:
            if c in _names(s):
                return s
    norm = normalise_name(name)
    variants = [norm]
    if (stripped := _LAB_SUFFIX.sub("", norm)) != norm:
        variants.append(stripped)
    for v in variants:
        for s in ordered:
            if v in _names(s):
                return s
    best: tuple[int, Subject | None] = (0, None)
    for v in variants:
        if len(v) < 8:
            continue
        for s in ordered:
            for n in _names(s):
                score = int(fuzz.ratio(v, n))
                if score >= FUZZY_MIN and score > best[0]:
                    best = (score, s)
    return best[1]
