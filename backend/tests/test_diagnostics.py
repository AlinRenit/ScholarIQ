"""Diagnostic quizzes: selection, shuffling, marking and evidence."""

from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from scholariq.db.models import DiagnosticAttempt, QuizSession, VerifiedAnswer
from scholariq.diagnostics.quiz import Candidate, choose, option_order

TOPIC = "ds.stacks-queues"


def cand(slug: str, style: str = "conceptual", difficulty: int = 2, shown: int = 0) -> Candidate:
    return Candidate(slug, slug, style, difficulty, shown, None)


def test_choose_prefers_unseen_questions_and_mixes_styles() -> None:
    pool = [cand(f"c{i}", shown=1) for i in range(4)] + [
        cand("new1"),
        cand("new2"),
        cand("app", "application", shown=3),
    ]
    picked = {c.slug for c in choose(pool, 3, "seed")}
    assert {"new1", "new2"} <= picked
    assert "app" in picked, "an application question is swapped in when none was picked"


def test_choose_is_deterministic_and_orders_easiest_first() -> None:
    pool = [cand(f"q{i}", difficulty=3 - i % 3) for i in range(8)]
    a, b = choose(pool, 5, "s1"), choose(pool, 5, "s1")
    assert a == b
    assert [c.difficulty for c in a] == sorted(c.difficulty for c in a)


def test_option_order_is_a_stable_permutation_that_moves_answers() -> None:
    assert sorted(option_order("s", "q", 4)) == [0, 1, 2, 3]
    assert option_order("s", "q", 4) == option_order("s", "q", 4)
    # Over many quizzes the stored answer (index 1) lands in every position.
    positions = Counter(option_order(f"quiz{i}", "q", 4).index(1) for i in range(200))
    assert set(positions) == {0, 1, 2, 3}
    assert min(positions.values()) > 25


def profile(client: TestClient, name: str = "Asha") -> None:
    assert client.post("/api/profile", json={"display_name": name, "consent": True}).is_success


def right_answers(engine: Engine, quiz_id: str, wrong: int = 0) -> dict[str, int]:
    """Displayed index of the correct option for each question; the first `wrong` are missed."""
    with Session(engine) as s:
        quiz = s.get(QuizSession, quiz_id)
        assert quiz is not None
        out = {}
        for n, item in enumerate(quiz.items):
            key = s.scalar(
                select(VerifiedAnswer).where(VerifiedAnswer.question_id == item["question_id"])
            )
            assert key is not None
            shown = item["order"].index(key.answer["option_index"])
            out[item["slug"]] = (shown + 1) % len(item["order"]) if n < wrong else shown
        return out


def topic(client: TestClient, slug: str = TOPIC) -> dict:  # type: ignore[type-arg]
    return next(t for t in client.get("/api/topics").json() if t["slug"] == slug)


def test_quiz_needs_a_profile(client: TestClient, knowledge: None) -> None:
    assert client.post("/api/practice/quizzes", json={"topic": TOPIC}).status_code == 401


def test_quiz_updates_topic_evidence_and_classification(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    quiz = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    assert len(quiz["questions"]) == 5
    assert {q["style"] for q in quiz["questions"]} == {"conceptual", "application"}
    assert quiz["submitted_at"] is None and quiz["marked"] == []
    assert all(q["trust"] in ("imported", "verified") for q in quiz["questions"])

    r = client.post(
        f"/api/practice/quizzes/{quiz['id']}/submit",
        json={"answers": right_answers(engine, quiz["id"], wrong=1)},
    )
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["correct"] == 4 and done["recorded_as_evidence"]
    assert done["before"]["classification"] == "insufficient_evidence"
    assert done["after"]["classification"] == "strong"
    assert done["after"]["direct_observations"] == 5
    missed = [m for m in done["marked"] if not m["correct"]]
    assert len(missed) == 1 and missed[0]["explanation"]
    assert missed[0]["chosen"] != missed[0]["correct_option"]

    t = topic(client)
    assert t["classification"] == "strong"
    assert any(e["description"] == "Diagnostic quiz: 4 of 5 correct" for e in t["evidence"])
    assert not any(e["removable"] for e in t["evidence"] if e["kind"] == "diagnostic")

    # The stored quiz still shows the same marking afterwards.
    again = client.get(f"/api/practice/quizzes/{quiz['id']}").json()
    assert again["marked"] == done["marked"]


def test_retake_uses_different_questions_first(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    first = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    client.post(
        f"/api/practice/quizzes/{first['id']}/submit",
        json={"answers": right_answers(engine, first["id"])},
    )
    second = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    seen = {q["slug"] for q in first["questions"]}
    fresh = [q["slug"] for q in second["questions"] if q["slug"] not in seen]
    assert len(fresh) == min(5, second["available"] - len(seen))


def test_submission_rules(client: TestClient, knowledge: None, engine: Engine) -> None:
    profile(client)
    quiz = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    answers = right_answers(engine, quiz["id"])
    partial = dict(list(answers.items())[:2])
    r = client.post(f"/api/practice/quizzes/{quiz['id']}/submit", json={"answers": partial})
    assert r.status_code == 422 and "3 left" in r.json()["detail"]
    url = f"/api/practice/quizzes/{quiz['id']}/submit"
    assert client.post(url, json={"answers": answers}).status_code == 200
    assert client.post(url, json={"answers": answers}).status_code == 422
    assert client.post("/api/practice/quizzes", json={"topic": "nope"}).status_code == 404


def test_quizzes_are_private(client: TestClient, knowledge: None) -> None:
    profile(client)
    quiz = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    client.cookies.clear()
    profile(client, "Ben")
    assert client.get(f"/api/practice/quizzes/{quiz['id']}").status_code == 404


def test_delete_my_data_removes_quizzes(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    quiz = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    client.post(
        f"/api/practice/quizzes/{quiz['id']}/submit",
        json={"answers": right_answers(engine, quiz["id"])},
    )
    assert client.delete("/api/profile").status_code == 204
    with Session(engine) as s:
        assert s.get(QuizSession, quiz["id"]) is None
        assert s.scalar(select(DiagnosticAttempt)) is None


def test_practice_overview_lists_history(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    quiz = client.post("/api/practice/quizzes", json={"topic": TOPIC}).json()
    topics = {t["slug"]: t for t in client.get("/api/practice/topics").json()}
    assert len(topics) == 40 and all(t["questions"] >= 5 for t in topics.values())
    assert topics[TOPIC]["open_quiz"] == quiz["id"]
    client.post(
        f"/api/practice/quizzes/{quiz['id']}/submit",
        json={"answers": right_answers(engine, quiz["id"])},
    )
    t = {t["slug"]: t for t in client.get("/api/practice/topics").json()}[TOPIC]
    assert t["open_quiz"] is None
    assert [(q["correct"], q["total"]) for q in t["quizzes"]] == [(5, 5)]
