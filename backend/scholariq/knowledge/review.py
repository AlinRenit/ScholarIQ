"""Reviewer helper: show review status, or print the block that marks a concept verified.

    python -m scholariq.knowledge.review                 # status of every concept
    python -m scholariq.knowledge.review SLUG --by NAME  # review block for SLUG

Paste the printed block over the concept's ``review:`` entry. The hash ties the
review to the exact content; editing the concept later voids it.
"""

from __future__ import annotations

import argparse
from datetime import date

from scholariq.core.config import get_settings
from scholariq.knowledge.loader import load_content, trust_of


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("slug", nargs="?")
    parser.add_argument("--by", help="reviewer name")
    args = parser.parse_args(argv)
    content = load_content(get_settings().content_dir)

    if not args.slug:
        for t, c in content.concepts():
            print(f"{trust_of(c).value:<9} {c.slug:<45} {t.relpath}")
        for w in content.warnings:
            print("warning:", w)
        return 0

    match = [(t, c) for t, c in content.concepts() if c.slug == args.slug]
    if not match:
        parser.error(f"unknown concept {args.slug}")
    if not args.by:
        parser.error("--by is required")
    t, c = match[0]
    print(f"# {t.relpath}")
    print("    review:")
    print("      status: verified")
    print(f"      by: {args.by}")
    print(f"      on: {date.today().isoformat()}")
    print(f"      hash: {c.content_hash()[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
