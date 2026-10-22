"""Tutor HTTP API: conversations, follow-ups, checking, privacy."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from scholariq.core.config import Settings
from scholariq.db.models import Conversation, Message, Student, Topic, TopicEvidence
from scholariq.domain.enums import EvidenceKind
from scholariq.tutoring.service import purge_expired


def profile(client: TestClient, name: str = "Asha") -> None:
    r = client.post("/api/profile", json={"display_name": name, "consent": True})
    assert r.status_code in (200, 201), r.text


def ask(client: TestClient, text: str = "", **kw: object) -> dict:  # type: ignore[type-arg]
    r = client.post("/api/tutor/ask", json={"text": text, **kw})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_tutor_needs_a_profile(client: TestClient, knowledge: None) -> None:
    assert client.post("/api/tutor/ask", json={"text": "What is a stack?"}).status_code == 401


def test_info_needs_no_profile(client: TestClient) -> None:
    body = client.get("/api/tutor/info").json()
    assert body["retention_days"] == 30
    assert body["rules_version"] == "tutor-rules/1"
    assert any("recurrence" in s.lower() for s in body["solvers"])


def test_ask_follow_up_and_history(client: TestClient, knowledge: None) -> None:
    profile(client)
    first = ask(client, "What is a stack?")
    conv = first["conversation_id"]
    assert first["answer"]["handler"] == "A"
    assert first["answer"]["review"]["all_reviewed"] is False

    simpler = ask(client, action="simplify", conversation_id=conv)
    assert simpler["answer"]["personalisation"]["level"] == "guided"
    assert [c["slug"] for c in simpler["answer"]["concepts"]] == ["ds.stack"]

    history = client.get(f"/api/tutor/conversations/{conv}").json()
    assert [m["role"] for m in history["messages"]] == ["student", "tutor", "student", "tutor"]
    assert history["messages"][1]["answer"]["concepts"][0]["slug"] == "ds.stack"
    listed = client.get("/api/tutor/conversations").json()
    assert listed[0]["id"] == conv and listed[0]["messages"] == 4


def test_actions_need_a_conversation(client: TestClient, knowledge: None) -> None:
    profile(client)
    r = client.post("/api/tutor/ask", json={"action": "simplify"})
    assert r.status_code == 422
    assert client.post("/api/tutor/ask", json={"text": "  "}).status_code == 422


def test_check_marks_answers_without_recording_evidence(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    answer = ask(client, "What is a stack?")["answer"]
    q = next(s["question"] for s in answer["sections"] if s["question"])
    results = [
        client.post(
            "/api/tutor/check", json={"question": q["slug"], "response": {"option_index": i}}
        ).json()
        for i in range(len(q["options"]))
    ]
    assert sum(r["correct"] for r in results) == 1
    assert all(r["recorded_as_evidence"] is False and r["explanation"] for r in results)
    bad = client.post(
        "/api/tutor/check", json={"question": q["slug"], "response": {"option_index": 99}}
    )
    assert bad.status_code == 422
    with Session(engine) as s:
        assert s.scalar(select(func.count(TopicEvidence.id))) == 0


def test_conversations_are_private(client: TestClient, knowledge: None, settings: Settings) -> None:
    profile(client, "Asha")
    conv = ask(client, "What is a queue?")["conversation_id"]
    client.cookies.clear()
    profile(client, "Ben")
    assert client.get(f"/api/tutor/conversations/{conv}").status_code == 404
    assert client.delete(f"/api/tutor/conversations/{conv}").status_code == 404
    r = client.post("/api/tutor/ask", json={"text": "and a stack?", "conversation_id": conv})
    assert r.status_code == 404


def test_delete_conversation_and_delete_my_data(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    a = ask(client, "What is a heap?")["conversation_id"]
    ask(client, "What is a trie?")
    assert client.delete(f"/api/tutor/conversations/{a}").status_code == 204
    assert len(client.get("/api/tutor/conversations").json()) == 1
    assert client.delete("/api/profile").status_code == 204
    with Session(engine) as s:
        assert s.scalar(select(func.count(Conversation.id))) == 0
        assert s.scalar(select(func.count(Message.id))) == 0


def test_old_conversations_expire(
    client: TestClient, knowledge: None, engine: Engine, settings: Settings
) -> None:
    profile(client)
    ask(client, "What is a heap?")
    old = datetime.now(UTC) - timedelta(days=settings.conversation_retention_days + 1)
    with Session(engine) as s:
        s.execute(update(Message).values(created_at=old))
        s.execute(update(Conversation).values(created_at=old))
        student_id = s.scalars(select(Student.id)).one()
        assert purge_expired(s, settings, student_id) == 1
        s.commit()
    assert client.get("/api/tutor/conversations").json() == []


def test_questions_are_not_logged(
    client: TestClient, knowledge: None, caplog: pytest.LogCaptureFixture
) -> None:
    profile(client)
    with caplog.at_level(logging.DEBUG):
        ask(client, "What is a zebra-crossing-secret-question?")
    assert "zebra-crossing-secret-question" not in caplog.text


def test_teaching_depth_follows_topic_evidence(
    client: TestClient, knowledge: None, engine: Engine
) -> None:
    profile(client)
    with Session(engine) as s:
        student_id = s.scalars(select(Student.id)).one()
        topic = s.scalars(select(Topic).where(Topic.slug == "os.deadlocks")).one()
        s.add(
            TopicEvidence(
                student_id=student_id,
                topic_id=topic.id,
                kind=EvidenceKind.TOPIC_EXAM,
                score=Decimal("0.2"),
                sample_size=10,
            )
        )
        s.commit()
    weak = ask(client, "Explain deadlock")["answer"]
    assert weak["personalisation"]["classification"] == "needs_attention"
    assert weak["personalisation"]["level"] == "guided"
    with Session(engine) as s:
        s.execute(update(TopicEvidence).values(score=Decimal("0.95")))
        s.commit()
    strong = ask(client, "Explain deadlock")["answer"]
    assert strong["personalisation"]["level"] == "overview"
    assert len(strong["sections"]) < len(weak["sections"])
    # Same definition either way: depth changes, facts do not.
    assert strong["sections"][0]["text"] == weak["sections"][0]["text"]
    # Asking about a topic is not evidence.
    with Session(engine) as s:
        assert s.scalar(select(func.count(TopicEvidence.id))) == 1


def test_study_advice_uses_evidence(client: TestClient, knowledge: None, engine: Engine) -> None:
    profile(client)
    with Session(engine) as s:
        student_id = s.scalars(select(Student.id)).one()
        for slug, score in (("os.deadlocks", "0.2"), ("ds.hashing", "0.9")):
            topic = s.scalars(select(Topic).where(Topic.slug == slug)).one()
            s.add(
                TopicEvidence(
                    student_id=student_id,
                    topic_id=topic.id,
                    kind=EvidenceKind.TOPIC_EXAM,
                    score=Decimal(score),
                    sample_size=10,
                )
            )
        s.commit()
    a = ask(client, "What should I study first based on my results?")["answer"]
    assert a["handler"] == "advice"
    items = a["sections"][0]["items"]
    assert items[0]["text"] == "Deadlocks"
    assert all(i["text"] != "Hashing" for i in items)
