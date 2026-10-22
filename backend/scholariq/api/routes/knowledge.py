"""Knowledge base: coverage, concept pages and transparent search.

The knowledge base is shared course content, not personal data, so these
routes do not need a profile. Quiz answers are never returned here.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from scholariq.api.deps import SessionDep, SettingsDep
from scholariq.db.models import (
    Concept,
    ConceptRelationship,
    KnowledgeDocument,
    Question,
    SourceReference,
    Subject,
    SubjectTopic,
    Topic,
)
from scholariq.domain.enums import (
    KnowledgeDocumentKind,
    RelationshipKind,
    TrustStatus,
)
from scholariq.knowledge.index import NAME_BONUS, get_index

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

LIVE = (TrustStatus.VERIFIED, TrustStatus.IMPORTED)


class TopicCoverage(BaseModel):
    id: str
    slug: str
    name: str
    concepts: int
    verified_concepts: int
    documents: int
    questions: int


class SubjectCoverage(BaseModel):
    id: str
    name: str
    topics: list[TopicCoverage]


class Overview(BaseModel):
    concepts: int
    verified_concepts: int
    documents: int
    questions: int
    allow_unreviewed: bool
    subjects: list[SubjectCoverage]


@router.get("/overview", response_model=Overview)
def overview(session: SessionDep, settings: SettingsDep) -> Overview:
    def per_topic(model: type[Concept] | type[Question], verified: bool = False) -> dict[str, int]:
        allowed = (TrustStatus.VERIFIED,) if verified else LIVE
        rows = session.execute(
            select(model.topic_id, func.count(model.id))
            .where(model.trust_status.in_(allowed))
            .group_by(model.topic_id)
        ).all()
        return {t: n for t, n in rows}

    concepts, verified, questions = (
        per_topic(Concept),
        per_topic(Concept, True),
        per_topic(Question),
    )
    docs = dict(
        session.execute(
            select(Concept.topic_id, func.count(KnowledgeDocument.id))
            .join(Concept, KnowledgeDocument.concept_id == Concept.id)
            .where(KnowledgeDocument.trust_status.in_(LIVE))
            .group_by(Concept.topic_id)
        )
        .tuples()
        .all()
    )
    subjects: list[SubjectCoverage] = []
    rows = session.execute(
        select(Subject, Topic)
        .join(SubjectTopic, SubjectTopic.subject_id == Subject.id)
        .join(Topic, SubjectTopic.topic_id == Topic.id)
        .where(Subject.is_custom.is_(False))
        .order_by(Subject.name, SubjectTopic.position)
    ).all()
    by_subject: dict[str, SubjectCoverage] = {}
    for subject, topic in rows:
        entry = by_subject.get(subject.id)
        if entry is None:
            entry = by_subject[subject.id] = SubjectCoverage(
                id=subject.id, name=subject.name, topics=[]
            )
            subjects.append(entry)
        entry.topics.append(
            TopicCoverage(
                id=topic.id,
                slug=topic.slug,
                name=topic.name,
                concepts=concepts.get(topic.id, 0),
                verified_concepts=verified.get(topic.id, 0),
                documents=docs.get(topic.id, 0),
                questions=questions.get(topic.id, 0),
            )
        )
    return Overview(
        concepts=sum(concepts.values()),
        verified_concepts=sum(verified.values()),
        documents=sum(docs.values()),
        questions=sum(questions.values()),
        allow_unreviewed=settings.allow_unreviewed_content,
        subjects=subjects,
    )


class ConceptSummary(BaseModel):
    slug: str
    name: str
    trust_status: TrustStatus


class TopicConcepts(BaseModel):
    slug: str
    name: str
    concepts: list[ConceptSummary]


@router.get("/topics/{slug}", response_model=TopicConcepts)
def topic_concepts(slug: str, session: SessionDep) -> TopicConcepts:
    topic = session.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topic not found.")
    concepts = session.scalars(
        select(Concept)
        .where(Concept.topic_id == topic.id, Concept.trust_status.in_(LIVE))
        .order_by(Concept.difficulty, Concept.canonical_name)
    ).all()
    return TopicConcepts(
        slug=topic.slug,
        name=topic.name,
        concepts=[
            ConceptSummary(slug=c.slug, name=c.canonical_name, trust_status=c.trust_status)
            for c in concepts
        ],
    )


class SearchMatch(BaseModel):
    slug: str
    name: str
    topic_slug: str
    topic_name: str
    trust_status: TrustStatus
    score: float
    matched_terms: dict[str, float]
    name_match: str | None
    name_bonus: float


class SearchResult(BaseModel):
    query: str
    method: str
    unmatched_terms: list[str]
    allow_unreviewed: bool
    results: list[SearchMatch]


@router.get("/search", response_model=SearchResult)
def search(
    session: SessionDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> SearchResult:
    index = get_index(session, settings.allow_unreviewed_content)
    hits = index.search(q, limit)
    return SearchResult(
        query=q,
        method=(
            "BM25 (k1 1.2, b 0.75) over concept names, definitions and explanations, "
            f"plus {NAME_BONUS:g} points per word when the question names the concept."
        ),
        unmatched_terms=index.unmatched_terms(q),
        allow_unreviewed=settings.allow_unreviewed_content,
        results=[
            SearchMatch(
                slug=h.concept.slug,
                name=h.concept.name,
                topic_slug=h.concept.topic_slug,
                topic_name=h.concept.topic_name,
                trust_status=h.concept.trust,
                score=h.score,
                matched_terms=h.matched,
                name_match=h.name_match,
                name_bonus=h.name_bonus,
            )
            for h in hits
        ],
    )


class DocumentOut(BaseModel):
    kind: KnowledgeDocumentKind
    title: str
    body: str
    steps: list[str]
    depth: int


class RelationOut(BaseModel):
    kind: RelationshipKind
    direction: str  # "out": this concept -> other; "in": other -> this concept
    slug: str
    name: str


class SourceOut(BaseModel):
    title: str
    authors: str | None
    citation: str | None
    url: str | None


class ConceptOut(BaseModel):
    slug: str
    name: str
    aliases: list[str]
    definition: str
    attributes: dict[str, str]
    difficulty: int
    topic_slug: str
    topic_name: str
    trust_status: TrustStatus
    reviewed_by: str | None
    reviewed_on: date | None
    content_version: str
    origin: str | None
    documents: list[DocumentOut]
    relations: list[RelationOut]
    further_reading: list[SourceOut]
    question_count: int


@router.get("/concepts/{slug}", response_model=ConceptOut)
def concept_detail(slug: str, session: SessionDep) -> ConceptOut:
    c = session.scalar(select(Concept).where(Concept.slug == slug))
    if c is None or c.trust_status is TrustStatus.RETIRED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Concept not found.")
    topic = session.get(Topic, c.topic_id)
    assert topic is not None
    docs = session.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.concept_id == c.id, KnowledgeDocument.trust_status.in_(LIVE))
        .order_by(KnowledgeDocument.depth, KnowledgeDocument.kind, KnowledgeDocument.title)
    ).all()
    relations: list[RelationOut] = []
    for edge, other, direction in [
        *(
            (e, o, "out")
            for e, o in session.execute(
                select(ConceptRelationship, Concept)
                .join(Concept, ConceptRelationship.target_concept_id == Concept.id)
                .where(ConceptRelationship.source_concept_id == c.id)
            ).tuples()
        ),
        *(
            (e, o, "in")
            for e, o in session.execute(
                select(ConceptRelationship, Concept)
                .join(Concept, ConceptRelationship.source_concept_id == Concept.id)
                .where(ConceptRelationship.target_concept_id == c.id)
            ).tuples()
        ),
    ]:
        if other.trust_status in LIVE:
            relations.append(
                RelationOut(
                    kind=edge.kind, direction=direction, slug=other.slug, name=other.canonical_name
                )
            )
    reading_slugs = list(c.attributes.get("_further_reading", []))
    sources = {
        s.slug: s
        for s in session.scalars(
            select(SourceReference).where(SourceReference.slug.in_(reading_slugs))
        ).all()
    }
    questions = session.scalar(
        select(func.count(Question.id)).where(
            Question.concept_id == c.id, Question.trust_status.in_(LIVE)
        )
    )
    return ConceptOut(
        slug=c.slug,
        name=c.canonical_name,
        aliases=c.aliases,
        definition=c.definition,
        attributes={k: str(v) for k, v in c.attributes.items() if not k.startswith("_")},
        difficulty=c.difficulty,
        topic_slug=topic.slug,
        topic_name=topic.name,
        trust_status=c.trust_status,
        reviewed_by=c.reviewed_by,
        reviewed_on=c.reviewed_on,
        content_version=c.content_version,
        origin=c.attributes.get("_origin"),
        documents=[
            DocumentOut(kind=d.kind, title=d.title, body=d.body, steps=d.steps, depth=d.depth)
            for d in docs
        ],
        relations=sorted(relations, key=lambda r: (r.kind.value, r.direction, r.name)),
        further_reading=[
            SourceOut(title=s.title, authors=s.authors, citation=s.citation, url=s.url)
            for slug in reading_slugs
            if (s := sources.get(slug))
        ],
        question_count=questions or 0,
    )
