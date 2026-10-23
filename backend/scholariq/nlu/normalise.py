"""Clean up a question without destroying notation.

Only presentation is changed: Unicode compatibility forms, curly quotes, dashes
and whitespace. Operators, brackets, digits and identifiers such as ``T(n)``,
``O(n log n)``, ``a->b`` or ``SELECT *`` are kept exactly. Code blocks are split
out first so their whitespace survives.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+#-]*)[ \t]*\n(.*?)(?:```|\Z)", re.S)
_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
    }
)


@dataclass(frozen=True)
class CodeBlock:
    language: str
    code: str


@dataclass
class Normalised:
    original: str
    # Prose with code removed, notation intact, whitespace collapsed.
    text: str
    code: list[CodeBlock] = field(default_factory=list)
    # Shorthand that was expanded: (typed, expansion).
    expansions: list[tuple[str, str]] = field(default_factory=list)


def load_abbreviations(content_dir: Path) -> dict[str, str]:
    path = content_dir / "lexicon.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k).lower(): str(v) for k, v in (data.get("abbreviations") or {}).items()}


def _looks_like_code(lines: list[str]) -> bool:
    """Unfenced code: several lines with code punctuation and indentation."""
    if len(lines) < 2:
        return False
    signals = sum(
        bool(re.search(r"(^\s{2,}\S)|[;{}]\s*$|:\s*$|^\s*(def|for|while|if|return|int|void)\b", ln))
        for ln in lines
    )
    return signals >= max(2, len(lines) // 2)


def normalise(text: str, abbreviations: dict[str, str] | None = None) -> Normalised:
    raw = unicodedata.normalize("NFKC", text).translate(_TRANSLATE).replace("\r\n", "\n")
    code = [CodeBlock(m.group(1).lower(), m.group(2).rstrip()) for m in _FENCE.finditer(raw)]
    prose = _FENCE.sub(" ", raw)
    if not code:
        lines = [ln for ln in prose.split("\n") if ln.strip()]
        # A question line followed by pasted code.
        if len(lines) >= 3 and _looks_like_code(lines[1:]):
            code = [CodeBlock("", "\n".join(lines[1:]))]
            prose = lines[0]
    prose = re.sub(r"\s+", " ", prose).strip()
    # "i-node": the prefix is also a stopword ("I") and would be dropped, leaving
    # an ordinary word. Join it up; the knowledge base indexes the name the same way.
    prose = re.sub(r"(?<![\w-])([AaIi])-([A-Za-z]{3,})(?![\w-])", r"\1\2", prose)

    expansions: list[tuple[str, str]] = []
    if abbreviations:

        def expand(m: re.Match[str]) -> str:
            word = m.group(0)
            full = abbreviations.get(word.lower())
            if full is None:
                return word
            expansions.append((word, full))
            return full

        # Tokens of letters, digits and the few joiners used in shorthand (b/w, e.g.).
        prose = re.sub(
            r"(?<![\w/.])[A-Za-z][A-Za-z0-9]*(?:[/.][A-Za-z]+\.?)*(?![\w/])", expand, prose
        )
    return Normalised(original=text, text=prose, code=code, expansions=expansions)
