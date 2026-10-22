"""Mark an answer to a knowledge-base question. Exact rules, no partial credit.

* multiple choice: the chosen option index must equal the stored one;
* numeric: within the stored tolerance (default 1e-9 relative);
* short answer: after lower-casing, removing accents, punctuation and extra
  spaces, the response must equal one of the accepted answers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from scholariq.db.models import Question, VerifiedAnswer
from scholariq.domain.enums import QuestionKind
from scholariq.retrieval.text import fold


@dataclass(frozen=True)
class Marked:
    correct: bool
    expected: str
    explanation: str


class BadResponse(ValueError):
    pass


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.+#-]", " ", fold(text))).strip()


def mark(question: Question, answer: VerifiedAnswer, response: dict[str, Any]) -> Marked:
    stored = answer.answer
    if question.kind is QuestionKind.MULTIPLE_CHOICE:
        idx = response.get("option_index")
        if not isinstance(idx, int) or not 0 <= idx < len(question.options):
            raise BadResponse("Choose one of the options.")
        right = int(stored["option_index"])
        return Marked(idx == right, question.options[right], answer.explanation)
    if question.kind is QuestionKind.NUMERIC:
        try:
            value = float(response.get("value"))  # type: ignore[arg-type]
        except (TypeError, ValueError) as e:
            raise BadResponse("Enter a number.") from e
        target = float(stored["value"])
        tol = float(stored.get("tolerance") or 0)
        ok = (
            abs(value - target) <= tol
            if tol
            else math.isclose(value, target, rel_tol=1e-9, abs_tol=1e-12)
        )
        return Marked(
            ok, f"{stored['value']}" + (f" (±{tol:g})" if tol else ""), answer.explanation
        )
    text = response.get("text")
    if not isinstance(text, str) or not text.strip():
        raise BadResponse("Type an answer.")
    accepted = [str(a) for a in stored.get("accepted", [])]
    ok = _norm(text) in {_norm(a) for a in accepted}
    return Marked(ok, accepted[0] if accepted else "", answer.explanation)
