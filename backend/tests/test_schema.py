from __future__ import annotations

import os
from decimal import Decimal

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scholariq.db.base import Base
from scholariq.db.models import (
    Assessment,
    AssessmentResult,
    Student,
    Subject,
    Topic,
    TopicEvidence,
)
from scholariq.domain.enums import EvidenceKind, ResultStatus
from tests.conftest import alembic_config


def test_migrations_match_models(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_upgrade_downgrade_roundtrip(database_url: str, engine: Engine) -> None:
    cfg = alembic_config(database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert "assessment_results" in inspect(engine).get_table_names()


@pytest.mark.skipif(
    not os.environ.get("SCHOLARIQ_TEST_POSTGRES_URL"), reason="PostgreSQL not configured"
)
def test_postgres_roundtrip() -> None:
    cfg = alembic_config(os.environ["SCHOLARIQ_TEST_POSTGRES_URL"])
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")


def _result_fixture(session: Session) -> tuple[Assessment, Subject]:
    student = Student(display_name="Test Student")
    subject = Subject(slug="dbms", name="Database Management Systems")
    assessment = Assessment(student=student, semester=3)
    session.add_all([student, subject, assessment])
    session.flush()
    return assessment, subject


def test_missing_marks_are_stored_as_null_not_zero(engine: Engine) -> None:
    with Session(engine) as s:
        assessment, subject = _result_fixture(s)
        r = AssessmentResult(
            assessment=assessment, subject_id=subject.id, status=ResultStatus.MISSING
        )
        s.add(r)
        s.commit()
        s.refresh(r)
        assert r.marks_obtained is None
        assert r.max_marks is None


@pytest.mark.parametrize(
    ("obtained", "maximum"),
    [(Decimal("-1"), Decimal("100")), (Decimal("101"), Decimal("100")), (None, Decimal("0"))],
)
def test_invalid_marks_rejected(engine: Engine, obtained: Decimal | None, maximum: Decimal) -> None:
    with Session(engine) as s:
        assessment, subject = _result_fixture(s)
        s.add(
            AssessmentResult(
                assessment=assessment,
                subject_id=subject.id,
                marks_obtained=obtained,
                max_marks=maximum,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_evidence_score_must_be_unit_interval(engine: Engine) -> None:
    with Session(engine) as s:
        student = Student(display_name="A")
        topic = Topic(slug="dbms.normalization", name="Normalization")
        s.add_all([student, topic])
        s.flush()
        s.add(
            TopicEvidence(
                student_id=student.id,
                topic_id=topic.id,
                kind=EvidenceKind.DIAGNOSTIC,
                score=Decimal("1.5"),
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_deleting_student_cascades(engine: Engine) -> None:
    with Session(engine) as s:
        assessment, subject = _result_fixture(s)
        s.add(
            AssessmentResult(
                assessment=assessment,
                subject_id=subject.id,
                marks_obtained=Decimal("40"),
                max_marks=Decimal("50"),
            )
        )
        s.commit()
        s.delete(assessment.student)
        s.commit()
        assert s.query(AssessmentResult).count() == 0
        assert s.query(Assessment).count() == 0
        # Curriculum data is not student data and survives.
        assert s.query(Subject).count() == 1
