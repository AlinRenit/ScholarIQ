"""Enumerations shared by the persistence layer, services and API."""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class ExamType(StrEnum):
    REGULAR = "regular"
    SUPPLEMENTARY = "supplementary"
    BACKLOG = "backlog"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class ResultComponent(StrEnum):
    THEORY = "theory"
    LAB = "lab"
    COMBINED = "combined"


class ResultStatus(StrEnum):
    # A missing score is recorded as MISSING, never as zero.
    PRESENT = "present"
    ABSENT = "absent"
    WITHHELD = "withheld"
    MISSING = "missing"


class GradingScaleKind(StrEnum):
    RAW = "raw"
    PERCENTAGE = "percentage"
    LETTER = "letter"
    GRADE_POINT = "grade_point"


class TrustStatus(StrEnum):
    # Only VERIFIED content may be cited as a supported answer.
    DRAFT = "draft"
    IMPORTED = "imported"
    VERIFIED = "verified"
    RETIRED = "retired"


class RelationshipKind(StrEnum):
    REQUIRES = "requires"
    RELATED_TO = "related_to"
    CONTRASTS_WITH = "contrasts_with"
    PART_OF = "part_of"


class KnowledgeDocumentKind(StrEnum):
    EXPLANATION = "explanation"
    PROCEDURE = "procedure"
    EXAMPLE = "example"
    MISCONCEPTION = "misconception"
    EXERCISE = "exercise"
    REFERENCE = "reference"


class QuestionKind(StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    NUMERIC = "numeric"


class QuestionPurpose(StrEnum):
    DIAGNOSTIC = "diagnostic"
    PRACTICE = "practice"


class EvidenceKind(StrEnum):
    # Subject-level marks are only a weak prior for every topic in the subject.
    SUBJECT_SCORE_PRIOR = "subject_score_prior"
    TOPIC_EXAM = "topic_exam"
    DIAGNOSTIC = "diagnostic"
    PRACTICE = "practice"
    SELF_REPORT = "self_report"


class MasteryClass(StrEnum):
    STRONG = "strong"
    DEVELOPING = "developing"
    NEEDS_ATTENTION = "needs_attention"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class StudyPlanItemStatus(StrEnum):
    PENDING = "pending"
    # Completing a lesson is not mastery; mastery comes only from evidence.
    LESSON_COMPLETED = "lesson_completed"
    SKIPPED = "skipped"


class MessageRole(StrEnum):
    STUDENT = "student"
    TUTOR = "tutor"
