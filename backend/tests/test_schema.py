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


def test_exam_breakdown_migration_keeps_existing_rows(database_url: str, engine: Engine) -> None:
    """Upgrading a database that already has evidence (0005 -> head) keeps it,
    and the widened evidence-kind check accepts exam-breakdown evidence."""
    from sqlalchemy import text

    cfg = alembic_config(database_url)
    command.downgrade(cfg, "0005")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO students (id, display_name, session_version, goals, "
                "created_at) VALUES ('s1', 'A', 0, '[]', CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO topics (id, slug, name, created_at) "
                "VALUES ('t1', 'x.t', 'T', CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(text("INSERT INTO topic_evidence (id, student_id, topic_id, kind, score, "
                          "sample_size, details, observed_at) VALUES ('e1', 's1', 't1', "
                          "'diagnostic', 0.5, 5, '{}', CURRENT_TIMESTAMP)"))  # fmt: skip
    command.upgrade(cfg, "head")
    with Session(engine) as s:
        old = s.get(TopicEvidence, "e1")
        assert old is not None and old.kind is EvidenceKind.DIAGNOSTIC
        assert old.exam_breakdown_id is None
        s.add(TopicEvidence(student_id="s1", topic_id="t1", kind=EvidenceKind.EXAM_BREAKDOWN,
                            score=Decimal("0.4"), sample_size=2))  # fmt: skip
        s.commit()
    # Downgrading drops exam-breakdown evidence but keeps everything else.
    command.downgrade(cfg, "0005")
    with engine.connect() as conn:
        kinds = [r[0] for r in conn.execute(text("SELECT kind FROM topic_evidence"))]
    assert kinds == ["diagnostic"]
    command.upgrade(cfg, "head")


def test_exam_question_constraints(engine: Engine) -> None:
    from scholariq.db.models import ExamBreakdown, ExamQuestion, ExamQuestionMapping

    with Session(engine) as s:
        student = Student(display_name="A")
        subject = Subject(slug="ds", name="DS")
        s.add_all([student, subject])
        s.flush()
        b = ExamBreakdown(student_id=student.id, subject_id=subject.id, title="T")
        s.add(b)
        s.flush()
        q = ExamQuestion(breakdown_id=b.id, position=0, label="1", max_marks=Decimal(5))
        s.add(q)
        s.commit()
        for bad in (
            ExamQuestion(breakdown_id=b.id, position=1, label="2", max_marks=Decimal(0)),
            ExamQuestion(
                breakdown_id=b.id,
                position=1,
                label="2",
                max_marks=Decimal(5),
                marks_obtained=Decimal(6),
            ),  # fmt: skip
            ExamQuestion(breakdown_id=b.id, position=1, label="2", marks_obtained=Decimal(-1)),
            ExamQuestionMapping(question_id=q.id, share=Decimal(1)),  # neither topic nor module
        ):
            s.add(bad)
            with pytest.raises(IntegrityError):
                s.commit()
            s.rollback()
        # Deleting the student removes breakdowns and questions.
        s.delete(s.get(Student, student.id))
        s.commit()
        assert s.query(ExamQuestion).count() == 0
