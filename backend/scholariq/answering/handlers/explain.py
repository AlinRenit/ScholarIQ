"""Handler A: definitions and explanations.

Structure for one concept (sections are left out when the knowledge base has
nothing for them, never filled with invented text):

1. definition
2. prerequisites (guided level)
3. key facts (principle, operations, costs as recorded)
4. explanations, simplest first, up to the plan's depth
5. procedures, if the concept has one
6. worked examples
7. common mistakes
8. connections or what comes next
9. summary (guided level)
10. a check question
"""

from __future__ import annotations

from scholariq.answering import sections as S
from scholariq.answering.content import ConceptBundle
from scholariq.answering.handlers.base import HandlerContext
from scholariq.answering.model import Item, Origin, Section
from scholariq.domain.enums import KnowledgeDocumentKind as K
from scholariq.tutoring.policy import TeachingPlan


def explain_concept(
    ctx: HandlerContext, b: ConceptBundle, plan: TeachingPlan, reasoning: bool = False
) -> list[Section]:
    out: list[Section] = [S.definition(b)]

    if plan.prerequisites and b.requires:
        out.append(
            Section(
                kind="list",
                title="What you need first",
                items=[
                    Item(text=r.name, detail=_definition_of(ctx, r.slug), concept=r.slug)
                    for r in b.requires
                ],
                origin=S.knowledge(b),
            )
        )

    if (f := S.facts(b)) is not None:
        out.append(f)

    explanations = sorted(b.docs(K.EXPLANATION), key=lambda d: d.depth)
    within = [d for d in explanations if d.depth <= plan.max_depth] or explanations[:1]
    if plan.level == "overview":
        # Concise: the most advanced explanation within reach, not the introductory one.
        within = within[-1:]
    out += [S.document(b, d) for d in within[: plan.explanations]]

    procedures = b.docs(K.PROCEDURE)
    out += [S.document(b, d) for d in procedures[: 1 if plan.level == "overview" else None]]

    examples = b.docs(K.EXAMPLE, K.EXERCISE)
    out += [S.document(b, d) for d in examples[: plan.examples]]

    if plan.misconceptions or reasoning:
        out += [S.document(b, d) for d in b.docs(K.MISCONCEPTION)]
    out += [S.document(b, d) for d in b.docs(K.REFERENCE)]

    if plan.connections:
        unique = list(
            {r.slug: r for r in [*b.requires, *b.contrasts, *b.related, *b.part_of]}.values()
        )
        if unique:
            out.append(S.concept_list("Connected concepts", unique, S.knowledge(b)))
    if plan.next_topics and b.required_by:
        out.append(S.concept_list("What builds on this", b.required_by, S.knowledge(b)))

    if plan.summary:
        attrs = b.attributes
        out.append(
            Section(
                kind="summary",
                title="Summary",
                items=[Item(text=S.first_sentence(b.concept.definition))]
                + [Item(text=f"{S.humanise(k)}: {v}") for k, v in list(attrs.items())[:3]],
                origin=S.knowledge(b),
            )
        )

    q = S.pick_question(b.questions, plan.check, ctx.asked)
    if q is not None:
        title = "Challenge question" if plan.check == "challenge" else "Check your understanding"
        out.append(S.check(b, q, title))
    return out


def explain_brief(b: ConceptBundle) -> list[Section]:
    """Definition and key facts only, used when several concepts are asked about at once."""
    out = [S.definition(b, b.ref.name)]
    if (f := S.facts(b)) is not None:
        f.title = f"{b.ref.name}: key facts"
        out.append(f)
    return out


def topic_overview(ctx: HandlerContext, topic_slug: str) -> list[Section]:
    from scholariq.answering.content import topic_concepts

    found = topic_concepts(ctx.session, topic_slug, ctx.allowed)
    if found is None or not found[1]:
        return []
    topic, concepts = found
    return [
        Section(
            kind="list",
            title=f"{topic.name}: the concepts it covers",
            items=[
                Item(text=c.canonical_name, detail=S.first_sentence(c.definition), concept=c.slug)
                for c in concepts
            ],
            origin=Origin(kind="knowledge", trust=None),
        )
    ]


def _definition_of(ctx: HandlerContext, slug: str) -> str | None:
    b = ctx.bundle(slug)
    return S.first_sentence(b.concept.definition) if b else None
