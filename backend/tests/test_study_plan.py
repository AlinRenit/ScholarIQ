"""Study plan: the priority formula, prerequisite order and the plan API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from scholariq.analytics.policy import PlanRules
from scholariq.analytics.subjects import Band
from scholariq.domain.enums import MasteryClass
from scholariq.planning.plan import TopicInput, build_plan
from tests.test_analytics_api import import_semester3
from tests.test_diagnostics import right_answers
from tests.test_import_api import new_profile

NOW = datetime(2026, 10, 22, tzinfo=UTC)
M = MasteryClass


def t(tid: str, label: MasteryClass, importance: int | None = 3, **kw: object) -> TopicInput:
    return TopicInput(tid, tid.upper(), label, importance, 120, **kw)  # type: ignore[arg-type]


def test_formula_terms_add_up_and_are_explained() -> None:
    [e] = build_plan([t("a", M.NEEDS_ATTENTION, 5)], {}, set(), PlanRules(), NOW)
    # need 1.0*3 + importance 1.0*2 + goal 0 + unlocks 0 + recent 0 - time 0.4*0.5
    assert e.priority == pytest.approx(4.8)
    assert sum(term.contribution for term in e.terms.values()) == pytest.approx(e.priority)
    assert e.terms["need"].why == "Classified needs attention"
    assert e.terms["study_time"].contribution == pytest.approx(-0.2)


def test_weaker_topics_rank_higher_and_strong_ones_are_left_out() -> None:
    plan = build_plan(
        [t("ok", M.DEVELOPING), t("weak", M.NEEDS_ATTENTION), t("solid", M.STRONG)],
        {},
        set(),
        PlanRules(),
        NOW,
    )
    assert [e.topic.topic_id for e in plan] == ["weak", "ok"]


def test_goals_low_subject_marks_and_recent_quizzes_raise_priority() -> None:
    rules = PlanRules()
    base = build_plan([t("x", M.INSUFFICIENT_EVIDENCE)], {}, set(), rules, NOW)[0].priority
    goal = build_plan([t("x", M.INSUFFICIENT_EVIDENCE)], {}, {"x"}, rules, NOW)[0]
    assert goal.priority == pytest.approx(base + 2.0)
    weak_subject = build_plan(
        [t("x", M.INSUFFICIENT_EVIDENCE, subject_bands=(Band.NEEDS_ATTENTION,))],
        {},
        set(),
        rules,
        NOW,
    )[0]
    assert weak_subject.priority == pytest.approx(base + 0.6)
    quiz = build_plan(
        [t("x", M.DEVELOPING, last_quiz=(0.4, NOW - timedelta(days=3)))], {}, set(), rules, NOW
    )[0]
    assert quiz.terms["recent_result"].value == pytest.approx(0.6)
    stale = build_plan(
        [t("x", M.DEVELOPING, last_quiz=(0.4, NOW - timedelta(days=90)))], {}, set(), rules, NOW
    )[0]
    assert stale.terms["recent_result"].value == 0
    # A strong topic stays in the plan when the student chose it.
    assert build_plan([t("s", M.STRONG)], {}, {"s"}, rules, NOW)


def test_prerequisites_come_first_and_cycles_do_not_loop() -> None:
    topics = [
        t("advanced", M.NEEDS_ATTENTION, 5),
        t("basics", M.DEVELOPING, 2),
        t("other", M.DEVELOPING, 4),
    ]
    plan = build_plan(topics, {"advanced": {"basics"}}, set(), PlanRules(), NOW)
    order = [e.topic.topic_id for e in plan]
    assert order.index("basics") < order.index("advanced")
    basics = next(e for e in plan if e.topic.topic_id == "basics")
    assert basics.moved_for == "advanced"
    assert next(e for e in plan if e.topic.topic_id == "advanced").after == ["basics"]
    assert basics.terms["unlocks"].value == pytest.approx(1 / 3)

    cyclic = build_plan(
        [t("a", M.DEVELOPING), t("b", M.DEVELOPING)],
        {"a": {"b"}, "b": {"a"}},
        set(),
        PlanRules(),
        NOW,
    )
    assert sorted(e.topic.topic_id for e in cyclic) == ["a", "b"]


@pytest.mark.usefixtures("knowledge")
def test_plan_api_follows_marksheet_goals_and_progress(client: TestClient, engine: Engine) -> None:
    new_profile(client)
    assert client.get("/api/study-plan").json() is None
    import_semester3(client)
    plan = client.post("/api/study-plan", json={"goal_topics": ["algo.dynamic-programming"]})
    assert plan.status_code == 201, plan.text
    body = plan.json()
    assert body["formula_version"] == "plan-formula/1"
    items = {i["topic_slug"]: i for i in body["items"]}
    assert (
        "algo.dynamic-programming" in items
        and items["algo.dynamic-programming"]["breakdown"]["goal"]
    )
    # DBMS marks may need attention, so its topics rank above Data Structures ones.
    first = body["items"][0]
    assert first["breakdown"]["terms"]["need"]["why"].endswith("may need attention")
    positions = [i["position"] for i in body["items"]]
    assert positions == sorted(positions)
    for i in body["items"]:
        for pre in i["breakdown"]["after"]:
            assert any(
                j["topic_name"] == pre and j["position"] < i["position"] for j in body["items"]
            )

    # Marking a lesson completed is progress, not mastery.
    target = items["db.normalization"]
    r = client.patch(f"/api/study-plan/items/{target['id']}", json={"status": "lesson_completed"})
    assert r.status_code == 200 and r.json()["status"] == "lesson_completed"
    topic = next(x for x in client.get("/api/topics").json() if x["slug"] == "db.normalization")
    assert topic["classification"] == "insufficient_evidence"

    # A strong quiz result moves the topic out of the plan; statuses survive regeneration.
    quiz = client.post("/api/practice/quizzes", json={"topic": "ds.hashing"}).json()
    client.post(
        f"/api/practice/quizzes/{quiz['id']}/submit",
        json={"answers": right_answers(engine, quiz["id"])},
    )
    again = client.post("/api/study-plan", json={"goal_topics": []}).json()
    slugs = {i["topic_slug"]: i for i in again["items"]}
    assert "ds.hashing" not in slugs
    assert "Hashing" in again["parameters"]["left_out_strong"]
    assert slugs["db.normalization"]["status"] == "lesson_completed"


@pytest.mark.usefixtures("knowledge")
def test_plan_items_are_private(client: TestClient) -> None:
    new_profile(client)
    item = client.post("/api/study-plan", json={"goal_topics": ["os.deadlocks"]}).json()["items"][0]
    client.cookies.clear()
    new_profile(client)
    r = client.patch(f"/api/study-plan/items/{item['id']}", json={"status": "skipped"})
    assert r.status_code == 404
    assert client.post("/api/study-plan", json={"goal_topics": ["nope"]}).status_code == 404
