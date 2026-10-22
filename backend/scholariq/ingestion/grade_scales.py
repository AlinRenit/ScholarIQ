"""Built-in grading-scale templates.

A template is only applied to a document when the student explicitly selects
it during review. Grades are never converted using a guessed scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScaleTemplate:
    key: str
    name: str
    description: str
    max_points: Decimal
    points: dict[str, Decimal]


def _d(mapping: dict[str, str]) -> dict[str, Decimal]:
    return {k: Decimal(v) for k, v in mapping.items()}


TEMPLATES: dict[str, ScaleTemplate] = {
    t.key: t
    for t in (
        ScaleTemplate(
            "ugc_cbcs_10",
            "10-point letter scale (UGC CBCS)",
            "O=10, A+=9, A=8, B+=7, B=6, C=5, P=4, F=0. Used by many Indian universities.",
            Decimal(10),
            _d(
                {"O": "10", "A+": "9", "A": "8", "B+": "7", "B": "6", "C": "5", "P": "4", "F": "0"}
            ),  # fmt: skip
        ),
        ScaleTemplate(
            "letter_4",
            "4.0 letter scale with plus/minus",
            "A/A+=4.0, A-=3.7, B+=3.3, B=3.0, B-=2.7, C+=2.3, C=2.0, C-=1.7, D+=1.3, D=1.0, F=0. "
            "Institutions differ (some give A+ 4.3); check yours.",
            Decimal(4),
            _d(
                {
                    "A+": "4.0",
                    "A": "4.0",
                    "A-": "3.7",
                    "B+": "3.3",
                    "B": "3.0",
                    "B-": "2.7",
                    "C+": "2.3",
                    "C": "2.0",
                    "C-": "1.7",
                    "D+": "1.3",
                    "D": "1.0",
                    "F": "0",
                }
            ),  # fmt: skip
        ),
    )
}
