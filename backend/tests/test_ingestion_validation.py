from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from scholariq.ingestion.storage import FileStore
from scholariq.ingestion.validation import FileKind, UploadRejected, safe_filename, validate_upload

FIXTURES = Path(__file__).parent / "fixtures" / "marksheets"
LIMIT = 10 * 1024 * 1024


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("digital_semester3.pdf", FileKind.PDF),
        ("scanned_semester4.png", FileKind.PNG),
        ("scanned_semester4.jpg", FileKind.JPEG),
        ("theory_practical.xlsx", FileKind.XLSX),
        ("percentages.csv", FileKind.CSV),
        ("plain_report.txt", FileKind.TEXT),
    ],
)
def test_accepts_supported_files(name: str, kind: FileKind) -> None:
    assert validate_upload(name, load(name), LIMIT).kind is kind


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("truncated.pdf", "damaged"),
        ("not_a_pdf.pdf", "Unsupported"),
        ("png_named_csv.csv", "does not match"),
    ],
)
def test_rejects_malformed_or_mislabelled(name: str, message: str) -> None:
    with pytest.raises(UploadRejected, match=message):
        validate_upload(name, load(name), LIMIT)


def test_rejects_empty_and_oversize() -> None:
    with pytest.raises(UploadRejected, match="empty"):
        validate_upload("a.csv", b"", LIMIT)
    with pytest.raises(UploadRejected, match="larger"):
        validate_upload("a.csv", b"x" * 2048, 1024)


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_rejects_zip_that_is_not_a_workbook() -> None:
    with pytest.raises(UploadRejected, match="not an Excel"):
        validate_upload("a.xlsx", _zip({"hello.txt": b"hi"}), LIMIT)


def test_rejects_decompression_bomb() -> None:
    bomb = _zip({"[Content_Types].xml": b"<x/>", "xl/sheet.xml": b"0" * (60 * 1024 * 1024)})
    with pytest.raises(UploadRejected, match="unsafe size"):
        validate_upload("a.xlsx", bomb, LIMIT)


def test_rejects_macro_workbook() -> None:
    data = _zip({"[Content_Types].xml": b"<x/>", "xl/vbaProject.bin": b"\x00"})
    with pytest.raises(UploadRejected, match="macros"):
        validate_upload("a.xlsx", data, LIMIT)


def test_binary_garbage_rejected() -> None:
    with pytest.raises(UploadRejected):
        validate_upload("a.txt", b"\x00\x01\x02" * 100, LIMIT)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\marks.pdf", "marks.pdf"),
        ("ok<script>.pdf", "okscript.pdf"),
        (None, "upload"),
    ],
)
def test_safe_filename(raw: str | None, expected: str) -> None:
    assert safe_filename(raw) == expected


def test_store_rejects_path_traversal_keys(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    key = store.save(b"data")
    assert store.read(key) == b"data"
    for bad in ("../x", "/etc/passwd", "a/b", ""):
        with pytest.raises(ValueError):
            store.read(bad)
