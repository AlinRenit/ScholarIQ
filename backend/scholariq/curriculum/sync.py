"""Load curriculum files into the database (idempotent).

Run:  python -m scholariq.curriculum.sync   (then loads the knowledge base too)

Subjects and topics are upserted by slug. Topic links of curriculum subjects
are replaced to match the file. Custom subjects created during imports are
merged into a curriculum subject when their name matches one of its names or
aliases, so earlier imports gain topic mappings automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from scholariq.curriculum.schema import CurriculumFile, ModuleSpec, normalise_name
from scholariq.db.models import (
    AssessmentResult,
    Curriculum,
    ExamBreakdown,
    Subject,
    SubjectModule,
    SubjectTopic,
    Topic,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    curricula: int = 0
    subjects: int = 0
    topics: int = 0
    modules: int = 0
    merged_custom_subjects: int = 0


def load_files(content_dir: Path) -> list[CurriculumFile]:
    files = sorted((content_dir / "curriculum").glob("*.yaml"))
    return [
        CurriculumFile.model_validate(yaml.safe_load(p.read_text(encoding="utf-8"))) for p in files
    ]


def subject_names(subject: Subject) -> set[str]:
    names = {normalise_name(subject.name), *(normalise_name(a) for a in subject.aliases)}
    if subject.code:
        names.add(normalise_name(subject.code))
    return names


def sync_curricula(session: Session, files: list[CurriculumFile]) -> SyncReport:
    report = SyncReport()
    for cf in files:
        meta = cf.curriculum
        cur = session.scalar(select(Curriculum).where(Curriculum.slug == meta.slug))
        if cur is None:
            cur = Curriculum(slug=meta.slug, name=meta.name, version=meta.version)
            session.add(cur)
        cur.name, cur.version = meta.name, meta.version
        session.flush()
        report.curricula += 1

        for spec in cf.subjects:
            subject = session.scalar(select(Subject).where(Subject.slug == spec.slug))
            if subject is None:
                subject = Subject(slug=spec.slug, name=spec.name, aliases=[], is_custom=False)
                session.add(subject)
            subject.name = spec.name
            subject.curriculum_id = cur.id
            subject.code = spec.codes[0] if spec.codes else None
            subject.aliases = [*spec.aliases, *spec.codes[1:]]
            subject.is_custom = False
            session.flush()
            report.subjects += 1

            session.execute(delete(SubjectTopic).where(SubjectTopic.subject_id == subject.id))
            module_of = _sync_modules(session, subject, spec.modules)
            report.modules += len(spec.modules)
            for position, t in enumerate(spec.topics):
                topic = session.scalar(select(Topic).where(Topic.slug == t.slug))
                if topic is None:
                    topic = Topic(slug=t.slug, name=t.name)
                    session.add(topic)
                    report.topics += 1
                topic.name = t.name
                topic.summary = t.summary
                topic.estimated_study_minutes = t.minutes
                session.flush()
                session.add(
                    SubjectTopic(
                        subject_id=subject.id,
                        topic_id=topic.id,
                        position=position,
                        importance=t.importance,
                        module_id=module_of.get(t.slug),
                    )
                )
        session.flush()
    report.merged_custom_subjects = merge_custom_subjects(session)
    session.commit()
    return report


def _sync_modules(session: Session, subject: Subject, specs: list[ModuleSpec]) -> dict[str, str]:
    """Upsert a subject's modules by slug and drop those no longer in the file.

    Module ids are kept stable so question mappings to a module survive a sync.
    Returns topic slug -> module id.
    """
    existing = {
        m.slug: m
        for m in session.scalars(
            select(SubjectModule).where(SubjectModule.subject_id == subject.id)
        )
    }
    wanted = {m.slug for m in specs}
    for slug, module in existing.items():
        if slug not in wanted:
            session.delete(module)
    # Free the numbers first so renumbering modules cannot hit the unique check.
    for slug, module in existing.items():
        if slug in wanted:
            module.number = 1000 + module.number
    session.flush()
    module_of: dict[str, str] = {}
    for spec in specs:
        found = existing.get(spec.slug)
        module = found or SubjectModule(subject_id=subject.id, slug=spec.slug, number=spec.number)
        session.add(module)
        module.number, module.name = spec.number, spec.name
        session.flush()
        for t in spec.topics:
            module_of[t] = module.id
    return module_of


def merge_custom_subjects(session: Session) -> int:
    """Re-point results from custom subjects to matching curriculum subjects."""
    curriculum = session.scalars(select(Subject).where(Subject.is_custom.is_(False))).all()
    lookup: dict[str, Subject] = {}
    for s in curriculum:
        for n in subject_names(s):
            lookup.setdefault(n, s)
    merged = 0
    for custom in session.scalars(select(Subject).where(Subject.is_custom.is_(True))).all():
        target = lookup.get(normalise_name(custom.name))
        if target is None and custom.code:
            target = lookup.get(normalise_name(custom.code))
        if target is None:
            continue
        session.execute(
            update(AssessmentResult)
            .where(AssessmentResult.subject_id == custom.id)
            .values(subject_id=target.id)
        )
        session.execute(
            update(ExamBreakdown)
            .where(ExamBreakdown.subject_id == custom.id)
            .values(subject_id=target.id)
        )
        session.delete(custom)
        merged += 1
    session.flush()
    return merged


def main() -> None:
    from scholariq.core.config import get_settings
    from scholariq.db.session import get_engine

    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    settings = get_settings()
    files = load_files(settings.content_dir)
    with Session(get_engine()) as session:
        report = sync_curricula(session, files)
    logger.info("curriculum sync: %s", report)

    # Knowledge files reference curriculum topics, so they load second.
    from scholariq.knowledge import sync as knowledge_sync

    knowledge_sync.main()


if __name__ == "__main__":
    main()
