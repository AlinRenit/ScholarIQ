"""Knowledge-base content, validation, review, sync and search."""

from __future__ import annotations

import math
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from scholariq.curriculum.sync import load_files, sync_curricula
from scholariq.db.models import Concept, ConceptRelationship, KnowledgeDocument, Question
from scholariq.domain.enums import TrustStatus
from scholariq.knowledge.evaluate import load_cases, report, run, summarise
from scholariq.knowledge.index import build_index, get_index
from scholariq.knowledge.loader import ContentError, KnowledgeContent, load_content, trust_of
from scholariq.knowledge.sync import sync_knowledge
from scholariq.retrieval.bm25 import BM25Index
from scholariq.retrieval.text import analyse, query_terms, stem
from tests.conftest import REPO_ROOT

REPO_CONTENT = Path(__file__).resolve().parents[2] / "content"

# --------------------------------------------------------------------------- #
# Seed content
# --------------------------------------------------------------------------- #


def test_seed_content_covers_every_curriculum_topic(knowledge_content: KnowledgeContent) -> None:
    topics = {t.slug for cf in load_files(REPO_CONTENT) for s in cf.subjects for t in s.topics}
    covered = {t.file.topic for t in knowledge_content.topics}
    assert covered == topics
    assert knowledge_content.warnings == []


def test_every_topic_has_enough_quiz_questions(knowledge_content: KnowledgeContent) -> None:
    # Five topic-level observations are needed to classify a topic (M3 rules),
    # so a diagnostic must be able to ask at least five questions per topic.
    per_topic = Counter[str]()
    for t, c in knowledge_content.concepts():
        per_topic[t.file.topic] += len(c.questions)
    assert min(per_topic.values()) >= 5


def test_every_concept_has_an_explanation_or_example(knowledge_content: KnowledgeContent) -> None:
    bare = [c.slug for _, c in knowledge_content.concepts() if not c.documents]
    assert bare == []


def test_seed_content_is_honestly_unreviewed(knowledge_content: KnowledgeContent) -> None:
    # No person has reviewed the seed entries yet; none may claim otherwise.
    assert {trust_of(c) for _, c in knowledge_content.concepts()} == {TrustStatus.IMPORTED}


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

CURRICULUM = {
    "curriculum": {"slug": "mini", "name": "Mini", "version": "1"},
    "subjects": [
        {
            "slug": "data-structures",
            "name": "Data Structures",
            "topics": [{"slug": "ds.stacks-queues", "name": "Stacks and queues"}],
        }
    ],
}


def mcq(slug: str, **over: Any) -> dict[str, Any]:
    q = {
        "slug": slug,
        "kind": "multiple_choice",
        "prompt": "Which order does a stack follow?",
        "options": ["FIFO", "LIFO"],
        "answer": {"option_index": 1},
        "explanation": "Last in, first out.",
    }
    return q | over


def concept(slug: str, name: str, **over: Any) -> dict[str, Any]:
    c = {
        "slug": slug,
        "name": name,
        "definition": f"{name} is a collection.",
        "documents": [{"kind": "explanation", "title": f"About {name}", "body": "Text."}],
        "questions": [mcq(f"q.{slug}")],
    }
    return c | over


