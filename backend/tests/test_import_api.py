"""Import workflow through the HTTP API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scholariq.core.config import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "marksheets"


def new_profile(client: TestClient, name: str = "Asha") -> None:
    r = client.post("/api/profile", json={"display_name": name, "consent": True})
    assert r.status_code == 201, r.text


def upload(client: TestClient, name: str) -> Any:
    with (FIXTURES / name).open("rb") as f:
        return client.post("/api/documents", files={"file": (name, f, "application/octet-stream")})


def confirmed_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn review records into a confirm payload, as the review screen does."""
    keys = ("subject_name", "subject_code", "component", "status", "marks_obtained",
            "max_marks", "grade", "grade_points", "credits", "semester", "exam_type",
            "exam_name")  # fmt: skip
    return [{k: r["fields"].get(k) for k in keys if k in r["fields"]} for r in detail["records"]]


def test_profile_required(client: TestClient) -> None:
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/profile").status_code == 401


def test_profile_requires_consent(client: TestClient) -> None:
    r = client.post("/api/profile", json={"display_name": "A", "consent": False})
    assert r.status_code == 422


def test_forged_cookie_rejected(client: TestClient) -> None:
    new_profile(client)
    token = client.cookies["scholariq_session"]
    student_id = token.rsplit(".", 1)[0]
    client.cookies.set("scholariq_session", f"{student_id}.{'0' * 64}")
    assert client.get("/api/profile").status_code == 401


