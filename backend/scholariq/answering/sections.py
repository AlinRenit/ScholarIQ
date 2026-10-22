"""Turn knowledge-base rows into answer sections, copying their text as is."""

from __future__ import annotations

import re

from scholariq.answering.content import ConceptBundle
from scholariq.answering.model import (
    CheckQuestion,
    ConceptRef,
    Item,
    Origin,
    Section,
    SectionKind,
)
from scholariq.db.models import KnowledgeDocument, Question
from scholariq.domain.enums import KnowledgeDocumentKind as K

_DOC_KIND: dict[K, SectionKind] = {
    K.EXPLANATION: "explanation",
    K.PROCEDURE: "procedure",
    K.EXAMPLE: "example",
    K.MISCONCEPTION: "misconception",
    K.EXERCISE: "example",
    K.REFERENCE: "note",
}


def humanise(key: str) -> str:
    return key.replace("_", " ").capitalize()


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip(), re.S)
    return (m.group(1) if m else text).strip()


def knowledge(b: ConceptBundle, doc: KnowledgeDocument | None = None) -> Origin:
    return Origin(
        kind="knowledge",
        concept=b.ref.slug,
        document=doc.slug if doc else None,
        trust=doc.trust_status if doc else b.concept.trust_status,
    )


def definition(b: ConceptBundle, title: str | None = None) -> Section:
    return Section(
        kind="definition",
        title=title or "Definition",
        text=b.concept.definition,
        origin=knowledge(b),
    )


def facts(b: ConceptBundle) -> Section | None:
    attrs = b.attributes
    if not attrs:
        return None
    return Section(
        kind="facts",
        title="Key facts",
        rows=[[humanise(k), v] for k, v in attrs.items()],
        origin=knowledge(b),
    )


def document(b: ConceptBundle, doc: KnowledgeDocument) -> Section:
    return Section(
        kind=_DOC_KIND[doc.kind],
        title=doc.title,
        text=doc.body or None,
        steps=list(doc.steps),
        origin=knowledge(b, doc),
    )


def check(b: ConceptBundle, q: Question, title: str = "Check your understanding") -> Section:
    return Section(
        kind="check",
        title=title,
        question=CheckQuestion(slug=q.slug, prompt=q.prompt, kind=q.kind.value, options=q.options),
        origin=Origin(kind="knowledge", concept=b.ref.slug, trust=q.trust_status),
    )


def concept_list(title: str, refs: list[ConceptRef], origin: Origin) -> Section:
    return Section(
        kind="list",
        title=title,
        items=[Item(text=r.name, detail=r.topic_name, concept=r.slug) for r in refs],
        origin=origin,
    )


def pick_question(questions: list[Question], level: str, exclude: set[str]) -> Question | None:
    pool = [q for q in questions if q.slug not in exclude] or questions
    if not pool:
        return None
    ordered = sorted(pool, key=lambda q: (q.difficulty, q.slug))
    if level == "easy":
        return ordered[0]
    if level == "challenge":
        return ordered[-1]
    return ordered[len(ordered) // 2]