def write_content(root: Path, concepts: list[dict[str, Any]]) -> Path:
    (root / "curriculum").mkdir(parents=True, exist_ok=True)
    (root / "curriculum" / "mini.yaml").write_text(yaml.safe_dump(CURRICULUM))
    (root / "sources.yaml").write_text(
        yaml.safe_dump({"sources": [{"slug": "book", "title": "A book"}]})
    )
    folder = root / "knowledge" / "data-structures"
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"topic": "ds.stacks-queues", "version": "1", "concepts": concepts}
    (folder / "ds.stacks-queues.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True))
    return root


def problems(root: Path) -> str:
    with pytest.raises(ContentError) as exc:
        load_content(root)
    return "\n".join(exc.value.problems)


def test_valid_minimal_content_loads(tmp_path: Path) -> None:
    content = load_content(write_content(tmp_path, [concept("ds.stack", "Stack")]))
    assert [c.slug for _, c in content.concepts()] == ["ds.stack"]


def test_unknown_references_are_reported(tmp_path: Path) -> None:
    c = concept("ds.stack", "Stack", requires=["ds.nothing"], further_reading=["nobook"])
    text = problems(write_content(tmp_path, [c]))
    assert "requires unknown concept ds.nothing" in text
    assert "cites unknown source nobook" in text


def test_prerequisite_cycles_are_rejected(tmp_path: Path) -> None:
    a = concept("ds.a", "A", requires=["ds.b"])
    b = concept("ds.b", "B", requires=["ds.a"])
    assert "prerequisite cycle" in problems(write_content(tmp_path, [a, b]))


def test_duplicate_slugs_are_rejected(tmp_path: Path) -> None:
    text = problems(write_content(tmp_path, [concept("ds.a", "A"), concept("ds.a", "A2")]))
    assert "duplicate concept slug ds.a" in text


@pytest.mark.parametrize(
    ("question", "message"),
    [
        (mcq("q.x", answer={"option_index": 5}), "option_index out of range"),
        # A YAML flow list split at commas typically yields too many options.
        (mcq("q.x", options=[str(i) for i in range(8)]), "2 to 6 options"),
        (mcq("q.x", options=["A", "A"]), "duplicate options"),
        (mcq("q.x", kind="numeric", options=[], answer={"accepted": ["1"]}), "value: x"),
        (mcq("q.x", kind="short_answer", options=[], answer={}), "accepted"),
    ],
)
def test_question_answer_shapes_are_checked(
    tmp_path: Path, question: dict[str, Any], message: str
) -> None:
    c = concept("ds.stack", "Stack", questions=[question])
    assert message in problems(write_content(tmp_path, [c]))


def test_topic_must_belong_to_the_folder_subject(tmp_path: Path) -> None:
    root = write_content(tmp_path, [concept("ds.stack", "Stack")])
    wrong = root / "knowledge" / "algorithms"
    wrong.mkdir()
    shutil.move(root / "knowledge" / "data-structures" / "ds.stacks-queues.yaml", wrong)
    assert "does not belong to 'algorithms'" in problems(root)


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #


def test_review_counts_only_for_the_exact_reviewed_content(tmp_path: Path) -> None:
    root = write_content(tmp_path, [concept("ds.stack", "Stack")])
    spec = load_content(root).concepts()[0][1]
    review = {
        "status": "verified",
        "by": "R. Reviewer",
        "on": "2026-10-22",
        "hash": spec.content_hash()[:12],
    }

    content = load_content(write_content(tmp_path, [concept("ds.stack", "Stack", review=review)]))
    assert trust_of(content.concepts()[0][1]) is TrustStatus.VERIFIED
    assert content.warnings == []

    edited = concept("ds.stack", "Stack", definition="Changed after review.", review=review)
    content = load_content(write_content(tmp_path, [edited]))
    assert trust_of(content.concepts()[0][1]) is TrustStatus.IMPORTED
    assert "changed after review by R. Reviewer" in content.warnings[0]


def test_verified_review_needs_reviewer_date_and_hash(tmp_path: Path) -> None:
    c = concept("ds.stack", "Stack", review={"status": "verified", "by": "Someone"})
    assert "a verified review needs by, on and hash" in problems(write_content(tmp_path, [c]))


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #


def count(session: Session, model: type[Any], **where: Any) -> int:
    stmt = select(func.count()).select_from(model)
    for k, v in where.items():
        stmt = stmt.where(getattr(model, k) == v)
    return session.scalar(stmt) or 0


def test_sync_is_idempotent_and_retires_removed_entries(tmp_path: Path, engine: Engine) -> None:
    stack = concept("ds.stack", "Stack", contrasts=["ds.queue"])
    queue = concept("ds.queue", "Queue")
    root = write_content(tmp_path / "c", [stack, queue])
    with Session(engine) as session:
        sync_curricula(session, load_files(root))
        first = sync_knowledge(session, load_content(root))
        second = sync_knowledge(session, load_content(root))
        assert (first.concepts, first.documents, first.questions, first.edges) == (2, 2, 2, 1)
        assert second.retired == 0
        assert count(session, Concept) == 2 and count(session, ConceptRelationship) == 1

        write_content(tmp_path / "c", [concept("ds.stack", "Stack")])
        report = sync_knowledge(session, load_content(root))
        # The queue concept, its document and its question are retired, not deleted.
        assert report.retired == 3
        assert count(session, Concept, trust_status=TrustStatus.RETIRED) == 1
        assert count(session, KnowledgeDocument, trust_status=TrustStatus.RETIRED) == 1
        assert count(session, Question, trust_status=TrustStatus.RETIRED) == 1
        assert count(session, ConceptRelationship) == 0


# --------------------------------------------------------------------------- #
# Text analysis and BM25
# --------------------------------------------------------------------------- #


def test_spelling_variants_and_inflections_meet() -> None:
    assert stem("normalisation") == stem("normalization")
    assert stem("normalised") == stem("normalized")
    assert stem("queues") == stem("queue")
    assert analyse("C++ and C# programs") == ["c++", "c#", "program"]


def test_query_words_about_answer_style_are_ignored() -> None:
    assert [
        w for _, w in query_terms("Please explain the difference between a stack and a queue")
    ] == [
        "stack",
        "queue",
    ]


def test_bm25_scores_are_explained_term_by_term() -> None:
    index = BM25Index(
        [
            ("a", [("stack push pop", 1.0)]),
            ("b", [("queue enqueue dequeue", 1.0)]),
            ("c", [("stack queue deque", 1.0)]),
        ]
    )
    hits = index.search(["stack", "pop"])
    assert [h.doc_id for h in hits] == ["a", "c"]
    for h in hits:
        assert math.isclose(h.score, sum(h.contributions.values()))
    # "pop" occurs in one document, "stack" in two, so "pop" carries more weight.
    assert hits[0].contributions["pop"] > hits[0].contributions["stack"]


def test_field_weights_raise_name_matches() -> None:
    index = BM25Index(
        [("named", [("heap", 3.0), ("filler text", 1.0)]), ("mention", [("heap filler text", 1.0)])]
    )
    assert index.search(["heap"])[0].doc_id == "named"


# --------------------------------------------------------------------------- #
# Concept search over the seed knowledge base
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("knowledge")
def test_search_finds_the_concept_a_question_names(engine: Engine) -> None:
    with Session(engine) as session:
        index = build_index(session, allow_unreviewed=True)
    top = index.search("what is the worst case of quick sort", 3)[0]
    assert top.concept.slug == "ds.quicksort"
    assert top.name_match == "quick sort"  # joined into "quicksort" and matched by alias
    assert index.search("binary search complexity", 1)[0].concept.slug == "ds.binary-search"
    assert index.search("photosynthesis", 5) == []
    assert index.unmatched_terms("photosynthesis in stacks") == ["photosynthesis"]


@pytest.mark.usefixtures("knowledge")
def test_unreviewed_content_is_excluded_when_not_allowed(engine: Engine) -> None:
    with Session(engine) as session:
        assert get_index(session, allow_unreviewed=False).search("stack") == []
        assert get_index(session, allow_unreviewed=True).search("stack")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("knowledge")
def test_knowledge_overview(client: TestClient) -> None:
    body = client.get("/api/knowledge/overview").json()
    assert body["concepts"] >= 150 and body["verified_concepts"] == 0
    assert body["allow_unreviewed"] is True
    topics = [t for s in body["subjects"] for t in s["topics"]]
    assert all(t["questions"] >= 5 for t in topics)


@pytest.mark.usefixtures("knowledge")
def test_search_api_explains_its_ranking(client: TestClient) -> None:
    body = client.get("/api/knowledge/search", params={"q": "What is 3NF?"}).json()
    first = body["results"][0]
    assert first["slug"] == "db.3nf"
    assert first["name_match"] == "3NF" and first["name_bonus"] > 0
    assert "3nf" in first["matched_terms"]
    assert "BM25" in body["method"]
    assert client.get("/api/knowledge/search", params={"q": ""}).status_code == 422


@pytest.mark.usefixtures("knowledge")
def test_concept_page_hides_quiz_answers(client: TestClient) -> None:
    r = client.get("/api/knowledge/concepts/ds.stack")
    assert r.status_code == 200
    body = r.json()
    assert body["trust_status"] == "imported" and body["reviewed_by"] is None
    assert body["question_count"] >= 1
    assert {
        "kind": "contrasts_with",
        "direction": "out",
        "slug": "ds.queue",
        "name": "Queue",
    } in body["relations"]
    assert body["further_reading"][0]["title"].startswith("Introduction to Algorithms")
    assert "_origin" not in body["attributes"] and body["origin"].endswith("ds.stacks-queues.yaml")
    raw = r.text
    assert "option_index" not in raw and "explanation" not in raw.replace(
        '"kind":"explanation"', ""
    )
    assert client.get("/api/knowledge/concepts/nope").status_code == 404


@pytest.mark.usefixtures("knowledge")
def test_topic_concepts_listing(client: TestClient) -> None:
    body = client.get("/api/knowledge/topics/ds.stacks-queues").json()
    assert {c["slug"] for c in body["concepts"]} >= {"ds.stack", "ds.queue"}
    assert client.get("/api/knowledge/topics/nope").status_code == 404


def test_retrieval_evaluation_set(knowledge: None, engine: Engine) -> None:

    cases = load_cases(REPO_ROOT / "content" / "eval" / "retrieval.yaml")
    with Session(engine) as session:
        index = build_index(session, allow_unreviewed=True)
    results = run(index, cases)  # raises if a case names an unknown concept
    in_scope = summarise([r for r in results if r.case.kind != "out_of_scope"])
    # A floor, not a target: catches search changes that quietly make ranking worse.
    assert in_scope.hit1 >= 0.85
    assert in_scope.hit3 >= 0.9
    assert "## Misses" in report(results)
