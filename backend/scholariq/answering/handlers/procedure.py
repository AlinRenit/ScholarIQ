"""Handler C: step-by-step teaching.

For a concept: what it builds on, its recorded procedure, a worked example and
a practice question. For a topic: its concepts in prerequisite order, each
with its procedure and example. If the knowledge base has no procedure for
what was asked, the answer says so and does not make one up.
"""

from __future__ import annotations

from scholariq.answering import sections as S
from scholariq.answering.content import ConceptBundle, topic_concepts
from scholariq.answering.handlers.base import HandlerContext
from scholariq.answering.model import Item, Origin, Section
from scholariq.db.models import Concept
from scholariq.domain.enums import KnowledgeDocumentKind as K


def procedure_for_concept(ctx: HandlerContext, b: ConceptBundle) -> list[Section]:
    out: list[Section] = []
    if b.requires:
        out.append(
            Section(
                kind="list",
                title="Step 1: make sure you know",
                items=[
                    Item(text=r.name, detail=_first(ctx, r.slug), concept=r.slug)
                    for r in b.requires
                ],
                origin=S.knowledge(b),
            )
        )
    out.append(S.definition(b, f"{'Step 2: ' if b.requires else ''}{b.ref.name}"))
    procedures = b.docs(K.PROCEDURE)
    if procedures:
        out += [S.document(b, d) for d in procedures]
    else:
        out.append(
            Section(
                kind="note",
                title="No recorded procedure",
                text=f"The knowledge base has no step-by-step procedure for {b.ref.name}, so "
                "none is given here. The explanation and example below are what it records.",
                origin=Origin(kind="template"),
            )
        )
        out += [S.document(b, d) for d in b.docs(K.EXPLANATION)[:1]]
    out += [S.document(b, d) for d in b.docs(K.EXAMPLE, K.EXERCISE)]
    out += [S.document(b, d) for d in b.docs(K.MISCONCEPTION)]
    q = S.pick_question(b.questions, "medium", ctx.asked)
    if q is not None:
        out.append(S.check(b, q, "Practice problem"))
    return out


def procedure_for_topic(ctx: HandlerContext, topic_slug: str) -> tuple[list[Section], list[str]]:
    """Walk a topic's concepts in prerequisite order. Returns sections and concept slugs."""
    found = topic_concepts(ctx.session, topic_slug, ctx.allowed)
    if found is None or not found[1]:
        return [], []
    topic, concepts = found
    ordered = prerequisite_order(ctx, concepts)
    out: list[Section] = []
    used: list[str] = []
    for i, c in enumerate(ordered, 1):
        b = ctx.bundle(c.slug)
        if b is None:
            continue
        used.append(b.ref.slug)
        out.append(S.definition(b, f"Step {i}: {b.ref.name}"))
        out += [S.document(b, d) for d in b.docs(K.PROCEDURE)]
        out += [S.document(b, d) for d in b.docs(K.EXAMPLE)[:1]]
    last = ctx.bundle(ordered[-1].slug) if ordered else None
    if last is not None and (q := S.pick_question(last.questions, "medium", ctx.asked)):
        out.append(S.check(last, q, "Practice problem"))
    return out, used


def prerequisite_order(ctx: HandlerContext, concepts: list[Concept]) -> list[Concept]:
    """Topological order by ``requires`` within the list; ties by difficulty, then name."""
    by_slug = {c.slug: c for c in concepts}
    needs: dict[str, set[str]] = {}
    for c in concepts:
        b = ctx.bundle(c.slug)
        needs[c.slug] = {r.slug for r in (b.requires if b else []) if r.slug in by_slug}
    done: list[Concept] = []
    remaining = dict(needs)
    while remaining:
        ready = sorted(
            (s for s, deps in remaining.items() if deps <= {d.slug for d in done}),
            key=lambda s: (by_slug[s].difficulty, by_slug[s].canonical_name),
        )
        if not ready:  # cycles are rejected on import; this is only a guard
            ready = sorted(remaining)
        done.append(by_slug[ready[0]])
        remaining.pop(ready[0])
    return done


def _first(ctx: HandlerContext, slug: str) -> str | None:
    b = ctx.bundle(slug)
    return S.first_sentence(b.concept.definition) if b else None
