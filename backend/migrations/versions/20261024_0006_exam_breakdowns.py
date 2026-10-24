"""exam breakdowns and subject modules

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-24 17:00:00.000000

Adds per-subject modules, exam breakdowns (question-level marks mapped to
topics or modules) and the "exam_breakdown" evidence kind. Purely additive:
existing rows are untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_KINDS = ("subject_score_prior", "topic_exam", "diagnostic", "practice", "self_report")
NEW_KINDS = (*OLD_KINDS, "exam_breakdown")


def _kind_check(kinds: tuple[str, ...]) -> sa.TextClause:
    return sa.text("kind IN (" + ", ".join(f"'{k}'" for k in kinds) + ")")


def upgrade() -> None:
    op.create_table(
        "subject_modules",
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint("number >= 1", name=op.f("ck_subject_modules_module_number_positive")),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_subject_modules_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subject_modules")),
        sa.UniqueConstraint("subject_id", "number", name="subject_module_number"),
        sa.UniqueConstraint("subject_id", "slug", name="subject_module_slug"),
    )
    op.create_table(
        "exam_breakdowns",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=True),
        sa.Column("declared_total", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "confirmed",
                name="breakdown_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("choice_rules", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "declared_total IS NULL OR declared_total > 0",
            name=op.f("ck_exam_breakdowns_total_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_exam_breakdowns_assessment_id_assessments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_exam_breakdowns_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_exam_breakdowns_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_exam_breakdowns_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_breakdowns")),
        sa.UniqueConstraint("assessment_id", "subject_id", name="assessment_subject"),
    )
    with op.batch_alter_table("exam_breakdowns", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exam_breakdowns_student_id"), ["student_id"], unique=False
        )

    op.create_table(
        "exam_questions",
        sa.Column("breakdown_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("section", sa.String(length=80), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("max_marks", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("marks_obtained", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column(
            "attempt_status",
            sa.Enum(
                "attempted",
                "not_attempted",
                "unknown",
                name="attempt_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("is_optional", sa.Boolean(), nullable=False),
        sa.Column("choice_group", sa.String(length=80), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("parse_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("paper_module", sa.String(length=40), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "marks_obtained IS NULL OR marks_obtained >= 0",
            name=op.f("ck_exam_questions_marks_non_negative"),
        ),
        sa.CheckConstraint(
            "marks_obtained IS NULL OR max_marks IS NULL OR marks_obtained <= max_marks",
            name=op.f("ck_exam_questions_marks_within_max"),
        ),
        sa.CheckConstraint(
            "max_marks IS NULL OR max_marks > 0", name=op.f("ck_exam_questions_max_marks_positive")
        ),
        sa.CheckConstraint(
            "parse_confidence IS NULL OR (parse_confidence >= 0 AND parse_confidence <= 1)",
            name=op.f("ck_exam_questions_confidence_unit"),
        ),
        sa.ForeignKeyConstraint(
            ["breakdown_id"],
            ["exam_breakdowns.id"],
            name=op.f("fk_exam_questions_breakdown_id_exam_breakdowns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_questions")),
    )
    with op.batch_alter_table("exam_questions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exam_questions_breakdown_id"), ["breakdown_id"], unique=False
        )

    op.create_table(
        "exam_question_mappings",
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=True),
        sa.Column("module_id", sa.String(length=36), nullable=True),
        sa.Column("share", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "(topic_id IS NULL AND module_id IS NOT NULL) OR (topic_id IS NOT NULL AND module_id IS NULL)",
            name=op.f("ck_exam_question_mappings_topic_or_module"),
        ),
        sa.CheckConstraint(
            "share > 0 AND share <= 1", name=op.f("ck_exam_question_mappings_share_unit")
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["subject_modules.id"],
            name=op.f("fk_exam_question_mappings_module_id_subject_modules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["exam_questions.id"],
            name=op.f("fk_exam_question_mappings_question_id_exam_questions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_exam_question_mappings_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_question_mappings")),
        sa.UniqueConstraint("question_id", "module_id", name="question_module"),
        sa.UniqueConstraint("question_id", "topic_id", name="question_topic"),
    )
    with op.batch_alter_table("exam_question_mappings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exam_question_mappings_question_id"), ["question_id"], unique=False
        )

    with op.batch_alter_table("subject_topics", schema=None) as batch_op:
        batch_op.add_column(sa.Column("module_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_subject_topics_module_id_subject_modules"),
            "subject_modules",
            ["module_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("topic_evidence", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exam_breakdown_id", sa.String(length=36), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_topic_evidence_exam_breakdown_id"), ["exam_breakdown_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_topic_evidence_exam_breakdown_id_exam_breakdowns"),
            "exam_breakdowns",
            ["exam_breakdown_id"],
            ["id"],
            ondelete="CASCADE",
        )
        # Enums are VARCHAR + CHECK; widen the check for the new evidence kind.
        batch_op.drop_constraint(batch_op.f("ck_topic_evidence_evidence_kind"), type_="check")
        batch_op.create_check_constraint(
            batch_op.f("ck_topic_evidence_evidence_kind"), _kind_check(NEW_KINDS)
        )


def downgrade() -> None:
    op.execute("DELETE FROM topic_evidence WHERE kind = 'exam_breakdown'")
    with op.batch_alter_table("topic_evidence", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_topic_evidence_evidence_kind"), type_="check")
        batch_op.create_check_constraint(
            batch_op.f("ck_topic_evidence_evidence_kind"), _kind_check(OLD_KINDS)
        )
        batch_op.drop_constraint(
            batch_op.f("fk_topic_evidence_exam_breakdown_id_exam_breakdowns"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_topic_evidence_exam_breakdown_id"))
        batch_op.drop_column("exam_breakdown_id")

    with op.batch_alter_table("subject_topics", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_subject_topics_module_id_subject_modules"), type_="foreignkey"
        )
        batch_op.drop_column("module_id")

    with op.batch_alter_table("exam_question_mappings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exam_question_mappings_question_id"))

    op.drop_table("exam_question_mappings")
    with op.batch_alter_table("exam_questions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exam_questions_breakdown_id"))

    op.drop_table("exam_questions")
    with op.batch_alter_table("exam_breakdowns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exam_breakdowns_student_id"))

    op.drop_table("exam_breakdowns")
    op.drop_table("subject_modules")
