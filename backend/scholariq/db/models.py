"""Persistence model.

Groups:
  * Students and their documents, assessments and results.
  * Curriculum: subjects and topics, with configurable subject-to-topic mapping.
  * Knowledge base: concepts, relationships, documents, sources, questions.
  * Learner model: diagnostic attempts, topic evidence, derived mastery.
  * Study plans and tutoring conversations.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scholariq.db.base import Base, IdMixin, TimestampMixin, utcnow
from scholariq.domain.enums import (
    DocumentStatus,
    EvidenceKind,
    ExamType,
    GradingScaleKind,
    KnowledgeDocumentKind,
    MasteryClass,
    MessageRole,
    QuestionKind,
    QuestionPurpose,
    RelationshipKind,
    ResultComponent,
    ResultStatus,
    StudyPlanItemStatus,
    TrustStatus,
)


def _enum(cls: type[StrEnum], name: str) -> Enum:
    # Stored as VARCHAR + CHECK so SQLite and PostgreSQL behave the same.
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


FK = String(36)
MARKS = Numeric(8, 2)

# --------------------------------------------------------------------------- #
# Students, documents and assessments
# --------------------------------------------------------------------------- #


class Student(IdMixin, TimestampMixin, Base):
    __tablename__ = "students"

    display_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    goals: Mapped[list[str]] = mapped_column(JSON, default=list)

    documents: Mapped[list[Document]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    student_id: Mapped[str] = mapped_column(FK, ForeignKey("students.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(String(255))
    # Server-generated name inside the upload dir; never derived from user input.
    storage_key: Mapped[str | None] = mapped_column(String(80))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), default=DocumentStatus.UPLOADED
    )
    parser_name: Mapped[str | None] = mapped_column(String(64))
    # Document-level interpretation: source kind, detected context, grades seen,
    # and warnings shown on the review screen.
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    retain_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship(back_populates="documents")
    extracted_records: Mapped[list[ExtractedRecord]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("student_id", "sha256", name="student_sha256"),)


class ExtractedRecord(IdMixin, TimestampMixin, Base):
    """One candidate result row awaiting student review. Not academic truth."""

    __tablename__ = "extracted_records"

    document_id: Mapped[str] = mapped_column(FK, ForeignKey("documents.id", ondelete="CASCADE"))
    row_index: Mapped[int] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    # Field name -> extracted value / per-field confidence (0..1, heuristic).
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped[Document] = relationship(back_populates="extracted_records")


class GradingScale(IdMixin, TimestampMixin, Base):
    __tablename__ = "grading_scales"

    # Null for built-in templates; set for scales a student defined.
    student_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    # Template key for built-in scales, e.g. "ugc_cbcs_10".
    template_key: Mapped[str | None] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[GradingScaleKind] = mapped_column(_enum(GradingScaleKind, "grading_scale_kind"))
    # e.g. {"O": {"points": 10, "min_pct": 90}, ...} for letter scales.
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    max_grade_points: Mapped[Decimal | None] = mapped_column(MARKS)
    # Unverified scales are never used to convert between grades and percentages.
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Assessment(IdMixin, TimestampMixin, Base):
    """An examination sitting, e.g. 'Semester 3 regular, Nov 2025'."""

    __tablename__ = "assessments"

    student_id: Mapped[str] = mapped_column(FK, ForeignKey("students.id", ondelete="CASCADE"))
    document_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("documents.id", ondelete="SET NULL")
    )
    semester: Mapped[int | None] = mapped_column(Integer)
    exam_name: Mapped[str | None] = mapped_column(String(200))
    exam_type: Mapped[ExamType] = mapped_column(
        _enum(ExamType, "exam_type"), default=ExamType.UNKNOWN
    )
    held_on: Mapped[date | None] = mapped_column(Date)

    student: Mapped[Student] = relationship(back_populates="assessments")
    results: Mapped[list[AssessmentResult]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class AssessmentResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "assessment_results"

    assessment_id: Mapped[str] = mapped_column(FK, ForeignKey("assessments.id", ondelete="CASCADE"))
    subject_id: Mapped[str] = mapped_column(FK, ForeignKey("subjects.id", ondelete="RESTRICT"))
    component: Mapped[ResultComponent] = mapped_column(
        _enum(ResultComponent, "result_component"), default=ResultComponent.COMBINED
    )
    status: Mapped[ResultStatus] = mapped_column(
        _enum(ResultStatus, "result_status"), default=ResultStatus.PRESENT
    )
    # Null means unknown. Never substitute zero for a missing value.
    marks_obtained: Mapped[Decimal | None] = mapped_column(MARKS)
    max_marks: Mapped[Decimal | None] = mapped_column(MARKS)
    grade: Mapped[str | None] = mapped_column(String(8))
    grade_points: Mapped[Decimal | None] = mapped_column(MARKS)
    credits: Mapped[Decimal | None] = mapped_column(MARKS)
    grading_scale_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("grading_scales.id", ondelete="SET NULL")
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    subject_label_as_printed: Mapped[str | None] = mapped_column(String(200))
    verified_by_student: Mapped[bool] = mapped_column(Boolean, default=False)

    assessment: Mapped[Assessment] = relationship(back_populates="results")
    subject: Mapped[Subject] = relationship()

    __table_args__ = (
        CheckConstraint("marks_obtained IS NULL OR marks_obtained >= 0", name="marks_non_negative"),
        CheckConstraint("max_marks IS NULL OR max_marks > 0", name="max_marks_positive"),
        CheckConstraint(
            "marks_obtained IS NULL OR max_marks IS NULL OR marks_obtained <= max_marks",
            name="marks_within_max",
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_positive"),
    )


# --------------------------------------------------------------------------- #
# Curriculum
# --------------------------------------------------------------------------- #


class Curriculum(IdMixin, TimestampMixin, Base):
    __tablename__ = "curricula"

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(40))

    subjects: Mapped[list[Subject]] = relationship(back_populates="curriculum")


class Subject(IdMixin, TimestampMixin, Base):
    __tablename__ = "subjects"

    curriculum_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("curricula.id", ondelete="SET NULL")
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(40))
    # Alternative printed names used to match marksheet rows ("DBMS", "Database Systems").
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    # True for subjects a student created that are not in a seeded curriculum.
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)

    curriculum: Mapped[Curriculum | None] = relationship(back_populates="subjects")
    topic_links: Mapped[list[SubjectTopic]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )


class Topic(IdMixin, TimestampMixin, Base):
    __tablename__ = "topics"

    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    estimated_study_minutes: Mapped[int | None] = mapped_column(Integer)

    concepts: Mapped[list[Concept]] = relationship(back_populates="topic")


class SubjectTopic(Base):
    """Configurable many-to-many mapping; a topic can belong to several subjects."""

    __tablename__ = "subject_topics"

    subject_id: Mapped[str] = mapped_column(
        FK, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(
        FK, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Curriculum-supplied importance, 1 (minor) to 5 (core). Used in plan scoring.
    importance: Mapped[int] = mapped_column(Integer, default=3)

    subject: Mapped[Subject] = relationship(back_populates="topic_links")
    topic: Mapped[Topic] = relationship()

    __table_args__ = (CheckConstraint("importance BETWEEN 1 AND 5", name="importance_range"),)


# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #


class SourceReference(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_references"

    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    authors: Mapped[str | None] = mapped_column(String(300))
    citation: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(120))


class Concept(IdMixin, TimestampMixin, Base):
    __tablename__ = "concepts"

    # Stable identifier from the content files, e.g. "dbms.normalization.3nf".
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    topic_id: Mapped[str] = mapped_column(FK, ForeignKey("topics.id", ondelete="CASCADE"))
    canonical_name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    definition: Mapped[str] = mapped_column(Text)
    # Structured attributes used by the comparison handler, e.g. {"ordering": "LIFO"}.
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    content_version: Mapped[str] = mapped_column(String(40))
    trust_status: Mapped[TrustStatus] = mapped_column(
        _enum(TrustStatus, "trust_status"), default=TrustStatus.DRAFT
    )
    source_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("source_references.id", ondelete="SET NULL")
    )

    topic: Mapped[Topic] = relationship(back_populates="concepts")
    documents: Mapped[list[KnowledgeDocument]] = relationship(
        back_populates="concept", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("difficulty BETWEEN 1 AND 5", name="difficulty_range"),)


class ConceptRelationship(IdMixin, Base):
    __tablename__ = "concept_relationships"

    source_concept_id: Mapped[str] = mapped_column(
        FK, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    target_concept_id: Mapped[str] = mapped_column(
        FK, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[RelationshipKind] = mapped_column(_enum(RelationshipKind, "relationship_kind"))

    __table_args__ = (
        UniqueConstraint("source_concept_id", "target_concept_id", "kind", name="edge"),
        CheckConstraint("source_concept_id <> target_concept_id", name="no_self_edge"),
    )


class KnowledgeDocument(IdMixin, TimestampMixin, Base):
    """A retrievable passage: explanation, procedure, worked example, etc."""

    __tablename__ = "knowledge_documents"

    slug: Mapped[str] = mapped_column(String(200), unique=True)
    concept_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[KnowledgeDocumentKind] = mapped_column(
        _enum(KnowledgeDocumentKind, "knowledge_document_kind")
    )
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    # Ordered steps for procedures and worked examples.
    steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    depth: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    content_version: Mapped[str] = mapped_column(String(40))
    trust_status: Mapped[TrustStatus] = mapped_column(
        _enum(TrustStatus, "trust_status"), default=TrustStatus.DRAFT
    )
    source_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("source_references.id", ondelete="SET NULL")
    )
    origin_path: Mapped[str | None] = mapped_column(String(500))

    concept: Mapped[Concept | None] = relationship(back_populates="documents")


class Question(IdMixin, TimestampMixin, Base):
    __tablename__ = "questions"

    slug: Mapped[str] = mapped_column(String(200), unique=True)
    concept_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str] = mapped_column(FK, ForeignKey("topics.id", ondelete="CASCADE"))
    kind: Mapped[QuestionKind] = mapped_column(_enum(QuestionKind, "question_kind"))
    purpose: Mapped[QuestionPurpose] = mapped_column(_enum(QuestionPurpose, "question_purpose"))
    # "conceptual" or "application".
    style: Mapped[str] = mapped_column(String(20), default="conceptual")
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    content_version: Mapped[str] = mapped_column(String(40))
    trust_status: Mapped[TrustStatus] = mapped_column(
        _enum(TrustStatus, "trust_status"), default=TrustStatus.DRAFT
    )

    answer: Mapped[VerifiedAnswer | None] = relationship(
        back_populates="question", cascade="all, delete-orphan", uselist=False
    )


class VerifiedAnswer(IdMixin, TimestampMixin, Base):
    __tablename__ = "verified_answers"

    question_id: Mapped[str] = mapped_column(
        FK, ForeignKey("questions.id", ondelete="CASCADE"), unique=True
    )
    # {"option_index": 2} / {"value": 12.5, "tolerance": 0.01} / {"accepted": [...]}.
    answer: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("source_references.id", ondelete="SET NULL")
    )

    question: Mapped[Question] = relationship(back_populates="answer")


# --------------------------------------------------------------------------- #
# Learner model
# --------------------------------------------------------------------------- #


class DiagnosticAttempt(IdMixin, Base):
    __tablename__ = "diagnostic_attempts"

    student_id: Mapped[str] = mapped_column(
        FK, ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(FK, ForeignKey("questions.id", ondelete="CASCADE"))
    topic_id: Mapped[str] = mapped_column(FK, ForeignKey("topics.id", ondelete="CASCADE"))
    quiz_session_id: Mapped[str | None] = mapped_column(String(36), index=True)
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TopicEvidence(IdMixin, Base):
    """One observation about a student and a topic, with where it came from."""

    __tablename__ = "topic_evidence"

    student_id: Mapped[str] = mapped_column(
        FK, ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str] = mapped_column(FK, ForeignKey("topics.id", ondelete="CASCADE"))
    kind: Mapped[EvidenceKind] = mapped_column(_enum(EvidenceKind, "evidence_kind"))
    # Normalised score in [0, 1] (e.g. fraction correct). Null for qualitative evidence.
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    # Number of observations behind the score (e.g. questions answered).
    sample_size: Mapped[int] = mapped_column(Integer, default=1)
    assessment_result_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("assessment_results.id", ondelete="CASCADE")
    )
    diagnostic_attempt_id: Mapped[str | None] = mapped_column(
        FK, ForeignKey("diagnostic_attempts.id", ondelete="CASCADE")
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="score_unit"),
    )


class TopicMastery(Base):
    """Derived classification. Recomputable from TopicEvidence at any time."""

    __tablename__ = "topic_mastery"

    student_id: Mapped[str] = mapped_column(
        FK, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(
        FK, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    classification: Mapped[MasteryClass] = mapped_column(_enum(MasteryClass, "mastery_class"))
    # Human-readable reasons and the evidence ids used, for display and audit.
    rationale: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rule_version: Mapped[str] = mapped_column(String(40))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- #
# Study plans and conversations
# --------------------------------------------------------------------------- #


class StudyPlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "study_plans"

    student_id: Mapped[str] = mapped_column(
        FK, ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    formula_version: Mapped[str] = mapped_column(String(40))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    items: Mapped[list[StudyPlanItem]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="StudyPlanItem.position"
    )


class StudyPlanItem(IdMixin, Base):
    __tablename__ = "study_plan_items"

    plan_id: Mapped[str] = mapped_column(FK, ForeignKey("study_plans.id", ondelete="CASCADE"))
    topic_id: Mapped[str] = mapped_column(FK, ForeignKey("topics.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    # Each term of the priority formula, so the UI can explain the ranking.
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[StudyPlanItemStatus] = mapped_column(
        _enum(StudyPlanItemStatus, "study_plan_item_status"),
        default=StudyPlanItemStatus.PENDING,
    )

    plan: Mapped[StudyPlan] = relationship(back_populates="items")


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    student_id: Mapped[str] = mapped_column(
        FK, ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(200))

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        FK, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"))
    text: Mapped[str] = mapped_column(Text)
    # Tutor messages: handler used, parsed intent, resolved concepts, evidence
    # status and answer sections, so follow-ups can refer back to them.
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    sources: Mapped[list[MessageSource]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class MessageSource(Base):
    """Citation from a tutor message to the knowledge documents it used."""

    __tablename__ = "message_sources"

    message_id: Mapped[str] = mapped_column(
        FK, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    knowledge_document_id: Mapped[str] = mapped_column(
        FK, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer)
    retrieval_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    message: Mapped[Message] = relationship(back_populates="sources")
