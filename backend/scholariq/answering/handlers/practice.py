"""Practice questions for a concept or topic.

Questions are shown without answers; the student answers in the chat and the
answer is checked on the server. Tutor practice is a self-check: it is not
recorded as topic evidence (diagnostic quizzes that do count arrive with the
Practice section).
"""

from __future__ import annotations

from scholariq.answering import sections as S
from scholariq.answering.content import topic_concepts
from scholariq.answering.handlers.base import HandlerContext
from scholariq.answering.model import Origin, Section

MAX_QUESTIONS = 5


def practice(
    ctx: HandlerContext, concepts: list[str], topic_slug: str | None = None
) -> tuple[list[Section], list[str]]:
    if topic_slug is not None:
        found = topic_concepts(ctx.session, topic_slug, ctx.allowed)
        concepts = [c.slug for c in found[1]] if found else []
    pool = []
    for slug in concepts:
        b = ctx.bundle(slug)
        if b is not None:
            pool += [(q.difficulty, q.slug, b, q) for q in b.questions if q.slug not in ctx.asked]
    pool.sort(key=lambda t: (t[0], t[1]))
    if not pool:
        return [
            Section(
                kind="note",
                title="No practice questions",
                text="The knowledge base has no further practice questions for this.",
                origin=Origin(kind="template"),
            )
        ], concepts
    # Spread across difficulty: easiest first, but not five of the same level.
    picked = pool[:: max(1, len(pool) // MAX_QUESTIONS)][:MAX_QUESTIONS]
    out = [S.check(b, q, f"Question {i}") for i, (_, _, b, q) in enumerate(picked, 1)]
    out.append(
        Section(
            kind="note",
            title="About these questions",
            text="Answers are checked when you submit them. These are for self-checking and "
            "are not recorded as evidence about your topics.",
            origin=Origin(kind="template"),
        )
    )
    return out, sorted({b.ref.slug for _, _, b, _ in picked})
