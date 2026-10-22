"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-22 16:34:15.893337
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "curricula",
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curricula")),
        sa.UniqueConstraint("slug", name=op.f("uq_curricula_slug")),
    )
    op.create_table(
        "grading_scales",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "raw",
                "percentage",
                "letter",
                "grade_point",
                name="grading_scale_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("max_grade_points", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_scales")),
        sa.UniqueConstraint("name", name=op.f("uq_grading_scales_name")),
    )
    op.create_table(
        "source_references",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("authors", sa.String(length=300), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("license", sa.String(length=120), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_references")),
        sa.UniqueConstraint("slug", name=op.f("uq_source_references_slug")),
    )
    op.create_table(
        "students",
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
        sa.UniqueConstraint("email", name=op.f("uq_students_email")),
    )
    op.create_table(
        "topics",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("estimated_study_minutes", sa.Integer(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topics")),
        sa.UniqueConstraint("slug", name=op.f("uq_topics_slug")),
    )
    op.create_table(
        "concepts",
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_name", sa.String(length=200), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("content_version", sa.String(length=40), nullable=False),
        sa.Column(
            "trust_status",
            sa.Enum(
                "draft",
                "imported",
                "verified",
                "retired",
                name="trust_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name=op.f("ck_concepts_difficulty_range")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source_references.id"],
            name=op.f("fk_concepts_source_id_source_references"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_concepts_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
        sa.UniqueConstraint("slug", name=op.f("uq_concepts_slug")),
    )
    op.create_table(
        "conversations",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_conversations_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_conversations_student_id"), ["student_id"], unique=False
        )

    op.create_table(
        "documents",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "uploaded",
                "extracted",
                "confirmed",
                "failed",
                name="document_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("parser_name", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_documents_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("student_id", "sha256", name="student_sha256"),
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_documents_sha256"), ["sha256"], unique=False)

    op.create_table(
        "study_plans",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("formula_version", sa.String(length=40), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_study_plans_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_plans")),
    )
    with op.batch_alter_table("study_plans", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_study_plans_student_id"), ["student_id"], unique=False)

    op.create_table(
        "subjects",
        sa.Column("curriculum_id", sa.String(length=36), nullable=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_id"],
            ["curricula.id"],
            name=op.f("fk_subjects_curriculum_id_curricula"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.UniqueConstraint("slug", name=op.f("uq_subjects_slug")),
    )
    op.create_table(
        "topic_mastery",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column(
            "classification",
            sa.Enum(
                "strong",
                "developing",
                "needs_attention",
                "insufficient_evidence",
                name="mastery_class",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.String(length=40), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_topic_mastery_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_topic_mastery_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("student_id", "topic_id", name=op.f("pk_topic_mastery")),
    )
    op.create_table(
        "assessments",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("exam_name", sa.String(length=200), nullable=True),
        sa.Column(
            "exam_type",
            sa.Enum(
                "regular",
                "supplementary",
                "backlog",
                "internal",
                "unknown",
                name="exam_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("held_on", sa.Date(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_assessments_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_assessments_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
    )
    op.create_table(
        "concept_relationships",
        sa.Column("source_concept_id", sa.String(length=36), nullable=False),
        sa.Column("target_concept_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "requires",
                "related_to",
                "contrasts_with",
                "part_of",
                name="relationship_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "source_concept_id <> target_concept_id",
            name=op.f("ck_concept_relationships_no_self_edge"),
        ),
        sa.ForeignKeyConstraint(
            ["source_concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_relationships_source_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_relationships_target_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_relationships")),
        sa.UniqueConstraint("source_concept_id", "target_concept_id", "kind", name="edge"),
    )
    with op.batch_alter_table("concept_relationships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_concept_relationships_source_concept_id"),
            ["source_concept_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_concept_relationships_target_concept_id"),
            ["target_concept_id"],
            unique=False,
        )

    op.create_table(
        "extracted_records",
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("field_confidence", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_extracted_records_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extracted_records")),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "explanation",
                "procedure",
                "example",
                "misconception",
                "exercise",
                "reference",
                name="knowledge_document_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_version", sa.String(length=40), nullable=False),
        sa.Column(
            "trust_status",
            sa.Enum(
                "draft",
                "imported",
                "verified",
                "retired",
                name="trust_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("origin_path", sa.String(length=500), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_knowledge_documents_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source_references.id"],
            name=op.f("fk_knowledge_documents_source_id_source_references"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("slug", name=op.f("uq_knowledge_documents_slug")),
    )
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_knowledge_documents_concept_id"), ["concept_id"], unique=False
        )

    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "student",
                "tutor",
                name="message_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_messages_conversation_id"), ["conversation_id"], unique=False
        )

    op.create_table(
        "questions",
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=True),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "multiple_choice",
                "short_answer",
                "numeric",
                name="question_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "purpose",
            sa.Enum(
                "diagnostic",
                "practice",
                name="question_purpose",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("style", sa.String(length=20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("content_version", sa.String(length=40), nullable=False),
        sa.Column(
            "trust_status",
            sa.Enum(
                "draft",
                "imported",
                "verified",
                "retired",
                name="trust_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_questions_concept_id_concepts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_questions_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        sa.UniqueConstraint("slug", name=op.f("uq_questions_slug")),
    )
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_questions_concept_id"), ["concept_id"], unique=False)

    op.create_table(
        "study_plan_items",
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("priority_score", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "lesson_completed",
                "skipped",
                name="study_plan_item_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["study_plans.id"],
            name=op.f("fk_study_plan_items_plan_id_study_plans"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_study_plan_items_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_plan_items")),
    )
    op.create_table(
        "subject_topics",
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "importance BETWEEN 1 AND 5", name=op.f("ck_subject_topics_importance_range")
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_subject_topics_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_subject_topics_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("subject_id", "topic_id", name=op.f("pk_subject_topics")),
    )
    op.create_table(
        "assessment_results",
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column(
            "component",
            sa.Enum(
                "theory",
                "lab",
                "combined",
                name="result_component",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "present",
                "absent",
                "withheld",
                "missing",
                name="result_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("marks_obtained", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("max_marks", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("grade", sa.String(length=8), nullable=True),
        sa.Column("grade_points", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("credits", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("grading_scale_id", sa.String(length=36), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("subject_label_as_printed", sa.String(length=200), nullable=True),
        sa.Column("verified_by_student", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number >= 1", name=op.f("ck_assessment_results_attempt_positive")
        ),
        sa.CheckConstraint(
            "marks_obtained IS NULL OR marks_obtained >= 0",
            name=op.f("ck_assessment_results_marks_non_negative"),
        ),
        sa.CheckConstraint(
            "marks_obtained IS NULL OR max_marks IS NULL OR marks_obtained <= max_marks",
            name=op.f("ck_assessment_results_marks_within_max"),
        ),
        sa.CheckConstraint(
            "max_marks IS NULL OR max_marks > 0",
            name=op.f("ck_assessment_results_max_marks_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_results_assessment_id_assessments"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grading_scale_id"],
            ["grading_scales.id"],
            name=op.f("fk_assessment_results_grading_scale_id_grading_scales"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_assessment_results_subject_id_subjects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_results")),
    )
    op.create_table(
        "diagnostic_attempts",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("quiz_session_id", sa.String(length=36), nullable=True),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_diagnostic_attempts_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_diagnostic_attempts_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_diagnostic_attempts_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_diagnostic_attempts")),
    )
    with op.batch_alter_table("diagnostic_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_diagnostic_attempts_quiz_session_id"), ["quiz_session_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_diagnostic_attempts_student_id"), ["student_id"], unique=False
        )

    op.create_table(
        "message_sources",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_document_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("retrieval_score", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.ForeignKeyConstraint(
            ["knowledge_document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_message_sources_knowledge_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_sources_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "message_id", "knowledge_document_id", name=op.f("pk_message_sources")
        ),
    )
    op.create_table(
        "verified_answers",
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_verified_answers_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["source_references.id"],
            name=op.f("fk_verified_answers_source_id_source_references"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verified_answers")),
        sa.UniqueConstraint("question_id", name=op.f("uq_verified_answers_question_id")),
    )
    op.create_table(
        "topic_evidence",
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "subject_score_prior",
                "topic_exam",
                "diagnostic",
                "practice",
                "self_report",
                name="evidence_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("assessment_result_id", sa.String(length=36), nullable=True),
        sa.Column("diagnostic_attempt_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name=op.f("ck_topic_evidence_score_unit"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_result_id"],
            ["assessment_results.id"],
            name=op.f("fk_topic_evidence_assessment_result_id_assessment_results"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["diagnostic_attempt_id"],
            ["diagnostic_attempts.id"],
            name=op.f("fk_topic_evidence_diagnostic_attempt_id_diagnostic_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_topic_evidence_student_id_students"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_topic_evidence_topic_id_topics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_topic_evidence")),
    )
    with op.batch_alter_table("topic_evidence", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_topic_evidence_student_id"), ["student_id"], unique=False
        )

    # ### end Alembic commands ###


def downgrade() -> None:
    with op.batch_alter_table("topic_evidence", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_topic_evidence_student_id"))

    op.drop_table("topic_evidence")
    op.drop_table("verified_answers")
    op.drop_table("message_sources")
    with op.batch_alter_table("diagnostic_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_diagnostic_attempts_student_id"))
        batch_op.drop_index(batch_op.f("ix_diagnostic_attempts_quiz_session_id"))

    op.drop_table("diagnostic_attempts")
    op.drop_table("assessment_results")
    op.drop_table("subject_topics")
    op.drop_table("study_plan_items")
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_questions_concept_id"))

    op.drop_table("questions")
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_conversation_id"))

    op.drop_table("messages")
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_knowledge_documents_concept_id"))

    op.drop_table("knowledge_documents")
    op.drop_table("extracted_records")
    with op.batch_alter_table("concept_relationships", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_concept_relationships_target_concept_id"))
        batch_op.drop_index(batch_op.f("ix_concept_relationships_source_concept_id"))

    op.drop_table("concept_relationships")
    op.drop_table("assessments")
    op.drop_table("topic_mastery")
    op.drop_table("subjects")
    with op.batch_alter_table("study_plans", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_study_plans_student_id"))

    op.drop_table("study_plans")
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_sha256"))

    op.drop_table("documents")
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_conversations_student_id"))

    op.drop_table("conversations")
    op.drop_table("concepts")
    op.drop_table("topics")
    op.drop_table("students")
    op.drop_table("source_references")
    op.drop_table("grading_scales")
    op.drop_table("curricula")
    # ### end Alembic commands ###
