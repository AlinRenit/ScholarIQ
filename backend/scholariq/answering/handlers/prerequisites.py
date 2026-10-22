"""Prerequisites: what to learn before a concept or topic.

Follows ``requires`` links transitively and lists the results in an order you
can study them in: a concept always comes after everything it requires.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import aliased

from scholariq.answering import sections as S
from scholariq.answering.handlers.base import HandlerContext
from scholariq.answering.model import Item, Origin, Section
from scholariq.db.models import Concept, ConceptRelationship, Topic
from scholariq.domain.enums import RelationshipKind


def _graph(ctx: HandlerContext) -> tuple[dict[str, set[str]], dict[str, tuple[Concept, Topic]]]:
    src, dst = aliased(Concept), aliased(Concept)
    rows = ctx.session.execute(
        select(src.slug, dst.slug)
        .select_from(ConceptRelationship)
        .join(src, ConceptRelationship.source_concept_id == src.id)
        .join(dst, ConceptRelationship.target_concept_id == dst.id)
        .where(
            ConceptRelationship.kind == RelationshipKind.REQUIRES,
            src.trust_status.in_(ctx.allowed),
            dst.trust_status.in_(ctx.allowed),
        )
    ).all()
    requires: dict[str, set[str]] = {}
    for a, b in rows:
        requires.setdefault(a, set()).add(b)
    info = {
        c.slug: (c, t)
        for c, t in ctx.session.execute(
            select(Concept, Topic)
            .join(Topic, Concept.topic_id == Topic.id)
            .where(Concept.trust_status.in_(ctx.allowed))
        ).tuples()
    }
    return requires, info


def study_order(requires: dict[str, set[str]], start: list[str]) -> list[str]:
    """Every concept ``start`` depends on, dependencies first (post-order DFS)."""
    order: list[str] = []
    seen: set[str] = set()

    def visit(slug: str) -> None:
        for dep in sorted(requires.get(slug, ())):
            if dep not in seen:
                seen.add(dep)
                visit(dep)
                order.append(dep)

    for s in start:
        visit(s)
    return [s for s in order if s not in start]


def prerequisites(
    ctx: HandlerContext, concepts: list[str], topic_slug: str | None = None
) -> tuple[list[Section], list[str]]:
    requires, info = _graph(ctx)
    if topic_slug is not None:
        concepts = [s for s, (_, t) in info.items() if t.slug == topic_slug]
    order = [s for s in study_order(requires, concepts) if s in info]
    if topic_slug is not None:
        order = [s for s in order if info[s][1].slug != topic_slug]
    if topic_slug is not None and concepts:
        target = info[concepts[0]][1].name
    else:
        target = ", ".join(info[s][0].canonical_name for s in concepts if s in info)
    if not order:
        return [
            Section(
                kind="note",
                title="No recorded prerequisites",
                text="The knowledge base records nothing that must come before "
                f"{target or 'this'}. "
                "It is a reasonable starting point.",
                origin=Origin(kind="template"),
            )
        ], concepts
    items = [
        Item(
            text=info[s][0].canonical_name,
            detail=f"{info[s][1].name}: {S.first_sentence(info[s][0].definition)}",
            concept=s,
        )
        for s in order
    ]
    title = f"Learn these before {target}, in this order" if target else "Learn these first"
    return [
        Section(
            kind="list",
            title=title,
            items=items,
            origin=Origin(kind="knowledge"),
        ),
        Section(
            kind="note",
            title="How this order was found",
            text="Each concept is listed after everything it requires, following the "
            "prerequisite links recorded in the knowledge base.",
            origin=Origin(kind="template"),
        ),
    ], order
