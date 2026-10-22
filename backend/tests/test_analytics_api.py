"""Import -> analysis -> topic evidence through the HTTP API."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_import_api import confirmed_rows, new_profile, upload

pytestmark = pytest.mark.usefixtures("curriculum")


def import_semester3(client: TestClient) -> None:
    doc = upload(client, "digital_semester3.pdf").json()
    r = client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assert r.status_code == 200, r.text


def topics_by_name(client: TestClient) -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in client.get("/api/topics").json()}


def test_imported_subjects_match_curriculum(client: TestClient) -> None:
    new_profile(client)
    import_semester3(client)
    overview = client.get("/api/analytics/overview").json()
    subjects = {s["name"]: s for s in overview["subjects"]}
    # "Data Structures Lab" is the lab component of Data Structures, not a new subject.
    assert set(subjects) == {
        "Data Structures",
        "Operating Systems",
        "Database Management Systems",
        "Computer Networks",
        "Discrete Mathematics",
    }
    assert all(not s["is_custom"] and s["mapped_topics"] > 0 for s in subjects.values())
    ds = subjects["Data Structures"]
    assert ds["latest"] == {"percent": 81.3, "basis": "marks"} and ds["band"] == "strong"
    assert subjects["Database Management Systems"]["band"] == "needs_attention"
    assert subjects["Computer Networks"]["latest"] is None
    assert overview["overall"]["marks_percentage"]["value"] == 68.9
    assert overview["overall"]["credit_weighted_percentage"]["value"] == 70.3
    # Grades were kept as printed (no scale), so no GPA is claimed.
    assert overview["overall"]["gpa"]["value"] is None
    assert overview["trend"]["direction"] == "insufficient_data"
    assert any("absent" in g for g in overview["data_gaps"])


def test_topics_start_with_insufficient_evidence(client: TestClient) -> None:
    new_profile(client)
    import_semester3(client)
    topics = topics_by_name(client)
    assert {t["classification"] for t in topics.values()} == {"insufficient_evidence"}
    norm = topics["Normalization"]
    assert norm["subjects"][0]["name"] == "Database Management Systems"
    assert norm["subject_messages"][0].startswith(
        "Your Database Management Systems score suggests this subject may need attention."
    )
    assert [e["kind"] for e in norm["evidence"]] == ["subject_score_prior"]
    assert norm["evidence"][0]["removable"] is False


def test_topic_test_evidence_updates_classification(client: TestClient) -> None:
    new_profile(client)
    import_semester3(client)
    norm_id = topics_by_name(client)["Normalization"]["id"]
    r = client.post(
        f"/api/topics/{norm_id}/evidence",
        json={"kind": "topic_exam", "obtained": "9", "maximum": "10", "questions": 10},
    )
    assert r.status_code == 201, r.text
    norm = topics_by_name(client)["Normalization"]
    # (0.45 * 1 + 0.9 * 10) / 11 = 0.859
    assert norm["classification"] == "strong"
    # Removing student-entered evidence reverts the classification.
    exam = next(e for e in norm["evidence"] if e["kind"] == "topic_exam")
    assert client.delete(f"/api/topics/evidence/{exam['id']}").status_code == 204
    assert topics_by_name(client)["Normalization"]["classification"] == "insufficient_evidence"


def test_derived_evidence_cannot_be_deleted(client: TestClient) -> None:
    new_profile(client)
    import_semester3(client)
    prior = topics_by_name(client)["SQL"]["evidence"][0]
    assert client.delete(f"/api/topics/evidence/{prior['id']}").status_code == 409


def test_self_report_validation(client: TestClient) -> None:
    new_profile(client)
    import_semester3(client)
    tid = topics_by_name(client)["SQL"]["id"]
    assert (
        client.post(f"/api/topics/{tid}/evidence", json={"kind": "self_report"}).status_code == 422
    )
    r = client.post(f"/api/topics/{tid}/evidence", json={"kind": "self_report", "rating": 2})
    assert r.status_code == 201
    sql = topics_by_name(client)["SQL"]
    assert sql["classification"] == "insufficient_evidence"
    assert any("self-assessment" in x for x in sql["reasons"])


def test_custom_subject_mapping_and_remap(client: TestClient) -> None:
    new_profile(client)
    doc = upload(client, "theory_practical.xlsx").json()
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    overview = client.get("/api/analytics/overview").json()
    subjects = {s["name"]: s for s in overview["subjects"]}
    compiler = subjects["Compiler Design"]
    assert compiler["is_custom"] and compiler["mapped_topics"] == 0
    assert any("No topic mapping for" in g for g in overview["data_gaps"])

    curriculum = {s["slug"]: s for s in client.get("/api/curriculum/subjects").json()}
    complexity = next(t for t in curriculum["algorithms"]["topics"] if t["slug"] == "ds.complexity")
    r = client.put(
        f"/api/curriculum/subjects/{compiler['id']}/topics", json={"topic_ids": [complexity["id"]]}
    )
    assert r.status_code == 200, r.text
    assert "Compiler Design" in [
        s["name"] for t in client.get("/api/topics").json() for s in t["subjects"]
    ]

    # Curriculum subjects are not editable through the API.
    r = client.put(
        f"/api/curriculum/subjects/{curriculum['dbms']['id']}/topics", json={"topic_ids": []}
    )
    assert r.status_code == 409

    # Remap the student's "Software Engineering" results onto DBMS (contrived but valid).
    se = subjects["Software Engineering"]
    r = client.post(
        "/api/academics/subjects/remap",
        json={"from_subject_id": se["id"], "to_subject_id": curriculum["dbms"]["id"]},
    )
    assert r.json() == {"results_moved": 1}
    names = {s["name"] for s in client.get("/api/analytics/overview").json()["subjects"]}
    assert "Software Engineering" not in names and "Database Management Systems" in names


def test_two_semesters_show_a_trend(client: TestClient) -> None:
    new_profile(client)
    import_semester3(client)
    csv = (
        b"Subject,Max Marks,Marks,Semester\n"
        b"Operating Systems,100,61,4\nComputer Networks,100,64,4\n"
    )
    r = client.post("/api/documents", files={"file": ("sem4.csv", csv, "text/csv")})
    d = r.json()
    client.post(f"/api/documents/{d['id']}/confirm", json={"results": confirmed_rows(d)})
    trend = client.get("/api/analytics/overview").json()["trend"]
    assert trend["direction"] == "declining" and trend["change_points"] == -6.4


def test_analytics_requires_profile(client: TestClient) -> None:
    assert client.get("/api/analytics/overview").status_code == 401
    assert client.get("/api/topics").status_code == 401


def test_shared_custom_subject_mapping_is_protected(client: TestClient) -> None:
    for name in ("Asha", "Ravi"):
        client.cookies.clear()
        new_profile(client, name)
        doc = upload(client, "theory_practical.xlsx").json()
        payload = {"results": confirmed_rows(doc)}
        r = client.post(f"/api/documents/{doc['id']}/confirm", json=payload)
        assert r.status_code == 200, r.text
    subjects = {s["name"]: s for s in client.get("/api/analytics/overview").json()["subjects"]}
    r = client.put(
        f"/api/curriculum/subjects/{subjects['Compiler Design']['id']}/topics",
        json={"topic_ids": []},
    )
    assert r.status_code == 409
    assert "Another profile" in r.json()["detail"]
