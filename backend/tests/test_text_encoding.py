"""Text files are read and written as UTF-8 on every platform.

Without ``encoding=`` Python uses the locale's encoding, which on Windows is
usually cp1252, and the content files (which contain characters such as "×"
and "≤") then fail to load.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_text_io_names_its_encoding() -> None:
    missing = []
    for folder in ("scholariq", "benchmarks"):
        for path in sorted((BACKEND / folder).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("read_text", "write_text")
                    and not any(k.arg == "encoding" for k in node.keywords)
                ):
                    missing.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert missing == [], "add encoding='utf-8' at: " + ", ".join(missing)
