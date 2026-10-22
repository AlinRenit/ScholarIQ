"""Question understanding: normalising, spelling, intent grammar, linking."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from scholariq.knowledge.index import build_index
from scholariq.nlu.intents import (
    Depth,
    FollowUp,
    Intent,
    match_follow_up,
    match_intents,
    requested_depth,
    step_number,
)
from scholariq.nlu.lexicon import Lexicon, build_lexicon
from scholariq.nlu.normalise import load_abbreviations, normalise
from scholariq.nlu.parser import Context, parse, split_parts
from scholariq.nlu.spelling import SpellingCorrector, edit_distance
from tests.conftest import REPO_ROOT

CONTENT = REPO_ROOT / "content"


@pytest.fixture
def lexicon(knowledge: None, engine: Engine) -> Iterator[Lexicon]:
    with Session(engine) as session:
        yield build_lexicon(session, build_index(session, allow_unreviewed=True), CONTENT)


# --------------------------------------------------------------------- normalise


def test_normalise_keeps_notation_and_expands_shorthand() -> None:
    ab = load_abbreviations(CONTENT)
    n = normalise("diff b/w  stack and queue?", ab)
    assert n.text == "difference between stack and queue?"
    assert ("b/w", "between") in n.expansions
    # Notation and single-letter variables are left exactly as typed.
    assert normalise("Solve T(n) = 2T(n/2) + n", ab).text == "Solve T(n) = 2T(n/2) + n"
    assert normalise("is R = {(1,2)} symmetric", ab).text == "is R = {(1,2)} symmetric"
    assert normalise("x \u2212 1 \u2264 y", ab).text == "x - 1 \u2264 y"


def test_normalise_splits_out_code() -> None:
    fenced = normalise("```python\nfor i in range(n):\n    pass\n```\nwhat is the complexity?")
    assert fenced.text == "what is the complexity?"
    assert fenced.code[0].language == "python"
    assert "    pass" in fenced.code[0].code
    pasted = normalise(
        "what does this do\nfor i in range(n):\n    for j in range(n):\n        s += 1"
    )
    assert pasted.text == "what does this do"
    assert pasted.code and "for j" in pasted.code[0].code


# ---------------------------------------------------------------------- spelling


def test_edit_distance_counts_adjacent_swaps_once() -> None:
    assert edit_distance("explian", "explain") == 1
    assert edit_distance("semafore", "semaphore") == 2
    assert edit_distance("abc", "abc") == 0


def test_corrector_is_conservative_and_prefers_names() -> None:
    c = SpellingCorrector(["three", "three", "thread", "semaphore"], names=["thread"])
    assert c.correct("thred").corrected == "thread"  # type: ignore[union-attr]
    assert c.correct("semafore").corrected == "semaphore"  # type: ignore[union-attr]
    assert c.correct("thre") is None  # four letters, and "three" is not a name
    assert c.correct("bananas") is None  # nothing close


def test_four_letter_words_correct_only_to_one_whole_name() -> None:
    c = SpellingCorrector(["stack", "heap", "head", "heat"], names=["stack", "heap", "head"])
    assert c.correct("stak").corrected == "stack"  # type: ignore[union-attr]
    assert c.correct("hea") is None  # three letters: never
    assert c.correct("heaf") is None  # heap and head are both one edit away


def test_stopword_prefixes_are_joined(lexicon: Lexicon) -> None:
    assert normalise("what is an i-node").text == "what is an inode"
    assert normalise("B-tree vs x-1").text == "B-tree vs x-1"
    assert [m.refs for m in parse("what is an i-node", lexicon).concepts()] == [("os.inode",)]
    assert parse("what is a node", lexicon).concepts() == []  # "i-node" does not claim "node"


# ------------------------------------------------------------------------ intents

SPEC_EXAMPLES = [
    ("What is normalization?", Intent.DEFINITION),
    ("Explain how virtual memory works.", Intent.EXPLANATION),
    ("What is the difference between a process and a thread?", Intent.COMPARISON),
    ("How do I calculate the time complexity of this algorithm?", Intent.PROCEDURE),
    ("Solve this recurrence relation.", Intent.WORKED_PROBLEM),
    ("Why can deadlocks occur?", Intent.REASONING),
    ("What should I learn before studying graph algorithms?", Intent.PREREQUISITES),
    ("Give me questions on binary search.", Intent.PRACTICE),
    ("What should I study first based on my results?", Intent.STUDY_ADVICE),
]


@pytest.mark.parametrize(("text", "intent"), SPEC_EXAMPLES)
def test_intent_grammar_on_spec_examples(text: str, intent: Intent) -> None:
    assert match_intents(text)[0].intent is intent


def test_follow_up_phrases() -> None:
    assert match_follow_up("Can you explain the second step again?")[0] is FollowUp.REPEAT_STEP  # type: ignore[index]
    assert step_number("Can you explain the second step again?") == 2
    assert step_number("the last step please") == -1
    assert match_follow_up("simplify this")[0] is FollowUp.SIMPLIFY  # type: ignore[index]
    assert match_follow_up("show me an example")[0] is FollowUp.EXAMPLE  # type: ignore[index]
    assert requested_depth("explain quick sort") is Depth.STANDARD  # "quick" is not "quickly"
    assert requested_depth("explain paging in detail") is Depth.DEEPER
    assert requested_depth("briefly, what is a heap") is Depth.SIMPLER


def test_split_parts() -> None:
    assert split_parts("What is a stack? How is a queue different?") == [
        "What is a stack?",
        "How is a queue different?",
    ]
    assert split_parts("What is a stack?") == ["What is a stack?"]


# ------------------------------------------------------------------------ parsing


def test_parse_links_concepts_and_corrects_spelling(lexicon: Lexicon) -> None:
    p = parse("diff b/w process and thred", lexicon)
    assert p.intent is Intent.COMPARISON
    assert [m.refs for m in p.concepts()] == [("os.process",), ("os.thread",)]
    assert [(c.typed, c.corrected) for c in p.corrections] == [("thred", "thread")]
    assert any("Corrected" in t for t in p.trace)


def test_topic_names_beat_aliases_but_not_own_topic_aliases(lexicon: Lexicon) -> None:
    # "Normalization" is a topic; no concept uses it as its own name.
    assert [m.kind for m in parse("What is normalization?", lexicon).mentions] == ["topic"]
    # "virtual memory" is an alias of the concept that its own topic is named after.
    p = parse("Explain how virtual memory works", lexicon)
    assert [m.refs for m in p.concepts()] == [("os.virtual-memory-concept",)]


def test_compound_words(lexicon: Lexicon) -> None:
    assert [m.refs for m in parse("explain quick sort", lexicon).concepts()] == [("ds.quicksort",)]


def test_coverage_marks_unknown_words(lexicon: Lexicon) -> None:
    p = parse("who won the world cup", lexicon)
    assert set(p.unmatched) == {"won", "cup"}
    assert p.coverage == 0
    assert parse("what is a semaphore", lexicon).coverage == 1


def test_follow_up_needs_context(lexicon: Lexicon) -> None:
    assert parse("explain the second step again", lexicon).intent is Intent.EXPLANATION
    p = parse("explain the second step again", lexicon, Context(concepts=["algo.dijkstra"]))
    assert p.intent is Intent.FOLLOW_UP
    assert p.follow_up is FollowUp.REPEAT_STEP
    assert p.step == 2
    # Naming a new concept is a new question, not a follow-up.
    q = parse("what is a heap?", lexicon, Context(concepts=["algo.dijkstra"]))
    assert q.intent is Intent.DEFINITION


def test_content_dir_exists() -> None:
    assert Path(CONTENT, "lexicon.yaml").exists()
