from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from scholariq.core.config import Settings
from scholariq.curriculum.matching import match_subject
from scholariq.curriculum.schema import CurriculumFile
from scholariq.curriculum.sync import load_files, sync_curricula
from scholariq.db.models import (
    Assessment,
    AssessmentResult,
    Student,
    Subject,
    SubjectTopic,
    Topic,
)


def counts(session: Session) -> tuple[int, int, int]:
    return (
        session.scalar(select(func.count(Subject.id))) or 0,
        session.scalar(select(func.count(Topic.id))) or 0,
        session.scalar(select(func.count()).select_from(SubjectTopic)) or 0,
    )


def test_seed_curriculum_is_valid_and_complete(settings: Settings) -> None:
    files = load_files(settings.content_dir)
    assert len(files) == 1
    names = {s.name for s in files[0].subjects}
    assert names == {
        "Data Structures",
        "Design and Analysis of Algorithms",
        "Operating Systems",
        "Database Management Systems",
        "Computer Networks",
        "Discrete Mathematics",
    }
    dbms = next(s for s in files[0].subjects if s.slug == "dbms")
    assert [t.name for t in dbms.topics][:4] == [
        "Relational model", "SQL", "Functional dependencies", "Normalization",
    ]  # fmt: skip


def test_sync_is_idempotent(settings: Settings, engine: Engine) -> None:
    files = load_files(settings.content_dir)
    with Session(engine) as s:
        sync_curricula(s, files)
        first = counts(s)
        sync_curricula(s, files)
        assert counts(s) == first
    # Topics shared by two subjects exist once.
    assert first[1] < first[2]


def test_conflicting_topic_names_rejected() -> None:
    data = {
        "curriculum": {"slug": "x", "name": "X", "version": "1"},
        "subjects": [
            {"slug": "a", "name": "A", "topics": [{"slug": "t", "name": "One"}]},
            {"slug": "b", "name": "B", "topics": [{"slug": "t", "name": "Two"}]},
        ],
    }
    with pytest.raises(ValidationError, match="two different names"):
        CurriculumFile.model_validate(data)


def test_custom_subjects_merged_on_sync(settings: Settings, engine: Engine) -> None:
    with Session(engine) as s:
        student = Student(display_name="A")
        custom = Subject(slug="custom-dbms", name="D.B.M.S", aliases=[], is_custom=True)
        assessment = Assessment(student=student)
        s.add_all([student, custom, assessment])
        s.flush()
        s.add(AssessmentResult(assessment=assessment, subject_id=custom.id, grade="A"))
        s.commit()
        report = sync_curricula(s, load_files(settings.content_dir))
        assert report.merged_custom_subjects == 1
        result = s.scalars(select(AssessmentResult)).one()
        assert s.get(Subject, result.subject_id).slug == "dbms"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("name", "code", "expected"),
    [
        ("Database Management Systems", None, "dbms"),
        ("DBMS", None, "dbms"),
        ("Database Systems", None, "dbms"),
        ("Operating System", None, "operating-systems"),
        ("Data Structures Lab", None, "data-structures"),
        ("Opearting Systems", None, "operating-systems"),  # typo
        ("Something Else", "CS303", "dbms"),  # code wins
        ("Design & Analysis of Algorithms", None, "algorithms"),
        ("Discrete Maths", None, "discrete-mathematics"),
    ],
)
def test_subject_matching(
    settings: Settings, engine: Engine, name: str, code: str | None, expected: str
) -> None:
    with Session(engine) as s:
        sync_curricula(s, load_files(settings.content_dir))
        found = match_subject(s.scalars(select(Subject)).all(), name, code)
        assert found is not None and found.slug == expected


@pytest.mark.parametrize("name", ["Compiler Design", "Database Systems II", "Engineering Physics"])
def test_no_false_subject_matches(settings: Settings, engine: Engine, name: str) -> None:
    with Session(engine) as s:
        sync_curricula(s, load_files(settings.content_dir))
        assert match_subject(s.scalars(select(Subject)).all(), name, None) is None


def test_policy_override_file(settings: Settings, tmp_path: Path) -> None:
    from scholariq.analytics.policy import load_policy

    (settings.content_dir / "policy.yaml").write_text(
        "version: policy/custom\ntopics:\n  min_direct_observations: 8\n"
    )
    p = load_policy(settings.content_dir)
    assert p.version == "policy/custom"
    assert p.topics.min_direct_observations == 8
    assert p.topics.strong_at == 0.75  # unspecified values keep defaults
