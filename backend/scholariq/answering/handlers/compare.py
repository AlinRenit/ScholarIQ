"""Handler B: comparisons.

The table has one row per attribute recorded for either concept. Attributes
both concepts record come first. A cell the knowledge base has no value for
says so instead of being filled in. Below the table, any explanation or
mistake entry of one concept that names the other is included, since that is
where the knowledge base discusses the difference directly.
"""

from __future__ import annotations

import re

from scholariq.answering import sections as S
from scholariq.answering.content import ConceptBundle
from scholariq.answering.model import Origin, Section
from scholariq.domain.enums import KnowledgeDocumentKind as K

NOT_RECORDED = "Not recorded in the knowledge base"


def compare(bundles: list[ConceptBundle]) -> list[Section]:
    a, b = bundles[0], bundles[1]
    keys_a, keys_b = list(a.attributes), list(b.attributes)
    shared = [k for k in keys_a if k in keys_b]
    only = [k for k in keys_a if k not in keys_b] + [k for k in keys_b if k not in keys_a]
    rows = [
        [
            "Definition",
            S.first_sentence(a.concept.definition),
            S.first_sentence(b.concept.definition),
        ]
    ]
    for k in shared + only:
        rows.append(
            [S.humanise(k), a.attributes.get(k, NOT_RECORDED), b.attributes.get(k, NOT_RECORDED)]
        )
    out = [
        Section(
            kind="table",
            title=f"{a.ref.name} and {b.ref.name} compared",
            columns=["", a.ref.name, b.ref.name],
            rows=rows,
            origin=Origin(kind="knowledge", concept=f"{a.ref.slug} {b.ref.slug}"),
        )
    ]
    if any(r.slug == b.ref.slug for r in a.contrasts):
        out.append(
            Section(
                kind="note",
                title="How they relate",
                text=f"The knowledge base lists {a.ref.name} and {b.ref.name} as contrasting "
                "concepts that are often confused.",
                origin=Origin(kind="template"),
            )
        )
    for x, y in ((a, b), (b, a)):
        names = [y.ref.name, *y.concept.aliases]
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in names if len(n) > 2) + r")\b", re.I
        )
        for d in x.docs(K.EXPLANATION, K.MISCONCEPTION, K.EXAMPLE):
            if pattern.search(f"{d.title}\n{d.body}"):
                out.append(S.document(x, d))
    return out
