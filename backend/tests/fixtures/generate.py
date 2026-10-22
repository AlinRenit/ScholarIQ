"""Regenerate the marksheet fixtures in ./marksheets.

Run from backend/:  python -m tests.fixtures.generate
The outputs are committed so tests do not depend on fonts or reportlab.
All names and marks are fictional.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).parent / "marksheets"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SEM3 = [
    ["S.No", "Subject Code", "Subject Name", "Max Marks", "Marks Obtained", "Grade", "Credits"],
    ["1", "CS301", "Data Structures", "100", "78", "A", "4"],
    ["2", "CS302", "Operating Systems", "100", "52", "C", "4"],
    ["3", "CS303", "Database Management Systems", "100", "45", "D", "3"],
    ["4", "CS304", "Computer Networks", "100", "AB", "-", "3"],
    ["5", "CS305L", "Data Structures Lab", "50", "44", "A+", "2"],
    ["6", "MA301", "Discrete Mathematics", "100", "91", "O", "4"],
]


def digital_pdf() -> None:
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    story = [
        Paragraph("Example Institute of Technology", styles["Title"]),
        Paragraph("Statement of Marks - B.Tech Computer Science", styles["Normal"]),
        Paragraph("Name of the Student: Test Student &nbsp; Roll No: 21CS999", styles["Normal"]),
        Paragraph("Semester III - Regular Examination November 2025", styles["Normal"]),
        Spacer(1, 12),
    ]
    t = Table(SEM3)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story += [t, Spacer(1, 12), Paragraph("SGPA: 7.42 &nbsp; Result: PASS", styles["Normal"])]
    doc.build(story)
    (OUT / "digital_semester3.pdf").write_bytes(buf.getvalue())


def unruled_pdf() -> None:
    """Two semesters, no table borders, so columns come from word positions."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    cols = [50, 130, 360, 430, 500]

    def line(values: list[str]) -> None:
        nonlocal y
        for x, v in zip(cols, values, strict=False):
            c.drawString(x, y, v)
        y -= 18

    c.drawString(50, y, "University Grade Card")
    y -= 30
    c.drawString(50, y, "Semester 1")
    y -= 20
    line(["Code", "Course Title", "Credits", "Grade", "Grade Points"])
    line(["MA101", "Engineering Mathematics I", "4", "B+", "7"])
    line(["CS101", "Programming in C", "3", "A", "8"])
    line(["PH101", "Engineering Physics", "3", "F", "0"])
    y -= 20
    c.drawString(50, y, "Semester 2 (Supplementary for PH101)")
    y -= 20
    line(["Code", "Course Title", "Credits", "Grade", "Grade Points"])
    line(["PH101", "Engineering Physics", "3", "C", "5"])
    line(["CS102", "Data Structures", "4", "A+", "9"])
    c.save()
    (OUT / "unruled_grades.pdf").write_bytes(buf.getvalue())


def _render(rows: list[list[str]], title: str, cols: list[int], noisy: bool) -> Image.Image:
    font = ImageFont.truetype(FONT, 26)
    img = Image.new("L", (1400, 120 + 52 * (len(rows) + 2)), 255)
    d = ImageDraw.Draw(img)
    d.text((60, 40), title, font=font, fill=0)
    y = 120
    for row in rows:
        for x, v in zip(cols, row, strict=False):
            d.text((x, y), v, font=font, fill=0)
        y += 52
    if noisy:
        img = img.rotate(0.6, expand=False, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
    return img


def scanned() -> None:
    rows = [
        ["Subject", "Max", "Obtained", "Grade"],
        ["Data Structures", "100", "78", "A"],
        ["Operating Systems", "100", "52", "C"],
        ["Computer Networks", "100", "64", "B"],
        ["Mathematics", "100", "88", "A+"],
    ]
    img = _render(rows, "Semester 4 Marks Statement", [60, 640, 820, 1060], noisy=True)
    img.save(OUT / "scanned_semester4.png")
    img.convert("RGB").save(OUT / "scanned_semester4.jpg", quality=85)
    img.convert("RGB").save(OUT / "scanned_semester4.pdf", resolution=200)


def spreadsheets() -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Results"
    ws.append(["Student Report"])
    ws.append([])
    ws.append(["Semester", "Course", "Theory", "Practical", "Credits"])
    ws.append([5, "Computer Networks", 61, 22, 4])
    ws.append([5, "Software Engineering", 70, None, 3])
    ws.append([5, "Compiler Design", 48.5, 18, 4])
    wb.save(OUT / "theory_practical.xlsx")

    with (OUT / "percentages.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Subject", "Percentage", "Sem"])
        w.writerow(["Data Structures", "81%", "3"])
        w.writerow(["Operating Systems", "67", "3"])
        w.writerow(["Database Systems", "", "3"])
        w.writerow(["Data Structures", "74%", "3"])  # repeated subject

    with (OUT / "semicolon_missing_max.csv").open("w", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Course Name", "Marks Obtained", "Grade"])
        w.writerow(["Algorithms", "56", "XQ"])
        w.writerow(["Theory of Computation", "71", "B"])

    (OUT / "plain_report.txt").write_text(
        "Annual Progress Report\n"
        "Semester 6 Backlog Examination May 2026\n"
        "Design and Analysis of Algorithms    38/75    C\n"
        "Artificial Neural Networks Elective  64/100   B\n"
        "Machine Drawing Practical            AB\n"
        "Total                                102/175\n"
    )


def malformed() -> None:
    good = (OUT / "digital_semester3.pdf").read_bytes()
    (OUT / "truncated.pdf").write_bytes(good[:400])
    (OUT / "not_a_pdf.pdf").write_bytes(b"MZ\x90\x00 this is not a pdf")
    (OUT / "png_named_csv.csv").write_bytes((OUT / "scanned_semester4.png").read_bytes())


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    digital_pdf()
    unruled_pdf()
    scanned()
    spreadsheets()
    malformed()
    for p in sorted(OUT.iterdir()):
        print(p.name, p.stat().st_size)
