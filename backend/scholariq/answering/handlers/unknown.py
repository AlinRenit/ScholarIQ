"""Handler F: questions the knowledge base cannot answer.

Says what is missing, shows the closest concepts that do exist (labelled as
such, never presented as the answer) and lists what the tutor covers. It
never fabricates an answer or a reference.
"""

from __future__ import annotations

from scholariq.answering.model import Item, Origin, Section, Suggestion
from scholariq.knowledge.index import SearchHit


def abstain(
    reason: str, closest: list[SearchHit], subjects: list[str]
) -> tuple[list[Section], list[Suggestion]]:
    sections = [
        Section(
            kind="note",
            title="Not something I can answer",
            text=reason,
            origin=Origin(kind="template"),
        )
    ]
    suggestions: list[Suggestion] = []
    if closest:
        sections.append(
            Section(
                kind="list",
                title="Closest concepts I do cover",
                items=[
                    Item(text=h.concept.name, detail=h.concept.topic_name, concept=h.concept.slug)
                    for h in closest
                ],
                origin=Origin(kind="template"),
            )
        )
        suggestions = [
            Suggestion(
                label=f"Explain {h.concept.name}", action="ask", query=f"Explain {h.concept.name}"
            )
            for h in closest[:2]
        ]
    if subjects:
        sections.append(
            Section(
                kind="note",
                title="What I cover",
                text="Questions about these subjects, answered from a curated knowledge base: "
                + ", ".join(subjects)
                + ". I can also solve some problem types: arithmetic and percentages, linear and "
                "quadratic equations, recurrences, truth tables, graph traversals on a graph you "
                "write out, and SQL SELECT queries on a practice database.",
                origin=Origin(kind="template"),
            )
        )
    return sections, suggestions
