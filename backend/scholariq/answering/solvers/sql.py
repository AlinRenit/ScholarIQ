"""Run a SELECT query against a small built-in practice database.

The database is created fresh in memory for every query, from the fixed
sample below, so nothing a query does can persist or touch real data. SQLite's
authorizer allows only reading tables and calling a list of plain functions:
writes, schema changes, ATTACH, PRAGMA and extension loading are refused. A
progress handler stops runaway queries, and output is capped at 50 rows.
"""

from __future__ import annotations

import re
import sqlite3

from scholariq.answering.solvers.base import Solution, SolverError

MAX_ROWS = 50
MAX_STEPS = 2_000_000

SCHEMA = """
CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT NOT NULL, dept TEXT, year INTEGER);
CREATE TABLE courses (id TEXT PRIMARY KEY, title TEXT NOT NULL, dept TEXT, credits INTEGER);
CREATE TABLE enrollments (student_id INTEGER REFERENCES students(id),
                          course_id TEXT REFERENCES courses(id),
                          marks INTEGER, PRIMARY KEY (student_id, course_id));
INSERT INTO students VALUES (1,'Asha','CSE',2),(2,'Ben','CSE',3),(3,'Chen','ECE',2),
  (4,'Divya','CSE',2),(5,'Emil','ME',1),(6,'Farah','ECE',3);
INSERT INTO courses VALUES ('CS201','Data Structures','CSE',4),('CS202','Database Systems','CSE',4),
  ('CS301','Operating Systems','CSE',3),('EC201','Signals','ECE',4),
  ('MA101','Discrete Mathematics','MATH',3);
INSERT INTO enrollments VALUES (1,'CS201',78),(1,'CS202',85),(1,'MA101',64),(2,'CS201',55),
  (2,'CS301',72),(3,'EC201',81),(3,'MA101',90),(4,'CS201',92),(4,'CS202',NULL),(4,'CS301',67),
  (6,'EC201',58),(6,'MA101',73);
"""

SCHEMA_SUMMARY = (
    "students(id, name, dept, year), courses(id, title, dept, credits), "
    "enrollments(student_id, course_id, marks); Emil (id 5) has no enrollments and one "
    "mark is NULL."
)

_FUNCTIONS = {
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "total",
    "group_concat",
    "abs",
    "round",
    "length",
    "lower",
    "upper",
    "substr",
    "trim",
    "coalesce",
    "ifnull",
    "nullif",
    "cast",
    "like",
    "glob",
    "instr",
    "replace",
    "iif",
}
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _authorizer(
    action: int, arg1: str | None, arg2: str | None, db: str | None, src: str | None
) -> int:
    if action in _ALLOWED_ACTIONS:
        if action == sqlite3.SQLITE_READ and (arg1 or "").startswith("sqlite_"):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def extract(text: str) -> str | None:
    m = re.search(
        r"(?is)\b(with\s+(?:recursive\s+)?\w+(?:\s*\([^)]*\))?\s+as\s*\(.*|select\s.+?\sfrom\s.+)$",
        text.strip(),
    )
    if not m:
        return None
    sql = m.group(1).strip().strip("`").strip()
    return re.sub(r"[;\s?]+$", "", sql)


def run(sql: str) -> tuple[list[str], list[list[str]], bool]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        conn.set_authorizer(_authorizer)
        steps = 0

        def tick() -> int:
            nonlocal steps
            steps += 1
            return 1 if steps * 1000 > MAX_STEPS else 0

        conn.set_progress_handler(tick, 1000)
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
        more = len(rows) > MAX_ROWS
        return cols, [["NULL" if v is None else str(v) for v in r] for r in rows[:MAX_ROWS]], more
    finally:
        conn.close()


class SqlSolver:
    name = "sql-sandbox"
    description = "SELECT queries on a built-in practice database (students, courses, enrollments)"

    def solve(self, text: str) -> Solution | SolverError | None:
        sql = extract(text)
        if sql is None:
            return None
        if ";" in sql:
            return SolverError(
                self.name, "Only one SELECT statement can be run at a time.", "db.sql-select"
            )
        try:
            cols, rows, more = run(sql)
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "not authorized" in msg:
                msg = "only reading the practice tables is allowed"
            elif "interrupted" in msg:
                msg = "the query took too long and was stopped"
            return SolverError(self.name, f"The query could not run: {msg}.", "db.sql-select")
        concept = (
            "db.sql-joins"
            if re.search(r"\bjoin\b", sql, re.I)
            else (
                "db.sql-aggregation"
                if re.search(r"\bgroup\s+by\b|\b(count|sum|avg)\s*\(", sql, re.I)
                else "db.sql-select"
            )
        )
        return Solution(
            self.name,
            "SQL query result",
            f"{len(rows)}{'+' if more else ''} row(s) returned.",
            steps=[f"Ran on the practice database: {SCHEMA_SUMMARY}"],
            columns=cols,
            rows=rows,
            limitations=["Runs against the built-in practice data only, never your own database."]
            + ([f"Only the first {MAX_ROWS} rows are shown."] if more else []),
            concept=concept,
        )
