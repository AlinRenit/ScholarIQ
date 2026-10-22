"""What to study first, from the student's own topic evidence.

Topics are listed in this order, and the answer shows why:

1. classification: Needs attention, then Developing, then Insufficient
   evidence (Strong topics are left out);
2. within a classification, topics with no weaker topic among their
   prerequisites come first, so foundations come before what builds on them;
3. then curriculum importance (5 = core), then name.

This is a short answer in the tutor. The Study Plan section adds study time,
goals and recent diagnostics to a published formula.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from scholariq.analytics.policy import Policy
from scholariq.analytics.service import compute_topics, load_result_rows
from scholariq.analytics.subjects import summarise_subjects
from scholariq.answering.model import Item, Origin, Section
from scholariq.db.models import Concept, ConceptRelationship, Topic
from scholariq.domain.enums import MasteryClass, RelationshipKind

ORDER = {
    MasteryClass.NEEDS_ATTENTION: 0,
    MasteryClass.DEVELOPING: 1,
    MasteryClass.INSUFFICIENT_EVIDENCE: 2,
}
LABEL = {
    MasteryClass.NEEDS_ATTENTION: "Needs attention",
    MasteryClass.DEVELOPING: "Developing",
    MasteryClass.INSUFFICIENT_EVIDENCE: "Insufficient evidence",
}
MAX_ITEMS = 6


def topic_prerequisites(session: Session) -> dict[str, set[str]]:
    """topic slug -> topic slugs it depends on, from concept-level requires links."""
    src, dst = aliased(Concept), aliased(Concept)
    ts, td = aliased(Topic), aliased(Topic)
    rows = session.execute(
        select(ts.slug, td.slug)
        .select_from(ConceptRelationship)
        .join(src, ConceptRelationship.source_concept_id == src.id)
        .join(dst, ConceptRelationship.target_concept_id == dst.id)
        .join(ts, src.topic_id == ts.id)
        .join(td, dst.topic_id == td.id)
        .where(ConceptRelationship.kind == RelationshipKind.REQUIRES)
    ).all()
    out: dict[str, set[str]] = {}
    for a, b in rows:
        if a != b:
            out.setdefault(a, set()).add(b)
    return out


def study_advice(session: Session, student_id: str, policy: Policy) -> list[Section]:
    rows = load_result_rows(session, student_id)
    views = compute_topics(session, student_id, policy, summarise_subjects(rows, policy))
    if not views:
        return [
            Section(
                kind="note",
                title="No results yet",
                text="There are no confirmed results to plan from. Import a marksheet in My "
                "Academics, or add topic test results on the Topics page.",
                origin=Origin(kind="template"),
            )
        ]
    label = {v.topic.slug: v.classification.label for v in views}
    needs = topic_prerequisites(session)
    candidates = [v for v in views if v.classification.label in ORDER]
    if not candidates:
        return [
            Section(
                kind="note",
                title="Every classified topic is Strong",
                text="All your topics with enough evidence are classified Strong. Practice on new "
                "topics, or go deeper on one you choose.",
                origin=Origin(kind="analysis"),
            )
        ]

    def weaker_prereq(slug: str) -> bool:
        mine = ORDER.get(label.get(slug, MasteryClass.STRONG), 9)
        return any(
            ORDER.get(label.get(p, MasteryClass.STRONG), 9) <= mine for p in needs.get(slug, ())
        )

    def importance(v: object) -> int:
        return max((imp for _, _, imp in v.subjects), default=3)  # type: ignore[attr-defined]

    ordered = sorted(
        candidates,
        key=lambda v: (
            ORDER[v.classification.label],
            weaker_prereq(v.topic.slug),
            -importance(v),
            v.topic.name,
        ),
    )
    items = []
    for v in ordered[:MAX_ITEMS]:
        c = v.classification
        why = f"{LABEL[c.label]} ({c.direct_observations} topic-level observation(s))"
        if weaker_prereq(v.topic.slug):
            why += "; builds on another topic you should look at first"
        items.append(Item(text=v.topic.name, detail=f"{why}. {c.next_action}", topic=v.topic.slug))
    return [
        Section(
            kind="list", title="Study these first", items=items, origin=Origin(kind="analysis")
        ),
        Section(
            kind="note",
            title="How this order was chosen",
            text="Needs attention before Developing before Insufficient evidence; within each, "
            "topics whose prerequisite topics are not weaker come first, then curriculum "
            f"importance. Classifications use {c.rule_version}; Strong topics are left out. "
            "Asking the tutor about a topic never changes its classification.",
            origin=Origin(kind="template"),
        ),
    ]
