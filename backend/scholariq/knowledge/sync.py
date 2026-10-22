"""Load validated knowledge-base files into the database (idempotent).

Run:  python -m scholariq.knowledge.sync   (also run by scholariq.curriculum.sync)

Rows are upserted by slug. Entries removed from the files are marked retired
rather than deleted, because quiz attempts and chat messages may reference
them.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from scholariq.db.models import (
    Concept,
    ConceptRelationship,
    KnowledgeDocument,
    Question,
    SourceReference,
    Topic,
    VerifiedAnswer,
)
from scholariq.domain.enums import RelationshipKind, TrustStatus
from scholariq.knowledge.loader import KnowledgeContent, trust_of

logger = logging.getLogger(__name__)

EDGE_KINDS = {
    "requires": RelationshipKind.REQUIRES,
    "related": RelationshipKind.RELATED_TO,
    "contrasts": RelationshipKind.CONTRASTS_WITH,
    "part_of": RelationshipKind.PART_OF,
}


@dataclass
class KnowledgeSyncReport:
    concepts: int = 0
    documents: int = 0
    questions: int = 0
    edges: int = 0
    verified_concepts: int = 0
    retired: int = 0
    warnings: list[str] = field(default_factory=list)


def doc_slug(concept_slug: str, kind: str, title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{concept_slug}.{kind}.{words}"[:200]


def sync_knowledge(session: Session, content: KnowledgeContent) -> KnowledgeSyncReport:
    report = KnowledgeSyncReport(warnings=list(content.warnings))

    sources: dict[str, SourceReference] = {}
    for s in content.sources:
        row = session.scalar(select(SourceReference).where(SourceReference.slug == s.slug))
        if row is None:
            row = SourceReference(slug=s.slug, title=s.title)
            session.add(row)
        row.title, row.authors, row.citation = s.title, s.authors, s.citation
        row.url, row.license = s.url, s.license
        sources[s.slug] = row
    session.flush()

    topics = {t.slug: t for t in session.scalars(select(Topic)).all()}
    concepts: dict[str, Concept] = {}
    seen_docs: set[str] = set()
    seen_questions: set[str] = set()

    for loaded, spec in content.concepts():
        topic = topics[loaded.file.topic]
        trust = trust_of(spec)
        verified = trust is TrustStatus.VERIFIED
        reviewed_by = spec.review.by if verified else None
        reviewed_on = spec.review.on if verified else None
        version = loaded.file.version
        first_source = sources[spec.further_reading[0]].id if spec.further_reading else None

        c = session.scalar(select(Concept).where(Concept.slug == spec.slug))
        if c is None:
            c = Concept(slug=spec.slug, topic_id=topic.id)
            session.add(c)
        c.topic_id = topic.id
        c.canonical_name = spec.name
        c.aliases = list(spec.aliases)
        c.definition = spec.definition
        c.attributes = {
            **spec.attributes,
            "_further_reading": list(spec.further_reading),
            "_origin": loaded.relpath,
        }
        c.difficulty = spec.difficulty
        c.content_version = version
        c.trust_status = trust
        c.source_id = first_source
        c.reviewed_by, c.reviewed_on = reviewed_by, reviewed_on
        session.flush()
        concepts[spec.slug] = c
        report.concepts += 1
        report.verified_concepts += verified

        for d in spec.documents:
            slug = doc_slug(spec.slug, d.kind.value, d.title)
            seen_docs.add(slug)
            doc_row = session.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.slug == slug)
            )
            if doc_row is None:
                doc_row = KnowledgeDocument(slug=slug)
                session.add(doc_row)
            doc_row.concept_id = c.id
            doc_row.kind, doc_row.title, doc_row.body = d.kind, d.title, d.body
            doc_row.steps, doc_row.depth = list(d.steps), d.depth
            doc_row.content_hash = hashlib.sha256(
                (d.title + "\n" + d.body + "\n" + "\n".join(d.steps)).encode()
            ).hexdigest()
            doc_row.content_version = version
            doc_row.trust_status = trust
            doc_row.source_id = first_source
            doc_row.origin_path = loaded.relpath
            doc_row.reviewed_by, doc_row.reviewed_on = reviewed_by, reviewed_on
            report.documents += 1

        for q in spec.questions:
            seen_questions.add(q.slug)
            row_q = session.scalar(select(Question).where(Question.slug == q.slug))
            if row_q is None:
                row_q = Question(slug=q.slug, topic_id=topic.id)
                session.add(row_q)
            row_q.concept_id, row_q.topic_id = c.id, topic.id
            row_q.kind, row_q.purpose, row_q.style = q.kind, q.purpose, q.style
            row_q.prompt, row_q.options, row_q.difficulty = q.prompt, list(q.options), q.difficulty
            row_q.content_version = version
            row_q.trust_status = trust
            row_q.reviewed_by, row_q.reviewed_on = reviewed_by, reviewed_on
            session.flush()
            ans = session.scalar(
                select(VerifiedAnswer).where(VerifiedAnswer.question_id == row_q.id)
            )
            if ans is None:
                ans = VerifiedAnswer(question_id=row_q.id, answer={}, explanation="")
                session.add(ans)
            ans.answer, ans.explanation, ans.source_id = dict(q.answer), q.explanation, first_source
            report.questions += 1
    session.flush()

    # Rebuild the concept graph from the files.
    ids = [c.id for c in concepts.values()]
    if ids:
        session.execute(
            delete(ConceptRelationship).where(
                or_(
                    ConceptRelationship.source_concept_id.in_(ids),
                    ConceptRelationship.target_concept_id.in_(ids),
                )
            )
        )
    for _, spec in content.concepts():
        for attr, kind in EDGE_KINDS.items():
            for target in getattr(spec, attr):
                session.add(
                    ConceptRelationship(
                        source_concept_id=concepts[spec.slug].id,
                        target_concept_id=concepts[target].id,
                        kind=kind,
                    )
                )
                report.edges += 1

    # Anything no longer in the files is retired, not deleted.
    retired = TrustStatus.RETIRED
    for model, keep in (
        (Concept, set(concepts)),
        (KnowledgeDocument, seen_docs),
        (Question, seen_questions),
    ):
        result = session.execute(
            update(model)
            .where(model.slug.not_in(keep) if keep else model.slug.is_not(None))
            .where(model.trust_status != retired)
            .values(trust_status=retired)
        )
        report.retired += result.rowcount  # type: ignore[attr-defined]
    session.commit()
    return report


def main() -> None:
    from scholariq.core.config import get_settings
    from scholariq.db.session import get_engine
    from scholariq.knowledge.loader import load_content

    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    content = load_content(get_settings().content_dir)
    with Session(get_engine()) as session:
        report = sync_knowledge(session, content)
    for w in report.warnings:
        logger.warning(w)
    logger.info(
        "knowledge sync: %d concepts (%d verified), %d documents, %d questions, %d edges, "
        "%d retired",
        report.concepts,
        report.verified_concepts,
        report.documents,
        report.questions,
        report.edges,
        report.retired,
    )


if __name__ == "__main__":
    main()
