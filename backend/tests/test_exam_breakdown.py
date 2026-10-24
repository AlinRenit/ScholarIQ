"""Exam breakdowns end to end through the HTTP API, plus the pure arithmetic.

Numbers in comments refer to the acceptance cases of the feature request.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from scholariq.core.config import Settings
from scholariq.db.models import (
    AssessmentResult,
    Document,
    ExamQuestion,
    ExamQuestionMapping,
    TopicEvidence,
)
from scholariq.domain.enums import AttemptStatus, EvidenceKind
from scholariq.exams.analysis import Exclusion, MappingInput, QuestionInput, analyse
from scholariq.ingestion.extract import OcrUnavailable, tesseract_available
from tests.test_import_api import confirmed_rows, new_profile, upload

pytestmark = pytest.mark.usefixtures("knowledge")

PAPERS = Path(__file__).parent / "fixtures" / "question_papers"
D = Decimal


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def subject(client: TestClient, slug: str = "data-structures") -> dict[str, Any]:
    subjects = client.get("/api/curriculum/subjects").json()
    return next(s for s in subjects if s["slug"] == slug)


def topic_id(subj: dict[str, Any], slug: str) -> str:
    return next(t["id"] for t in subj["topics"] if t["slug"] == slug)


def module_id(subj: dict[str, Any], number: int) -> str:
    return next(m["id"] for m in subj["modules"] if m["number"] == number)


def create(client: TestClient, **body: Any) -> dict[str, Any]:
    body.setdefault("subject_id", subject(client)["id"])
    r = client.post("/api/exam-breakdowns", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def put(client: TestClient, b: dict[str, Any], questions: list[dict[str, Any]], **extra: Any):  # type: ignore[no-untyped-def]
    body = {
        "title": b["title"],
        "held_on": b.get("held_on"),
        "declared_total": b.get("declared_total"),
        "assessment_id": b.get("assessment_id"),
        "choice_rules": b.get("choice_rules", {}),
        "questions": questions,
    }
    body.update(extra)
    return client.put(f"/api/exam-breakdowns/{b['id']}", json=body)


def q(label: str, max_marks: Any, obtained: Any = None, status: str | None = None, **kw: Any):  # type: ignore[no-untyped-def]
    out: dict[str, Any] = {"label": label, "text": kw.pop("text", f"Question {label}")}
    if max_marks is not None:
        out["max_marks"] = str(max_marks)
    if obtained is not None:
        out["marks_obtained"] = str(obtained)
    if status is not None:
        out["attempt_status"] = status
    out.update(kw)
    return out


def topics(t: str | list[tuple[str, str]]) -> list[dict[str, Any]]:
    if isinstance(t, str):
        return [{"topic_id": t}]
    return [{"topic_id": tid, "share": share} for tid, share in t]


def analysis(client: TestClient, b: dict[str, Any]) -> dict[str, Any]:
    r = client.get(f"/api/exam-breakdowns/{b['id']}/analysis")
    assert r.status_code == 200, r.text
    return r.json()


def confirm(client: TestClient, b: dict[str, Any]) -> dict[str, Any]:
    r = client.post(f"/api/exam-breakdowns/{b['id']}/confirm")
    assert r.status_code == 200, r.text
    return r.json()


def evidence(engine: Engine, kind: EvidenceKind | None = None) -> list[TopicEvidence]:
    with Session(engine) as s:
        stmt = select(TopicEvidence)
        if kind is not None:
            stmt = stmt.where(TopicEvidence.kind == kind)
        return list(s.scalars(stmt))


def topic_view(client: TestClient, name: str) -> dict[str, Any]:
    return next(t for t in client.get("/api/topics").json() if t["name"] == name)


def upload_paper(client: TestClient, b: dict[str, Any], name: str, **params: Any) -> Any:
    path = PAPERS / name if (PAPERS / name).exists() else Path(name)
    with path.open("rb") as f:
        return client.post(
            f"/api/exam-breakdowns/{b['id']}/paper",
            params=params,
            files={"file": (path.name, f, "application/octet-stream")},
        )


# --------------------------------------------------------------------------- #
# Pure arithmetic
# --------------------------------------------------------------------------- #


def qi(
    label: str,
    mx: str | None,
    got: str | None,
    status: AttemptStatus = AttemptStatus.ATTEMPTED,
    optional: bool = False,
    review: bool = False,
    maps: tuple[MappingInput, ...] = (),
) -> QuestionInput:
    return QuestionInput(
        label, label, D(mx) if mx else None, D(got) if got else None, status, optional, review,
        maps,
    )  # fmt: skip


def test_percentages_are_sum_over_sum_not_mean_of_percentages() -> None:  # 9
    a = MappingInput("t1", None, D(1))
    r = analyse([qi("1", "2", "2", maps=(a,)), qi("2", "10", "5", maps=(a,))], {"t1": "m1"})
    t = r.topics["t1"]
    assert (t.earned, t.possible) == (D(7), D(12))  # 58.3%, not (100% + 50%) / 2 = 75%
    assert round(float(t.fraction or 0), 3) == 0.583
    assert r.modules["m1"].possible == D(12)


def test_inclusion_rules() -> None:  # 6, 7, 8
    r = analyse(
        [
            qi("1", "5", "0"),  # explicit zero: counted
            qi("2", "5", None),  # attempted, mark missing: left out, never zero
            qi("3", "5", None, AttemptStatus.NOT_ATTEMPTED),  # required, skipped: 0 / 5
            qi("4", "5", None, AttemptStatus.NOT_ATTEMPTED, optional=True),  # not chosen
            qi("5", "5", "4", AttemptStatus.UNKNOWN),  # status unknown: left out
            qi("6", None, None),  # maximum unknown: left out
            qi("7", "5", "5", review=True),  # flagged uncertain: left out
        ],
        {},
    )
    assert (r.overall.earned, r.overall.possible) == (D(0), D(10))
    assert r.overall.questions == ["1", "3"]
    assert r.excluded == {
        Exclusion.NO_MARK: ["2"],
        Exclusion.OPTIONAL_NOT_CHOSEN: ["4"],
        Exclusion.UNKNOWN_STATUS: ["5"],
        Exclusion.NO_MAX: ["6"],
        Exclusion.NEEDS_REVIEW: ["7"],
    }
    assert not r.complete


def test_split_question_is_not_counted_twice() -> None:  # 11
    maps = (MappingInput("a", None, D("0.6")), MappingInput("b", None, D("0.4")))
    r = analyse([qi("1", "10", "5", maps=maps)], {"a": "m1", "b": "m2"})
    assert (r.topics["a"].earned, r.topics["a"].possible) == (D(3), D(6))
    assert (r.topics["b"].earned, r.topics["b"].possible) == (D(2), D(4))
    assert sum(t.possible for t in r.topics.values()) == r.overall.possible == D(10)


def test_module_only_mapping_has_no_topic_result() -> None:
    r = analyse([qi("1", "10", "4", maps=(MappingInput(None, "m3", D(1)),))], {})
    assert r.topics == {}
    assert r.modules["m3"].possible == D(10) and r.modules["m3"].module_only == ["1"]


# --------------------------------------------------------------------------- #
# Curriculum modules
# --------------------------------------------------------------------------- #


def test_curriculum_subjects_have_modules(client: TestClient) -> None:
    ds = subject(client)
    assert [m["number"] for m in ds["modules"]] == [1, 2, 3, 4, 5]
    stacks = next(t for t in ds["topics"] if t["slug"] == "ds.stacks-queues")
    assert stacks["module_id"] == module_id(ds, 2)
    # A topic shared by two subjects sits in a different module of each.
    algo = subject(client, "algorithms")
    sorting_ds = next(t for t in ds["topics"] if t["slug"] == "ds.sorting-searching")
    sorting_algo = next(t for t in algo["topics"] if t["slug"] == "ds.sorting-searching")
    assert sorting_ds["module_id"] == module_id(ds, 5)
    assert sorting_algo["module_id"] == module_id(algo, 2)


# --------------------------------------------------------------------------- #
# Paper upload and review
# --------------------------------------------------------------------------- #


def test_digital_pdf_gives_editable_questions(client: TestClient) -> None:  # 1
    new_profile(client)
    b = create(client)
    r = upload_paper(client, b, "digital_ds_paper.pdf")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["questions_found"] == 8 and out["error"] is None and out["source"] == "pdf_text"
    detail = out["breakdown"]
    assert detail["declared_total"] == "34.00"
    assert detail["choice_rules"] == {"Part B": 2}
    qs = {x["label"]: x for x in detail["questions"]}
    assert qs["4(a)"]["max_marks"] == "6.00" and qs["4(a)"]["is_optional"]
    assert qs["1"]["marks_obtained"] is None and qs["1"]["attempt_status"] == "unknown"
    assert qs["1"]["page"] == 1 and qs["1"]["parse_confidence"] is not None
    # The paper is stored like other uploads, but no file path is ever returned.
    assert detail["paper"]["filename"] == "digital_ds_paper.pdf"
    assert "storage_key" not in r.text and "/uploads" not in r.text
    # Question papers do not appear in the marksheet document list.
    assert client.get("/api/documents").json() == []


def test_suggestions_come_from_the_curriculum_and_knowledge_base(client: TestClient) -> None:
    new_profile(client)
    b = create(client)
    detail = upload_paper(client, b, "digital_ds_paper.pdf").json()["breakdown"]
    ds = subject(client)
    qs = {x["label"]: x["suggestion"] for x in detail["questions"]}
    s4 = qs["4(a)"]  # a circular-array queue with enqueue and dequeue
    assert s4["status"] == "clear"
    assert s4["candidates"][0]["topic_id"] == topic_id(ds, "ds.stacks-queues")
    assert s4["candidates"][0]["module_id"] == module_id(ds, 2)
    assert {"queue", "enqueue", "dequeue"} <= set(s4["candidates"][0]["matched"])
    assert qs["4(b)"]["candidates"][0]["topic_id"] == topic_id(ds, "ds.stacks-queues")
    assert qs["5"]["status"] == "clear"
    assert qs["5"]["candidates"][0]["topic_id"] == topic_id(ds, "ds.trees-bst")
    assert qs["3"]["candidates"][0]["topic_id"] == topic_id(ds, "ds.hashing")
    # "Explain merge sort and analyse its time complexity" tests two topics: the
    # scores are close, so both are offered instead of one confident answer.
    s7 = qs["7"]
    assert s7["status"] == "ambiguous"
    assert {c["topic_id"] for c in s7["candidates"][:2]} == {
        topic_id(ds, "ds.sorting-searching"),
        topic_id(ds, "ds.complexity"),
    }
    # Nothing is mapped until the student confirms a mapping.
    assert all(x["mappings"] == [] for x in detail["questions"])


def test_weak_matches_are_left_unmapped(client: TestClient) -> None:
    new_profile(client)
    b = create(client)
    detail = put(client, b, [q("1", 5, text="Write your roll number on the cover.")]).json()
    assert detail["questions"][0]["suggestion"] == {
        "status": "none",
        "candidates": [],
        "paper_module_id": None,
    }


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract not installed")
def test_scanned_paper_goes_through_ocr(client: TestClient) -> None:  # 2
    new_profile(client)
    b = create(client)
    out = upload_paper(client, b, "scanned_ds_paper.png").json()
    assert out["source"] == "ocr" and out["questions_found"] == 8


def test_ocr_unavailable_still_allows_manual_entry(  # 2, 3
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_ocr(*_: Any, **__: Any) -> Any:
        raise OcrUnavailable("This file needs OCR, but Tesseract is not installed on the server.")

    monkeypatch.setattr("scholariq.exams.service.extract", no_ocr)
    new_profile(client)
    b = create(client)
    out = upload_paper(client, b, "scanned_ds_paper.png").json()
    assert out["questions_found"] == 0 and "Tesseract" in out["error"]
    assert out["breakdown"]["paper"]["status"] == "failed"
    r = put(client, b, [q("1", 10, 7), q("2", 5)])
    assert r.status_code == 200, r.text
    assert [x["label"] for x in r.json()["questions"]] == ["1", "2"]


def test_unreadable_and_disallowed_files(client: TestClient, tmp_path: Path) -> None:  # 3
    new_profile(client)
    b = create(client)
    fake = tmp_path / "paper.pdf"
    fake.write_bytes(b"MZ\x90\x00 not a pdf")
    assert upload_paper(client, b, str(fake)).status_code == 422
    sheet = tmp_path / "paper.csv"
    sheet.write_text("Q,Marks\n1,5\n", encoding="utf-8")
    r = upload_paper(client, b, str(sheet))
    assert r.status_code == 422 and "question paper" in r.json()["detail"]
    text = tmp_path / "notes.txt"
    text.write_text("Example Institute\nGeneral instructions\n", encoding="utf-8")
    out = upload_paper(client, b, str(text)).json()
    assert out["questions_found"] == 0
    assert any("by hand" in w for w in out["warnings"])


def test_replacing_questions_needs_confirmation(client: TestClient) -> None:
    new_profile(client)
    b = create(client)
    put(client, b, [q("1", 5)])
    assert upload_paper(client, b, "digital_ds_paper.pdf").status_code == 409
    r = upload_paper(client, b, "digital_ds_paper.pdf", replace="true")
    assert r.status_code == 200 and r.json()["questions_found"] == 8


def test_same_paper_reused_for_a_repeat_attempt(client: TestClient, engine: Engine) -> None:
    new_profile(client)
    first = create(client, title="Mid-term")
    second = create(client, title="Mid-term (repeat)")
    assert upload_paper(client, first, "digital_ds_paper.pdf").json()["questions_found"] == 8
    assert upload_paper(client, second, "digital_ds_paper.pdf").json()["questions_found"] == 8
    with Session(engine) as s:
        assert s.scalar(select(func.count(Document.id))) == 1
    client.delete(f"/api/exam-breakdowns/{first['id']}")
    with Session(engine) as s:  # still used by the second breakdown
        assert s.scalar(select(func.count(Document.id))) == 1
    client.delete(f"/api/exam-breakdowns/{second['id']}")
    with Session(engine) as s:
        assert s.scalar(select(func.count(Document.id))) == 0


def test_corrections_are_saved(client: TestClient) -> None:  # 4
    new_profile(client)
    ds = subject(client)
    b = create(client)
    detail = upload_paper(client, b, "digital_ds_paper.pdf").json()["breakdown"]
    edited = []
    for x in detail["questions"]:
        item = {k: x[k] for k in ("id", "label", "text", "max_marks", "is_optional")}
        item["choice_group"] = x["choice_group"]
        edited.append(item)
    edited[0]["label"] = "1(a)"
    edited[0]["max_marks"] = "3"
    edited[0]["mappings"] = topics(topic_id(ds, "ds.stacks-queues"))
    edited.pop(1)  # remove a duplicate/irrelevant entry
    edited.append({"label": "8", "text": "Added by hand", "max_marks": "4.5"})
    r = put(client, detail, edited)
    assert r.status_code == 200, r.text
    qs = {x["label"]: x for x in r.json()["questions"]}
    assert "2" not in qs and qs["8"]["max_marks"] == "4.50"
    assert qs["1(a)"]["max_marks"] == "3.00"
    assert qs["1(a)"]["mappings"] == [
        {"topic_id": topic_id(ds, "ds.stacks-queues"), "module_id": None, "share": "1.0000"}
    ]
    assert qs["1(a)"]["id"] == detail["questions"][0]["id"]  # edited in place


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (q("1", 5, "-1"), "greater than or equal to 0"),
        (q("1", 5, "5.5"), "exceed the maximum"),
        (q("1", 0), "greater than zero"),
        (q("1", None, 3), "maximum marks before"),
        (q("1", 5, 2, "not_attempted"), "cannot earn marks"),
    ],
)
def test_invalid_marks_are_rejected(  # 5
    client: TestClient, item: dict[str, Any], message: str
) -> None:
    new_profile(client)
    b = create(client)
    r = put(client, b, [item])
    assert r.status_code == 422
    assert message in r.text


def test_mapping_validation(client: TestClient) -> None:
    new_profile(client)
    ds = subject(client)
    os_ = subject(client, "operating-systems")
    b = create(client)
    stacks, trees = topic_id(ds, "ds.stacks-queues"), topic_id(ds, "ds.trees-bst")
    bad_share = q("1", 10, mappings=topics([(stacks, "0.5"), (trees, "0.3")]))
    assert "add up to 100%" in put(client, b, [bad_share]).text
    other_subject = q("1", 10, mappings=topics(topic_id(os_, "os.deadlocks")))
    r = put(client, b, [other_subject])
    assert r.status_code == 422 and "not part of Data Structures" in r.text
    both = q("1", 10, mappings=[{"topic_id": stacks, "module_id": module_id(ds, 2)}])
    assert put(client, b, [both]).status_code == 422
    dupe = put(client, b, [q("1", 2), q("1", 3)])
    assert dupe.status_code == 422 and "unique" in dupe.text
    # Shares may be left out: they are split equally.
    r = put(client, b, [q("1", 10, mappings=topics(stacks) + topics(trees))])
    shares = [m["share"] for m in r.json()["questions"][0]["mappings"]]
    assert shares == ["0.5000", "0.5000"]


def test_a_mark_implies_an_attempt_and_blank_stays_unknown(client: TestClient) -> None:  # 6, 7
    new_profile(client)
    b = create(client)
    r = put(client, b, [q("1", 5, 0), q("2", 5)])
    qs = {x["label"]: x for x in r.json()["questions"]}
    assert qs["1"]["marks_obtained"] == "0.00" and qs["1"]["attempt_status"] == "attempted"
    assert qs["2"]["marks_obtained"] is None and qs["2"]["attempt_status"] == "unknown"
    assert qs["1"]["counted"] and not qs["2"]["counted"]


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #


def scenario(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    """A paper with required, optional, split, module-only and unmapped questions."""
    new_profile(client)
    ds = subject(client)
    t = {s: topic_id(ds, s) for s in ("ds.stacks-queues", "ds.linked-lists", "ds.trees-bst",
                                      "ds.hashing", "ds.sorting-searching")}  # fmt: skip
    b = create(client, declared_total="30")
    questions = [
        q("1", 2, 2, mappings=topics(t["ds.stacks-queues"])),
        q("2", 2, 0, mappings=topics(t["ds.linked-lists"])),  # explicit zero
        q("3", 2, None, "not_attempted", mappings=topics(t["ds.hashing"])),  # required, skipped
        q("4(a)", 6, "4.5", is_optional=True, choice_group="Part B",
          mappings=topics([(t["ds.stacks-queues"], "0.5"), (t["ds.linked-lists"], "0.5")])),
        q("4(b)", 4, 1, is_optional=True, choice_group="Part B",
          mappings=topics(t["ds.stacks-queues"])),
        q("5", 10, 3, is_optional=True, choice_group="Part B",
          mappings=topics(t["ds.trees-bst"])),
        q("6", 10, None, "not_attempted", is_optional=True, choice_group="Part B",
          mappings=topics(t["ds.sorting-searching"])),  # optional, not chosen
        q("7", 8, None, "attempted", mappings=topics(t["ds.sorting-searching"])),  # mark missing
        q("8", 4, 2, mappings=[{"module_id": module_id(ds, 5)}]),  # module only
        q("9", 2, 1),  # unmapped
    ]  # fmt: skip
    r = put(client, b, questions, choice_rules={"Part B": 2})
    assert r.status_code == 200, r.text
    return r.json(), ds


def test_overall_breakdown(client: TestClient) -> None:  # 6, 7, 8, 9, 12
    b, _ = scenario(client)
    a = analysis(client, b)
    o = a["overall"]
    # Counted: 1, 2, 3, 4(a), 4(b), 5, 8, 9 -> earned 2+0+0+4.5+1+3+2+1, possible 2+2+2+6+4+10+4+2
    assert (o["earned"], o["possible"]) == ("13.50", "32.00")
    assert o["percentage"] == 42.2 and o["band"] == "needs_attention"
    assert o["counted"] == 8 and o["total_questions"] == 10 and not o["complete"]
    excluded = {e["reason"]: e["labels"] for e in o["excluded"]}
    assert excluded == {"optional_not_chosen": ["6"], "no_mark": ["7"]}
    assert o["unmapped"] == ["9"]
    # The optional question that was not chosen does not enlarge the denominator.
    assert "6" not in a["breakdown"] and o["possible"] != "42.00"


def test_module_and_topic_breakdown(client: TestClient) -> None:  # 10, 11, 12
    b, ds = scenario(client)
    a = analysis(client, b)
    modules = {m["number"]: m for m in a["modules"]}
    # Module 2 (linear structures): stacks Q1 2/2, Q4(a) half 2.25/3, Q4(b) 1/4;
    # linked lists Q2 0/2, Q4(a) half 2.25/3.
    m2 = modules[2]
    assert (m2["earned"], m2["possible"]) == ("7.50", "14.00")
    assert m2["questions"] == ["1", "2", "4(a)", "4(b)"]
    assert m2["marks_lost"] == "6.50" and m2["evidence"] == "complete"
    assert set(m2["topics"]) == {"Stacks and queues", "Linked lists"}
    # Module 5 (sorting, searching and hashing): hashing Q3 0/2 and the module-only
    # Q8 2/4; Q7 (sorting, mark missing) is left out, so the module is partial.
    m5 = modules[5]
    assert (m5["earned"], m5["possible"]) == ("2.00", "6.00")
    assert m5["module_only"] == ["8"] and m5["evidence"] == "partial" and m5["left_out"] == ["7"]
    assert a["focus_module_id"] == module_id(ds, 3)  # trees: 7 marks lost, the most
    by_name = {t["name"]: t for t in a["topics"]}
    stacks = by_name["Stacks and queues"]
    assert (stacks["earned"], stacks["possible"]) == ("5.25", "9.00")
    assert stacks["questions"] == ["1", "4(a)", "4(b)"]
    assert [x["label"] for x in stacks["lost_by"]] == ["4(b)", "4(a)"]
    assert stacks["module_name"] == "Linear data structures"
    hashing = by_name["Hashing"]  # required but not attempted: 0 of 2
    assert (hashing["earned"], hashing["possible"], hashing["band"]) == (
        "0.00", "2.00", "needs_attention",
    )  # fmt: skip
    # Topic totals never exceed the mapped part of the paper.
    mapped = sum(D(t["possible"]) for t in a["topics"])
    assert mapped == D("32") - D(4) - D(2)  # minus module-only Q8 and unmapped Q9
    assert "Sorting and searching" in by_name and by_name["Sorting and searching"]["partial"]


def test_reconciliation_and_total_warnings(client: TestClient) -> None:  # 17
    new_profile(client)
    doc = upload(client, "digital_semester3.pdf").json()
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assessment = client.get("/api/academics/assessments").json()[0]
    ds = subject(client)
    results_before = len(assessment["results"])
    b = create(client, assessment_id=assessment["id"], declared_total="100")
    assert b["recorded"] == {
        "assessment_label": b["recorded"]["assessment_label"],
        "marks_obtained": "78.00",
        "max_marks": "100.00",
    }
    put(client, b, [q("1", 60, 40, mappings=topics(topic_id(ds, "ds.trees-bst")))])
    a = analysis(client, b)
    assert any("recorded in your results" in w and "40 marks instead of 78" in w
               for w in a["warnings"])  # fmt: skip
    assert any("add up to 60" in w for w in a["warnings"])
    # The recorded result is unchanged and no second overall result is created.
    after = client.get("/api/academics/assessments").json()[0]
    assert len(after["results"]) == results_before
    ds_row = next(r for r in after["results"] if r["subject_name"] == "Data Structures")
    assert ds_row["marks_obtained"] == "78.00"
    # One breakdown per subject per recorded exam.
    dup = client.post(
        "/api/exam-breakdowns", json={"subject_id": ds["id"], "assessment_id": assessment["id"]}
    )
    assert dup.status_code == 409 and dup.json()["detail"]["breakdown_id"] == b["id"]


def test_choice_overflow_warning(client: TestClient) -> None:
    new_profile(client)
    b = create(client)
    qs = [q(str(i), 10, 5, is_optional=True, choice_group="Part B") for i in (1, 2, 3)]
    a = put(client, b, qs, choice_rules={"Part B": 2}).json()
    assert any("3 questions are marked attempted but only 2 count" in w for w in a["warnings"])


# --------------------------------------------------------------------------- #
# Evidence and classification
# --------------------------------------------------------------------------- #


def five_trees(ds: dict[str, Any], obtained: list[int]) -> list[dict[str, Any]]:
    trees = topic_id(ds, "ds.trees-bst")
    return [q(str(i + 1), 10, got, mappings=topics(trees)) for i, got in enumerate(obtained)]


def test_draft_has_no_evidence_and_confirm_creates_it(client: TestClient, engine: Engine) -> None:
    new_profile(client)
    ds = subject(client)
    b = create(client)
    put(client, b, five_trees(ds, [2, 3, 1, 4, 2]))
    assert evidence(engine, EvidenceKind.EXAM_BREAKDOWN) == []
    confirm(client, b)
    rows = evidence(engine, EvidenceKind.EXAM_BREAKDOWN)
    assert len(rows) == 1
    ev = rows[0]
    assert ev.exam_breakdown_id == b["id"] and ev.sample_size == 5
    assert ev.score == D("0.2400")
    assert ev.details["obtained"] == "12.00" and ev.details["maximum"] == "50.00"
    assert ev.details["questions"] == ["Q1", "Q2", "Q3", "Q4", "Q5"]


def test_classification_updates_through_the_existing_pipeline(client: TestClient) -> None:  # 13
    new_profile(client)
    ds = subject(client)
    b = create(client)
    # No results and no evidence yet: the topic is not listed at all.
    names = {t["name"] for t in client.get("/api/topics").json()}
    assert "Trees and binary search trees" not in names
    put(client, b, five_trees(ds, [2, 3, 1, 4, 2]))
    confirm(client, b)
    trees = topic_view(client, "Trees and binary search trees")
    assert trees["classification"] == "needs_attention"
    assert trees["direct_observations"] == 5
    ev = next(e for e in trees["evidence"] if e["kind"] == "exam_breakdown")
    assert ev["description"].startswith("Exam questions in Data Structures exam: 12 of 50 marks")
    assert not ev["removable"]
    # Editing the marks re-classifies the topic.
    put(client, b, five_trees(ds, [9, 8, 10, 9, 8]))
    assert topic_view(client, "Trees and binary search trees")["classification"] == "strong"


def test_insufficient_evidence_stays_insufficient(client: TestClient) -> None:  # 14
    new_profile(client)
    ds = subject(client)
    b = create(client)
    put(client, b, five_trees(ds, [0, 1]))  # two questions, both poor
    a = confirm(client, b)
    trees = next(t for t in a["topics"] if t["name"] == "Trees and binary search trees")
    # Exam performance is shown at once ...
    assert trees["percentage"] == 5.0 and trees["band"] == "needs_attention"
    # ... but topic mastery still needs more evidence.
    assert trees["classification"] == "insufficient_evidence"
    assert not trees["evidence_sufficient"] and trees["direct_observations"] == 2
    assert "not yet enough topic-level evidence" in trees["recommendation"]


def test_repeated_saves_do_not_duplicate_evidence(client: TestClient, engine: Engine) -> None:  # 15
    new_profile(client)
    ds = subject(client)
    b = create(client)
    questions = five_trees(ds, [2, 3, 1, 4, 2])
    questions.append(q("6", 10, 5, mappings=topics(topic_id(ds, "ds.hashing"))))
    put(client, b, questions)
    confirm(client, b)
    first = sorted((e.topic_id, e.score) for e in evidence(engine, EvidenceKind.EXAM_BREAKDOWN))
    for _ in range(3):
        detail = client.get(f"/api/exam-breakdowns/{b['id']}").json()
        saved = [
            {k: x[k] for k in ("id", "label", "text", "max_marks", "marks_obtained")}
            | {"mappings": [{"topic_id": m["topic_id"]} for m in x["mappings"]]}
            for x in detail["questions"]
        ]
        assert put(client, detail, saved).status_code == 200
        confirm(client, b)
    again = sorted((e.topic_id, e.score) for e in evidence(engine, EvidenceKind.EXAM_BREAKDOWN))
    assert again == first and len(again) == 2


def test_other_exams_keep_their_evidence(client: TestClient, engine: Engine) -> None:  # 16
    new_profile(client)
    ds = subject(client)
    mid = create(client, title="Mid-term")
    final = create(client, title="Final")
    put(client, mid, five_trees(ds, [2, 3, 1]))
    put(client, final, five_trees(ds, [4, 2]))
    confirm(client, mid)
    confirm(client, final)
    assert topic_view(client, "Trees and binary search trees")["direct_observations"] == 5
    # Editing one exam leaves the other's evidence untouched.
    put(client, mid, five_trees(ds, [5, 5, 5]))
    by_exam = {e.exam_breakdown_id: e for e in evidence(engine, EvidenceKind.EXAM_BREAKDOWN)}
    assert by_exam[final["id"]].score == D("0.3000")
    assert by_exam[mid["id"]].score == D("0.5000")
    # Deleting one exam removes only its evidence; the topic is re-classified.
    assert client.delete(f"/api/exam-breakdowns/{mid['id']}").status_code == 204
    rows = evidence(engine, EvidenceKind.EXAM_BREAKDOWN)
    assert [e.exam_breakdown_id for e in rows] == [final["id"]]
    trees = topic_view(client, "Trees and binary search trees")
    assert trees["direct_observations"] == 2 and trees["classification"] == "insufficient_evidence"
    with Session(engine) as s:
        assert s.scalar(select(func.count(ExamQuestion.id))) == 2
        assert s.scalar(select(func.count(ExamQuestionMapping.id))) == 2


def test_reopen_removes_evidence(client: TestClient, engine: Engine) -> None:
    new_profile(client)
    ds = subject(client)
    b = create(client)
    put(client, b, five_trees(ds, [2, 3, 1, 4, 2]))
    confirm(client, b)
    assert client.post(f"/api/exam-breakdowns/{b['id']}/reopen").json()["status"] == "draft"
    assert evidence(engine, EvidenceKind.EXAM_BREAKDOWN) == []


def test_nothing_to_confirm(client: TestClient) -> None:
    new_profile(client)
    b = create(client)
    put(client, b, [q("1", 10), q("2", None)])
    r = client.post(f"/api/exam-breakdowns/{b['id']}/confirm")
    assert r.status_code == 422 and "Nothing can be counted" in r.text


def test_subject_mark_is_not_counted_twice(client: TestClient, engine: Engine) -> None:  # 17
    new_profile(client)
    doc = upload(client, "digital_semester3.pdf").json()
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assessment = client.get("/api/academics/assessments").json()[0]
    ds = subject(client)
    trees, graphs = topic_id(ds, "ds.trees-bst"), topic_id(ds, "ds.graphs")

    def priors(tid: str) -> int:
        return sum(
            1 for e in evidence(engine, EvidenceKind.SUBJECT_SCORE_PRIOR) if e.topic_id == tid
        )

    assert priors(trees) == 1 and priors(graphs) == 1
    with Session(engine) as s:
        results_before = s.scalar(select(func.count(AssessmentResult.id)))
    b = create(client, assessment_id=assessment["id"])
    put(client, b, five_trees(ds, [7, 8]))
    confirm(client, b)
    # Trees now has question-level marks from that exam, so the same exam's subject
    # mark is not added to it again; Graphs (no questions) keeps its prior.
    assert priors(trees) == 0 and priors(graphs) == 1
    with Session(engine) as s:
        assert s.scalar(select(func.count(AssessmentResult.id))) == results_before
    # A breakdown of a different (unrecorded) exam does not remove the prior.
    client.delete(f"/api/exam-breakdowns/{b['id']}")
    assert priors(trees) == 1
    other = create(client, title="Class test")
    put(client, other, five_trees(ds, [7, 8]))
    confirm(client, other)
    assert priors(trees) == 1


def test_study_plan_uses_exam_results(client: TestClient) -> None:
    new_profile(client)
    ds = subject(client)
    b = create(client, held_on=None)
    put(client, b, five_trees(ds, [2, 3, 1, 4, 2]))
    confirm(client, b)
    plan = client.post("/api/study-plan", json={"goal_topics": []})
    assert plan.status_code == 201, plan.text
    item = next(
        i for i in plan.json()["items"] if i["topic_name"] == "Trees and binary search trees"
    )
    recent = item["breakdown"]["terms"]["recent_result"]
    assert recent["why"].startswith(
        "Latest exam questions (Data Structures exam): 24% of the marks"
    )
    assert recent["value"] == pytest.approx(0.76)
    assert plan.json()["items"][0]["topic_name"] == "Trees and binary search trees"


def test_summary_across_exams(client: TestClient) -> None:
    new_profile(client)
    ds = subject(client)
    hashing = topic_id(ds, "ds.hashing")
    for title, marks in (("Mid-term", [1, 2]), ("Final", [2, 1])):
        b = create(client, title=title)
        qs = five_trees(ds, marks) + [q("9", 10, 9, mappings=topics(hashing))]
        put(client, b, qs)
        confirm(client, b)
    s = client.get("/api/exam-breakdowns/summary").json()
    assert s["confirmed"] == 2 and s["drafts"] == 0
    assert s["modules"][0]["name"] == "Trees" and s["modules"][0]["marks_lost"] == "34.00"
    trees = s["topics"][0]
    assert trees["name"] == "Trees and binary search trees"
    assert trees["weak_in_exams"] == 2 and trees["repeated"] and trees["exams"] == 2
    h = next(t for t in s["topics"] if t["name"] == "Hashing")
    assert h["weak_in_exams"] == 0 and not h["repeated"] and h["percentage"] == 90.0


# --------------------------------------------------------------------------- #
# Ownership, deletion, custom subjects
# --------------------------------------------------------------------------- #


def test_other_students_cannot_reach_a_breakdown(  # 18
    client: TestClient, settings: Settings, engine: Engine
) -> None:
    from scholariq.core.config import get_settings
    from scholariq.db.session import get_engine
    from scholariq.main import create_app

    new_profile(client)
    b = create(client)
    put(client, b, [q("1", 5, 3)])
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as other:
        new_profile(other, "Ravi")
        base = f"/api/exam-breakdowns/{b['id']}"
        assert other.get(base).status_code == 404
        assert other.get(base + "/analysis").status_code == 404
        assert put(other, b, [q("1", 5, 5)]).status_code == 404
        assert other.post(base + "/confirm").status_code == 404
        assert upload_paper(other, b, "digital_ds_paper.pdf").status_code == 404
        assert other.delete(base).status_code == 404
        assert other.get("/api/exam-breakdowns").json() == []
        # Nor link a breakdown to someone else's recorded exam.
    assert client.get(base).json()["questions"][0]["marks_obtained"] == "3.00"


def test_linking_to_another_students_exam_is_refused(
    client: TestClient, settings: Settings, engine: Engine
) -> None:
    from scholariq.core.config import get_settings
    from scholariq.db.session import get_engine
    from scholariq.main import create_app

    new_profile(client)
    doc = upload(client, "digital_semester3.pdf").json()
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": confirmed_rows(doc)})
    assessment = client.get("/api/academics/assessments").json()[0]
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as other:
        new_profile(other, "Ravi")
        r = other.post(
            "/api/exam-breakdowns",
            json={"subject_id": subject(other)["id"], "assessment_id": assessment["id"]},
        )
        assert r.status_code == 422


def test_deleting_the_profile_removes_breakdowns(client: TestClient, engine: Engine) -> None:
    new_profile(client)
    ds = subject(client)
    b = create(client)
    upload_paper(client, b, "digital_ds_paper.pdf")
    put(client, b, five_trees(ds, [2, 3, 1, 4, 2]))
    confirm(client, b)
    assert client.delete("/api/profile").status_code == 204
    with Session(engine) as s:
        assert s.scalar(select(func.count(ExamQuestion.id))) == 0
        assert s.scalar(select(func.count(Document.id))) == 0
        assert s.scalar(select(func.count(TopicEvidence.id))) == 0


def test_custom_subject_modules(client: TestClient) -> None:
    new_profile(client)
    # A custom subject comes from an import whose subject matched no curriculum.
    doc = upload(client, "digital_semester3.pdf").json()
    rows = confirmed_rows(doc)
    rows[0] = {**rows[0], "subject_name": "Compiler Design", "subject_code": "CS399"}
    client.post(f"/api/documents/{doc['id']}/confirm", json={"results": rows})
    custom = next(s for s in client.get("/api/curriculum/subjects").json() if s["is_custom"])
    ds = subject(client)
    t1, t2 = topic_id(ds, "ds.trees-bst"), topic_id(ds, "ds.graphs")
    client.put(f"/api/curriculum/subjects/{custom['id']}/topics", json={"topic_ids": [t1, t2]})
    r = client.put(
        f"/api/curriculum/subjects/{custom['id']}/modules",
        json={"modules": [{"number": 1, "name": "Parsing", "topic_ids": [t1]},
                          {"number": 2, "name": "Code generation", "topic_ids": [t2]}]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["name"] for m in body["modules"]] == ["Parsing", "Code generation"]
    assert {t["id"]: t["module_id"] for t in body["topics"]} == {
        t1: body["modules"][0]["id"],
        t2: body["modules"][1]["id"],
    }
    # Renumbering keeps module ids; topic edits keep module assignments.
    m1, m2 = body["modules"]
    r = client.put(
        f"/api/curriculum/subjects/{custom['id']}/modules",
        json={"modules": [{"id": m1["id"], "number": 2, "name": "Parsing", "topic_ids": [t1]},
                          {"id": m2["id"], "number": 1, "name": "Codegen", "topic_ids": [t2]}]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert {m["id"] for m in r.json()["modules"]} == {m1["id"], m2["id"]}
    r = client.put(f"/api/curriculum/subjects/{custom['id']}/topics", json={"topic_ids": [t1, t2]})
    assert {t["module_id"] for t in r.json()["topics"]} == {m1["id"], m2["id"]}
    # A breakdown of the custom subject can map a question to a module only.
    b = create(client, subject_id=custom["id"])
    r = put(client, b, [q("1", 10, 6, mappings=[{"module_id": m2["id"]}])])
    assert r.status_code == 200, r.text
    a = analysis(client, b)
    assert a["modules"][0]["name"] == "Codegen" and a["topics"] == []
    # Curriculum subjects' modules come from the files.
    r = client.put(f"/api/curriculum/subjects/{ds['id']}/modules", json={"modules": []})
    assert r.status_code == 409


def test_marksheet_flow_refuses_a_question_paper(client: TestClient, engine: Engine) -> None:
    new_profile(client)
    b = create(client)
    upload_paper(client, b, "digital_ds_paper.pdf")
    with Session(engine) as s:
        doc_id = s.scalar(select(Document.id))
    r = client.post(f"/api/documents/{doc_id}/confirm", json={"results": []})
    assert r.status_code in (409, 422)