def test_upload_review_confirm(client: TestClient) -> None:
    new_profile(client)
    r = upload(client, "digital_semester3.pdf")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["status"] == "extracted"
    assert doc["analysis"]["grades_seen"] == ["A", "A+", "C", "D", "O"]
    assert len(doc["records"]) == 6

    # Nothing is an academic record until confirmed.
    assert client.get("/api/academics/assessments").json() == []

    rows = confirmed_rows(doc)
    rows[2]["marks_obtained"] = "47"  # student corrects an OCR/extraction error
    # The 10-point template has no "D", so it is refused rather than guessed.
    r = client.post(
        f"/api/documents/{doc['id']}/confirm",
        json={"results": rows, "grading": {"template": "ugc_cbcs_10"}},
    )
    assert r.status_code == 422 and "D" in r.json()["detail"]
    scale = {"O": 10, "A+": 9, "A": 8, "B+": 7, "B": 6, "C": 5, "D": 4, "F": 0}
    r = client.post(
        f"/api/documents/{doc['id']}/confirm",
        json={
            "results": rows,
            "grading": {"custom": {"name": "Institute scale", "max_points": 10, "points": scale}},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["results_saved"] == 6

    assessments = client.get("/api/academics/assessments").json()
    assert len(assessments) == 1
    a = assessments[0]
    assert (a["semester"], a["exam_type"], a["exam_name"]) == (3, "regular", "November 2025")
    results = {x["subject_name"]: x for x in a["results"]}
    assert results["Database Management Systems"]["marks_obtained"] == "47.00"
    assert results["Computer Networks"]["status"] == "absent"
    assert results["Computer Networks"]["marks_obtained"] is None
    # Grade points come only from the scale the student chose.
    assert results["Discrete Mathematics"]["grade_points"] == "10.00"

    # Extraction rows are removed after confirmation; re-confirming is refused.
    detail = client.get(f"/api/documents/{doc['id']}").json()
    assert detail["status"] == "confirmed" and detail["records"] == []
    again = client.post(f"/api/documents/{doc['id']}/confirm", json={"results": rows})
    assert again.status_code == 409


def test_grades_without_scale_are_stored_unconverted(client: TestClient) -> None:
    new_profile(client)
    doc = upload(client, "unruled_grades.pdf").json()
    rows = confirmed_rows(doc)
    for r in rows:
        r.pop("grade_points", None)
    r = client.post(f"/api/documents/{doc['id']}/confirm", json={"results": rows})
    assert r.status_code == 200, r.text
    results = [x for a in client.get("/api/academics/assessments").json() for x in a["results"]]
    assert all(x["grade_points"] is None and x["grading_scale_id"] is None for x in results)
    # Repeated subject becomes a second attempt, not an overwrite.
    physics = sorted(x["attempt_number"] for x in results if x["subject_code"] == "PH101")
    assert physics == [1, 2]


def test_scale_must_cover_every_grade(client: TestClient) -> None:
    new_profile(client)
    doc = upload(client, "semicolon_missing_max.csv").json()
    rows = confirmed_rows(doc)
    r = client.post(
        f"/api/documents/{doc['id']}/confirm",
        json={"results": rows, "grading": {"template": "ugc_cbcs_10"}},
    )
    assert r.status_code == 422
    assert "XQ" in r.json()["detail"]
    custom = {"custom": {"name": "My college", "max_points": 10, "points": {"XQ": 3, "B": 6}}}
    r = client.post(
        f"/api/documents/{doc['id']}/confirm", json={"results": rows, "grading": custom}
    )
    assert r.status_code == 200, r.text


@pytest.mark.parametrize(
    "bad",
    [
        {"subject_name": "X", "status": "present"},  # no marks or grade
        {"subject_name": "X", "status": "absent", "marks_obtained": "0"},
        {"subject_name": "X", "marks_obtained": "60", "max_marks": "50"},
        {"subject_name": "X", "marks_obtained": "-1"},
        {"subject_name": "X", "marks_obtained": "5", "semester": 40},
        {"subject_name": "", "marks_obtained": "5"},
    ],
)
def test_confirm_validates_rows(client: TestClient, bad: dict[str, Any]) -> None:
    new_profile(client)
    doc = upload(client, "percentages.csv").json()
    r = client.post(f"/api/documents/{doc['id']}/confirm", json={"results": [bad]})
    assert r.status_code == 422


def test_missing_result_saved_without_marks(client: TestClient) -> None:
    new_profile(client)
    doc = upload(client, "percentages.csv").json()
    rows = confirmed_rows(doc)
    r = client.post(f"/api/documents/{doc['id']}/confirm", json={"results": rows})
    assert r.status_code == 200, r.text
    results = client.get("/api/academics/assessments").json()[0]["results"]
    db = next(x for x in results if x["subject_name"] == "Database Systems")
    assert db["status"] == "missing" and db["marks_obtained"] is None


def test_duplicate_upload(client: TestClient) -> None:
    new_profile(client)
    first = upload(client, "percentages.csv").json()
    r = upload(client, "percentages.csv")
    assert r.status_code == 409
    assert r.json()["detail"]["document_id"] == first["id"]


def test_rejected_upload_messages(client: TestClient) -> None:
    new_profile(client)
    r = upload(client, "png_named_csv.csv")
    assert r.status_code == 422
    assert "does not match" in r.json()["detail"]


def test_students_cannot_see_each_others_documents(client: TestClient, settings: Settings) -> None:
    new_profile(client, "A")
    doc = upload(client, "percentages.csv").json()
    client.cookies.clear()
    new_profile(client, "B")
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404
    assert client.get("/api/documents").json() == []


def test_delete_document_removes_file_and_results(client: TestClient, settings: Settings) -> None:
    new_profile(client)
    doc = upload(client, "percentages.csv").json()
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assert len(list(settings.upload_dir.iterdir())) == 1
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert list(settings.upload_dir.iterdir()) == []
    assert client.get("/api/academics/assessments").json() == []


def test_delete_my_data(client: TestClient, settings: Settings) -> None:
    new_profile(client)
    for name in ("percentages.csv", "digital_semester3.pdf"):
        doc = upload(client, name).json()
        client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assert len(list(settings.upload_dir.iterdir())) == 2
    assert client.delete("/api/profile").status_code == 204
    assert list(settings.upload_dir.iterdir()) == []
    assert client.get("/api/profile").status_code == 401


def test_zero_retention_deletes_file_on_confirm(client: TestClient, settings: Settings) -> None:
    settings.upload_retention_days = 0
    new_profile(client)
    doc = upload(client, "percentages.csv").json()
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assert list(settings.upload_dir.iterdir()) == []
    assert client.get(f"/api/documents/{doc['id']}").json()["file_retained"] is False


def test_unreadable_scan_without_ocr_fails_cleanly(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    new_profile(client)
    r = upload(client, "scanned_semester4.png")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "failed"
    assert "Tesseract" in body["error"]
    assert list(settings.upload_dir.iterdir()) == []


def test_upload_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from scholariq.api import deps
    from scholariq.core.ratelimit import RateLimiter

    monkeypatch.setattr(deps, "upload_limiter", RateLimiter(limit=1, window_seconds=60))
    import scholariq.api.routes.documents as docs_routes

    monkeypatch.setattr(docs_routes, "upload_limiter", deps.upload_limiter)
    new_profile(client)
    assert upload(client, "percentages.csv").status_code == 201
    assert upload(client, "plain_report.txt").status_code == 429
