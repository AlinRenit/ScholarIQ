"""The answer engine against the seed knowledge base."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from scholariq.answering.engine import Engine as AnswerEngine
from scholariq.answering.engine import Request, UnbackedSection, validate
from scholariq.answering.model import Answer, Origin, Section
from scholariq.db.models import Concept, KnowledgeDocument
from scholariq.domain.enums import MasteryClass
from scholariq.knowledge.index import build_index
from scholariq.nlu.intents import Depth, FollowUp
from scholariq.nlu.lexicon import build_lexicon
from scholariq.tutoring.policy import plan_for
from tests.conftest import REPO_ROOT


@pytest.fixture
def session(knowledge: None, engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


def make(session: Session, allow_unreviewed: bool = True) -> AnswerEngine:
    index = build_index(session, allow_unreviewed)
    return AnswerEngine(
        session,
        build_lexicon(session, index, REPO_ROOT / "content"),
        allow_unreviewed=allow_unreviewed,
    )


def ask(eng: AnswerEngine, text: str, req: Request | None = None) -> Answer:
    return eng.answer(req or Request(text)).answer


@pytest.mark.parametrize(
    ("text", "handler", "concepts"),
    [
        ("What is a stack?", "A", ["ds.stack"]),
        ("Explain how virtual memory works.", "A", ["os.virtual-memory-concept"]),
        (
            "What is the difference between a process and a thread?",
            "B",
            ["os.process", "os.thread"],
        ),
        ("How do I calculate the time complexity of this algorithm?", "C", ["ds.complexity-big-o"]),
        ("Why can deadlocks occur?", "A", ["os.deadlock"]),
        ("Give me questions on binary search.", "practice", ["ds.binary-search"]),
        ("semafore", "A", ["os.semaphore"]),
        ("Solve T(n) = 2T(n/2) + n", "D", ["algo.master-theorem"]),
    ],
)
def test_question_types_reach_the_right_handler(
    session: Session, text: str, handler: str, concepts: list[str]
) -> None:
    a = ask(make(session), text)
    assert a.status == "answered"
    assert a.handler == handler
    assert [c.slug for c in a.concepts] == concepts


def test_prerequisites_are_in_study_order(session: Session) -> None:
    a = ask(make(session), "What should I learn before studying graph algorithms?")
    assert a.handler == "prerequisites"
    names = [i.text for i in a.sections[0].items]
    assert names.index("Graph") < names.index("Graph representation")


def test_definition_answer_follows_the_template(session: Session) -> None:
    a = ask(make(session), "What is a stack?")
    kinds = [s.kind for s in a.sections]
    assert kinds[0] == "definition" and "facts" in kinds and "example" in kinds
    assert kinds[-1] == "check"
    check = a.sections[-1].question
    assert check is not None and "option_index" not in check.model_dump_json()


def test_answers_from_unreviewed_content_are_labelled(session: Session) -> None:
    a = ask(make(session), "What is a stack?")
    assert not a.review.all_reviewed
    assert a.review.label and "Not yet reviewed by a person" in a.review.label
    assert a.review.unreviewed == ["ds.stack"]


def test_reviewed_only_mode_abstains_rather_than_using_unreviewed_content(session: Session) -> None:
    a = ask(make(session, allow_unreviewed=False), "What is a stack?")
    assert a.status == "abstained"
    assert a.handler == "F"


@pytest.mark.parametrize(
    "text", ["who won the world cup", "what is a black hole", "photosynthesis", "capital of France"]
)
def test_out_of_scope_questions_are_declined_honestly(session: Session, text: str) -> None:
    a = ask(make(session), text)
    assert a.status == "abstained" and a.handler == "F"
    assert a.missing
    assert all(s.kind != "definition" for s in a.sections)


def test_close_candidates_get_a_clarifying_question(session: Session) -> None:
    a = ask(make(session), "processes waiting for each other forever")
    assert a.status == "clarify" and a.clarification is not None
    assert "os.deadlock" in [c.slug for c in a.concepts]
    assert all(o.query for o in a.clarification.options)


@pytest.mark.parametrize(
    "text", ["relation", "processes waiting for each other forever", "compare stack with"]
)
def test_every_clarifying_option_leads_to_an_answer(session: Session, text: str) -> None:
    eng = make(session)
    a = ask(eng, text)
    assert a.clarification is not None
    for option in a.clarification.options:
        assert option.query
        picked = ask(eng, "", Request(option.query, meaning=option.concept))
        assert picked.status == "answered", (option.label, picked.interpretation)
        if option.concept:
            assert option.concept in [c.slug for c in picked.concepts]


def test_comparison_uses_only_recorded_attributes(session: Session) -> None:
    a = ask(make(session), "tcp vs udp")
    table = a.sections[0]
    assert table.kind == "table" and table.columns == ["", "TCP", "UDP"]
    tcp = session.scalar(select(Concept).where(Concept.slug == "cn.tcp"))
    assert tcp is not None
    recorded = {k.replace("_", " ").capitalize() for k in tcp.attributes if not k.startswith("_")}
    for label, left, _ in table.rows[1:]:
        assert left == "Not recorded in the knowledge base" or label in recorded


def test_comparison_with_one_name_asks_for_the_other(session: Session) -> None:
    a = ask(make(session), "compare stack with")
    assert a.status == "clarify"
    assert "ds.queue" in [c.slug for c in a.concepts]


def test_follow_ups_use_the_previous_answer(session: Session) -> None:
    eng = make(session)
    first = eng.answer(Request("Explain Dijkstra's algorithm"))
    assert first.context.steps, "the procedure's steps are remembered for follow-ups"
    again = eng.answer(Request("Can you explain the second step again?", first.context)).answer
    assert again.handler == "follow-up"
    assert again.sections[0].steps == [first.context.steps[1]]
    simpler = eng.answer(Request("", first.context, FollowUp.SIMPLIFY)).answer
    assert simpler.personalisation and simpler.personalisation.level == "guided"
    test_me = eng.answer(Request("", first.context, FollowUp.CHECK)).answer
    assert test_me.handler == "practice"


def test_multi_part_questions_carry_context(session: Session) -> None:
    a = ask(make(session), "what is a stack? and how is a queue different?")
    assert a.handler == "multi"
    assert [c.slug for c in a.concepts] == ["ds.stack", "ds.queue"]
    assert any(s.kind == "table" for s in a.sections)


def test_unsupported_problem_lists_what_is_supported(session: Session) -> None:
    a = ask(make(session), "solve the travelling salesman problem for my city")
    assert a.status == "abstained"


def test_code_question_is_analysed_without_running(session: Session) -> None:
    a = ask(
        make(session), "what is the complexity?\n```python\nfor i in range(n):\n    print(i)\n```"
    )
    assert a.handler == "E"
    table = next(s for s in a.sections if s.kind == "table")
    assert table.rows[0][-1] == "Θ(n)"
    assert "without running it" in " ".join(a.limitations)


# --------------------------------------------------------- depth, not truth


def knowledge_texts(session: Session, slug: str) -> set[str]:
    c = session.scalar(select(Concept).where(Concept.slug == slug))
    assert c is not None
    docs = session.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.concept_id == c.id)
    ).all()
    texts = {c.definition, *(str(v) for v in c.attributes.values())}
    for d in docs:
        texts |= {d.body, *d.steps}
    return texts


@pytest.mark.parametrize("depth", [Depth.SIMPLER, Depth.STANDARD, Depth.DEEPER])
def test_every_level_teaches_the_same_facts(session: Session, depth: Depth) -> None:
    eng = make(session)
    a = eng.answer(
        Request(
            f"Explain deadlock{' simply' if depth is Depth.SIMPLER else ''}"
            f"{' in detail' if depth is Depth.DEEPER else ''}"
        )
    ).answer
    allowed = knowledge_texts(session, "os.deadlock")
    for s in a.sections:
        if s.kind in ("definition", "explanation", "example", "procedure", "misconception"):
            assert s.text in allowed or s.text is None
            assert all(step in allowed for step in s.steps)
        if s.kind == "facts":
            assert all(v in allowed for _, v in s.rows)
    definition = next(s for s in a.sections if s.kind == "definition")
    assert definition.text == session.scalar(
        select(Concept.definition).where(Concept.slug == "os.deadlock")
    )


def test_levels_differ_only_in_how_much_they_include(session: Session) -> None:
    from scholariq.answering.handlers.base import HandlerContext
    from scholariq.answering.handlers.explain import explain_concept
    from scholariq.nlu.parser import parse

    eng = make(session)
    p = parse("explain deadlock", eng.lex)
    ctx = HandlerContext(session, eng.allowed, p, eng._plan)
    b = ctx.bundle("os.deadlock")
    assert b is not None
    strong = explain_concept(ctx, b, plan_for(MasteryClass.STRONG, Depth.STANDARD, "Deadlocks"))
    weak = explain_concept(
        ctx, b, plan_for(MasteryClass.NEEDS_ATTENTION, Depth.STANDARD, "Deadlocks")
    )
    assert len(weak) > len(strong)
    strong_text = {s.text for s in strong if s.text}
    weak_text = {s.text for s in weak if s.text}
    assert strong_text <= weak_text | {None}
    assert strong[-1].title == "Challenge question" and weak[-1].title == "Check your understanding"


def test_validation_rejects_unbacked_sections() -> None:
    with pytest.raises(UnbackedSection):
        validate([Section(kind="definition", title="x", text="y", origin=Origin(kind="knowledge"))])
    with pytest.raises(UnbackedSection):
        validate([Section(kind="note", title="x", origin=Origin(kind="solver"))])
