"""The gold-standard answer set must keep passing.

The floor is below the current result so a content edit does not fail the
suite outright, but any wrongly answered out-of-scope question fails it.
"""

from __future__ import annotations

from pathlib import Path

from scholariq.answering.engine import Engine
from scholariq.answering.evaluate import load_cases, run
from scholariq.knowledge.evaluate import seed_session
from scholariq.knowledge.index import build_index
from scholariq.nlu.lexicon import build_lexicon

CONTENT = Path(__file__).resolve().parents[2] / "content"


def test_gold_answers() -> None:
    cases = load_cases(CONTENT / "eval/answers.yaml")
    with seed_session(CONTENT) as session:
        index = build_index(session, allow_unreviewed=True)
        engine = Engine(session, build_lexicon(session, index, CONTENT), allow_unreviewed=True)
        results = run(engine, cases)
    failures = [f"{r.case.q}: {'; '.join(r.problems)}" for r in results if not r.passed]
    held_out = [r for r in results if r.case.group == "held_out"]
    assert sum(r.passed for r in held_out) / len(held_out) >= 0.9, failures
    assert len(failures) <= 3, failures
    wrongly_answered = [
        r.case.q for r in results if r.case.status == "abstained" and r.answer.status == "answered"
    ]
    assert not wrongly_answered
