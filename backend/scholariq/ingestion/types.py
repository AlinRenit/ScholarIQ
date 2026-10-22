"""Format-independent representation of what was read from a document.

Every extractor (PDF text, OCR, spreadsheet, CSV, plain text) produces an
``ExtractedContent``: blocks of rows of cells, each cell carrying the
confidence of the *reading* (1.0 for digital text, Tesseract's word confidence
for OCR). Interpretation of what the cells mean happens later and is scored
separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SourceKind(StrEnum):
    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    SPREADSHEET = "spreadsheet"
    CSV = "csv"
    TEXT = "text"


@dataclass(frozen=True)
class Cell:
    text: str
    confidence: float = 1.0
    # Horizontal position, when the source has layout (PDF words, OCR).
    x0: float | None = None
    x1: float | None = None


@dataclass
class Row:
    cells: list[Cell]
    # Vertical position on the page, when known; used to order rows and tables.
    top: float | None = None

    @property
    def text(self) -> str:
        return " ".join(c.text for c in self.cells if c.text).strip()

    @property
    def confidence(self) -> float:
        filled = [c.confidence for c in self.cells if c.text]
        return min(filled) if filled else 0.0

    def is_blank(self) -> bool:
        return not any(c.text.strip() for c in self.cells)


@dataclass
class Block:
    """A table or a run of text lines. Rows need not have equal length."""

    rows: list[Row]
    page: int | None = None


@dataclass
class ExtractedContent:
    source: SourceKind
    blocks: list[Block] = field(default_factory=list)
    pages: int = 1
    notes: list[str] = field(default_factory=list)

    def rows(self) -> list[Row]:
        return [r for b in self.blocks for r in b.rows]
