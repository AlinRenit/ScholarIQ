"""Tokenising for lexical retrieval.

The same pipeline runs over knowledge-base text and student questions:
lower-case, split into word tokens (keeping ``c++``, ``c#`` and digits inside
words such as ``3nf``), drop stopwords, unify British and American ``-ise`` /
``-ize`` spellings, then apply the Snowball English stemmer. Every step is a
fixed rule; nothing is learned.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import snowballstemmer

_TOKEN = re.compile(r"[a-z0-9]+(?:\+\+|#)?")
_ISE = re.compile(r"(?<=[a-z]{3})is(e|ed|es|ing|ation|ations|er|ers)$")

STOPWORDS = frozenset(
    """a an and are as at be been being but by can could did do does doing for from had
    has have how i if in into is it its me my of on or our should so than that the their
    them then there these they this those to was we were what when where which while who
    whom why will with would you your yours about also any each just more most other
    some such only own same too very s t""".split()
)

# Words that describe what kind of answer is wanted rather than what it is about.
# They are removed from queries (not from documents) so "explain stacks" and
# "stacks" retrieve the same concepts.
QUERY_STOPWORDS = frozenset(
    """explain explanation define definition meaning mean means describe tell give show
    example examples difference differences between compare comparison versus vs
    understand know learn please help question answer simple simply briefly detail
    detailed work works working""".split()
)

_stemmer = snowballstemmer.stemmer("english")


def fold(text: str) -> str:
    """Lower-case and strip accents so 'Dijkstra's' and 'dijkstras' meet."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().replace("’", "'").replace("'s ", " ").replace("'", "")


def words(text: str) -> list[str]:
    return _TOKEN.findall(fold(text))


@lru_cache(maxsize=50_000)
def stem(word: str) -> str:
    if not word.isalpha() or len(word) <= 3:
        return word
    return str(_stemmer.stemWord(_ISE.sub(r"iz\1", word)))


def analyse(text: str) -> list[str]:
    """Document-side analysis: tokens -> stems, stopwords removed."""
    return [stem(w) for w in words(text) if w not in STOPWORDS]


def query_terms(text: str) -> list[tuple[str, str]]:
    """Query-side analysis: (stem, surface word) pairs in question order."""
    return [(stem(w), w) for w in words(text) if w not in STOPWORDS and w not in QUERY_STOPWORDS]
