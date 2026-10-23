"""Read and validate knowledge-base files.

Validation collects every problem it finds instead of stopping at the first, so
an author can fix a file in one pass. Problems that make content unusable
(unknown references, duplicate slugs, prerequisite cycles) are errors; a review
whose hash no longer matches is a warning and the concept is downgraded to
unreviewed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from scholariq.curriculum.sync import load_files as load_curriculum_files
from scholariq.domain.enums import TrustStatus
from scholariq.knowledge.schema import ConceptSpec, SourcesFile, SourceSpec, TopicFile


class ContentError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class LoadedTopic:
    path: Path
    relpath: str
    file: TopicFile


@dataclass
class KnowledgeContent:
    sources: list[SourceSpec]
    topics: list[LoadedTopic]
    warnings: list[str] = field(default_factory=list)

    def concepts(self) -> list[tuple[LoadedTopic, ConceptSpec]]:
        return [(t, c) for t in self.topics for c in t.file.concepts]


def trust_of(concept: ConceptSpec) -> TrustStatus:
    r = concept.review
    if r.status == "retired":
        return TrustStatus.RETIRED
    if r.status == "verified" and r.hash == concept.content_hash()[:12]:
        return TrustStatus.VERIFIED
    # Unreviewed, or reviewed content that has changed since.
    return TrustStatus.IMPORTED


def load_content(content_dir: Path) -> KnowledgeContent:
    problems: list[str] = []
    warnings: list[str] = []

    sources: list[SourceSpec] = []
    sources_path = content_dir / "sources.yaml"
    if sources_path.exists():
        try:
            sources = SourcesFile.model_validate(
                yaml.safe_load(sources_path.read_text(encoding="utf-8"))
            ).sources
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"sources.yaml: {exc}")

    # Which subject each topic belongs to, from the curriculum files.
    topic_subjects: dict[str, set[str]] = {}
    for cf in load_curriculum_files(content_dir):
        for s in cf.subjects:
            for topic_spec in s.topics:
                topic_subjects.setdefault(topic_spec.slug, set()).add(s.slug)

    topics: list[LoadedTopic] = []
    root = content_dir / "knowledge"
    for path in sorted(root.glob("*/*.yaml")) if root.exists() else []:
        rel = path.relative_to(content_dir).as_posix()
        try:
            tf = TopicFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (ValidationError, yaml.YAMLError) as exc:
            problems.append(f"{rel}: {exc}")
            continue
        if tf.topic not in topic_subjects:
            problems.append(f"{rel}: topic {tf.topic!r} is not in any curriculum file")
        elif path.parent.name not in topic_subjects[tf.topic]:
            problems.append(f"{rel}: topic {tf.topic!r} does not belong to {path.parent.name!r}")
        if path.stem != tf.topic:
            problems.append(f"{rel}: file name must be {tf.topic}.yaml")
        topics.append(LoadedTopic(path, rel, tf))

    content = KnowledgeContent(sources, topics, warnings)
    problems += _cross_check(content)
    for t, c in content.concepts():
        if c.review.status == "verified" and trust_of(c) is not TrustStatus.VERIFIED:
            warnings.append(
                f"{t.relpath}: {c.slug} changed after review by {c.review.by}; "
                "it is treated as unreviewed until reviewed again"
            )
    if problems:
        raise ContentError(problems)
    return content


def _cross_check(content: KnowledgeContent) -> list[str]:
    problems: list[str] = []
    source_slugs = {s.slug for s in content.sources}
    if len(source_slugs) != len(content.sources):
        problems.append("sources.yaml: duplicate source slugs")

    concepts: dict[str, ConceptSpec] = {}
    question_slugs: set[str] = set()
    for t, c in content.concepts():
        if c.slug in concepts:
            problems.append(f"{t.relpath}: duplicate concept slug {c.slug}")
        concepts[c.slug] = c
        for q in c.questions:
            if q.slug in question_slugs:
                problems.append(f"{t.relpath}: duplicate question slug {q.slug}")
            question_slugs.add(q.slug)
        titles = [(d.kind, d.title) for d in c.documents]
        if len(titles) != len(set(titles)):
            problems.append(f"{t.relpath}: {c.slug} has two documents with the same title")

    for t, c in content.concepts():
        for kind in ("requires", "related", "contrasts", "part_of"):
            for target in getattr(c, kind):
                if target not in concepts:
                    problems.append(f"{t.relpath}: {c.slug} {kind} unknown concept {target}")
                elif target == c.slug:
                    problems.append(f"{t.relpath}: {c.slug} {kind} itself")
        for s in c.further_reading:
            if s not in source_slugs:
                problems.append(f"{t.relpath}: {c.slug} cites unknown source {s}")

    cycle = _find_cycle({slug: c.requires for slug, c in concepts.items()})
    if cycle:
        problems.append("prerequisite cycle: " + " -> ".join(cycle))
    return problems


def _find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle in the ``requires`` graph, or None."""
    state: dict[str, int] = {}  # 1 = on stack, 2 = done
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in edges.get(node, []):
            if state.get(nxt) == 1:
                return [*stack[stack.index(nxt) :], nxt]
            if nxt not in state and (found := visit(nxt)):
                return found
        stack.pop()
        state[node] = 2
        return None

    for node in sorted(edges):
        if node not in state and (found := visit(node)):
            return found
    return None
