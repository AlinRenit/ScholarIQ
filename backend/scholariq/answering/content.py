"""Read a concept and everything attached to it, in a fixed order."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from scholariq.answering.model import ConceptRef, Reading
from scholariq.db.models import (
    Concept,
    ConceptRelationship,
    KnowledgeDocument,
    Question,
    SourceReference,
    Topic,
)
from scholariq.domain.enums import KnowledgeDocumentKind, RelationshipKind, TrustStatus


@dataclass
class ConceptBundle:
    concept: Concept
    topic: Topic
    ref: ConceptRef
    documents: list[KnowledgeDocument]
    questions: list[Question]
    requires: list[ConceptRef] = field(default_factory=list)
    required_by: list[ConceptRef] = field(default_factory=list)
    related: list[ConceptRef] = field(default_factory=list)
    contrasts: list[ConceptRef] = field(default_factory=list)
    part_of: list[ConceptRef] = field(default_factory=list)
    includes: list[ConceptRef] = field(default_factory=list)
    reading: list[Reading] = field(default_factory=list)

    @property
    def attributes(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.concept.attributes.items() if not k.startswith("_")}

    def docs(self, *kinds: KnowledgeDocumentKind) -> list[KnowledgeDocument]:
        return [d for d in self.documents if d.kind in kinds]


def ref_of(concept: Concept, topic: Topic) -> ConceptRef:
    return ConceptRef(
        slug=concept.slug,
        name=concept.canonical_name,
        topic_slug=topic.slug,
        topic_name=topic.name,
        trust=concept.trust_status,
    )


def load_bundle(
    session: Session, slug: str, allowed: tuple[TrustStatus, ...]
) -> ConceptBundle | None:
    c = session.scalar(select(Concept).where(Concept.slug == slug))
    if c is None or c.trust_status not in allowed:
        return None
    topic = session.get(Topic, c.topic_id)
    assert topic is not None
    docs = session.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.concept_id == c.id, KnowledgeDocument.trust_status.in_(allowed))
        .order_by(KnowledgeDocument.depth, KnowledgeDocument.kind, KnowledgeDocument.title)
    ).all()
    questions = session.scalars(
        select(Question)
        .where(Question.concept_id == c.id, Question.trust_status.in_(allowed))
        .order_by(Question.difficulty, Question.slug)
    ).all()
    bundle = ConceptBundle(c, topic, ref_of(c, topic), list(docs), list(questions))

    edges = session.execute(
        select(ConceptRelationship, Concept, Topic)
        .join(Concept, ConceptRelationship.target_concept_id == Concept.id)
        .join(Topic, Concept.topic_id == Topic.id)
        .where(ConceptRelationship.source_concept_id == c.id, Concept.trust_status.in_(allowed))
    ).tuples()
    back = session.execute(
        select(ConceptRelationship, Concept, Topic)
        .join(Concept, ConceptRelationship.source_concept_id == Concept.id)
        .join(Topic, Concept.topic_id == Topic.id)
        .where(ConceptRelationship.target_concept_id == c.id, Concept.trust_status.in_(allowed))
    ).tuples()
    out_lists = {
        RelationshipKind.REQUIRES: bundle.requires,
        RelationshipKind.RELATED_TO: bundle.related,
        RelationshipKind.CONTRASTS_WITH: bundle.contrasts,
        RelationshipKind.PART_OF: bundle.part_of,
    }
    in_lists = {
        RelationshipKind.REQUIRES: bundle.required_by,
        RelationshipKind.RELATED_TO: bundle.related,
        RelationshipKind.CONTRASTS_WITH: bundle.contrasts,
        RelationshipKind.PART_OF: bundle.includes,
    }
    for lists, rows in ((out_lists, edges), (in_lists, back)):
        for edge, other, other_topic in rows:
            target = lists[edge.kind]
            if all(r.slug != other.slug for r in target):
                target.append(ref_of(other, other_topic))
    for lst in (*out_lists.values(), *in_lists.values()):
        lst.sort(key=lambda r: r.name)

    slugs = list(c.attributes.get("_further_reading", []))
    rows_by_slug = {
        s.slug: s
        for s in session.scalars(select(SourceReference).where(SourceReference.slug.in_(slugs)))
    }
    bundle.reading = [
        Reading(title=s.title, authors=s.authors, citation=s.citation, url=s.url)
        for slug in slugs
        if (s := rows_by_slug.get(slug))
    ]
    return bundle


def topic_concepts(
    session: Session, topic_slug: str, allowed: tuple[TrustStatus, ...]
) -> tuple[Topic, list[Concept]] | None:
    topic = session.scalar(select(Topic).where(Topic.slug == topic_slug))
    if topic is None:
        return None
    concepts = session.scalars(
        select(Concept)
        .where(Concept.topic_id == topic.id, Concept.trust_status.in_(allowed))
        .order_by(Concept.difficulty, Concept.canonical_name)
    ).all()
    return topic, list(concepts)
