"""Upload validation: size, type by content signature, and basic integrity.

The declared filename extension and browser-supplied content type are never
trusted on their own; the file's leading bytes decide its type, and the
extension must agree.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath


class FileKind(StrEnum):
    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"
    XLSX = "xlsx"
    CSV = "csv"
    TEXT = "text"


MEDIA_TYPES = {
    FileKind.PDF: "application/pdf",
    FileKind.PNG: "image/png",
    FileKind.JPEG: "image/jpeg",
    FileKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    FileKind.CSV: "text/csv",
    FileKind.TEXT: "text/plain",
}

EXTENSIONS = {
    FileKind.PDF: {".pdf"},
    FileKind.PNG: {".png"},
    FileKind.JPEG: {".jpg", ".jpeg"},
    FileKind.XLSX: {".xlsx"},
    FileKind.CSV: {".csv"},
    FileKind.TEXT: {".txt"},
}

# Limits that protect the parsers from decompression bombs and huge inputs.
MAX_XLSX_UNCOMPRESSED = 50 * 1024 * 1024
MAX_XLSX_RATIO = 100
MAX_IMAGE_PIXELS = 40_000_000
MAX_PDF_PAGES = 20


class UploadRejected(ValueError):
    """The upload is refused; the message is safe to show to the student."""


@dataclass(frozen=True)
class ValidatedUpload:
    kind: FileKind
    media_type: str
    filename: str
    data: bytes


def safe_filename(name: str | None) -> str:
    # Keep only the final path component and printable characters. The result
    # is for display only; storage uses a server-generated key.
    base = PurePath((name or "upload").replace("\\", "/")).name
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '<>:"|?*')
    return cleaned[:200] or "upload"


def sniff(data: bytes) -> FileKind | None:
    if data.startswith(b"%PDF-"):
        return FileKind.PDF
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileKind.PNG
    if data.startswith(b"\xff\xd8\xff"):
        return FileKind.JPEG
    if data.startswith(b"PK\x03\x04"):
        return FileKind.XLSX  # confirmed as a workbook below
    return None


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:4096]:
        return None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _check_xlsx(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names or not any(n.startswith("xl/") for n in names):
                raise UploadRejected("This ZIP file is not an Excel workbook.")
            total = sum(i.file_size for i in zf.infolist())
            if total > MAX_XLSX_UNCOMPRESSED or total > MAX_XLSX_RATIO * max(len(data), 1):
                raise UploadRejected("This workbook expands to an unsafe size.")
            if any(n.endswith("vbaProject.bin") for n in names):
                raise UploadRejected("Workbooks containing macros are not accepted.")
    except zipfile.BadZipFile as exc:
        raise UploadRejected("The workbook is damaged and cannot be read.") from exc


def _check_pdf(data: bytes) -> None:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise UploadRejected("Password-protected PDFs are not supported.") from exc
        raise UploadRejected("The PDF is damaged and cannot be read.") from exc
    try:
        pages = len(pdf)
    finally:
        pdf.close()
    if pages == 0:
        raise UploadRejected("The PDF has no pages.")
    if pages > MAX_PDF_PAGES:
        raise UploadRejected(f"Marksheets longer than {MAX_PDF_PAGES} pages are not supported.")


def _check_image(data: bytes) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise UploadRejected("The image is damaged and cannot be read.") from exc
    if width * height > MAX_IMAGE_PIXELS:
        raise UploadRejected("The image resolution is too large.")


def validate_upload(filename: str | None, data: bytes, max_bytes: int) -> ValidatedUpload:
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")

    name = safe_filename(filename)
    ext = PurePath(name).suffix.lower()
    kind = sniff(data)

    if kind is None:
        text = _decode_text(data)
        if text is None:
            raise UploadRejected("Unsupported file type. Use PDF, PNG, JPEG, XLSX, CSV or TXT.")
        kind = FileKind.CSV if ext == ".csv" else FileKind.TEXT

    if ext not in EXTENSIONS[kind]:
        raise UploadRejected(
            f"The file contents look like {kind.value.upper()}, "
            f"which does not match '{ext or 'no extension'}'."
        )

    if kind is FileKind.XLSX:
        _check_xlsx(data)
    elif kind is FileKind.PDF:
        _check_pdf(data)
    elif kind in (FileKind.PNG, FileKind.JPEG):
        _check_image(data)

    return ValidatedUpload(kind=kind, media_type=MEDIA_TYPES[kind], filename=name, data=data)
