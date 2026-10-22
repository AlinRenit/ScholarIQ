// Typed client for the ScholarIQ backend. Server components call the backend
// directly; browser code goes through the /api rewrite in next.config.ts.

export type CheckStatus = "ok" | "degraded" | "failed";

export type HealthCheck = {
  name: string;
  status: CheckStatus;
  detail: string;
  required: boolean;
};

export type Readiness = { status: CheckStatus; checks: HealthCheck[] };

export type Capability = {
  key: string;
  label: string;
  milestone: number;
  status: "available" | "planned";
};

export type SystemInfo = {
  name: string;
  version: string;
  deployment_mode: "server" | "offline";
  intelligence: string;
  uses_external_ai: boolean;
  max_upload_bytes: number;
  capabilities: Capability[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiBaseUrl(): string {
  if (typeof window !== "undefined") return "";
  return process.env.SCHOLARIQ_API_URL ?? "http://localhost:8000";
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export async function getJson<T>(
  path: string,
  opts: { fetchImpl?: FetchLike; acceptStatuses?: number[] } = {},
): Promise<T> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  let res: Response;
  try {
    res = await fetchImpl(`${apiBaseUrl()}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiError("The ScholarIQ API is not reachable.", null);
  }
  if (!res.ok && !(opts.acceptStatuses ?? []).includes(res.status)) {
    throw new ApiError(`Request to ${path} failed with status ${res.status}.`, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  systemInfo: (fetchImpl?: FetchLike) => getJson<SystemInfo>("/api/system/info", { fetchImpl }),
  // 503 still carries the per-check breakdown, which is what we want to show.
  readiness: (fetchImpl?: FetchLike) =>
    getJson<Readiness>("/api/health/ready", { fetchImpl, acceptStatuses: [503] }),
};

/** Load data for a server component, returning an error message instead of throwing. */
export async function load<T>(
  fn: () => Promise<T>,
): Promise<{ data: T; error: null } | { data: null; error: string }> {
  try {
    return { data: await fn(), error: null };
  } catch (e) {
    return { data: null, error: e instanceof Error ? e.message : "Unknown error" };
  }
}

// --------------------------------------------------------------------------- //
// Profiles, imports and academic records
// --------------------------------------------------------------------------- //

export type Profile = {
  id: string;
  display_name: string;
  consented_at: string | null;
  email?: string | null;
  has_password?: boolean;
};

export type DocumentStatus = "uploaded" | "extracted" | "confirmed" | "failed";

export type DocumentAnalysis = {
  source?: string;
  pages?: number;
  notes?: string[];
  warnings?: string[];
  grades_seen?: string[];
  context?: { semester: number | null; exam_type: string; exam_name: string | null };
  review_threshold?: number;
};

export type DocumentSummary = {
  id: string;
  original_filename: string;
  media_type: string;
  size_bytes: number;
  status: DocumentStatus;
  parser_name: string | null;
  error: string | null;
  created_at: string;
  file_retained: boolean;
  analysis: DocumentAnalysis;
};

export type ExtractedFields = {
  subject_name?: string;
  subject_code?: string | null;
  component?: string;
  status?: string;
  marks_obtained?: string | null;
  max_marks?: string | null;
  grade?: string | null;
  grade_points?: string | null;
  credits?: string | null;
  semester?: number | null;
  exam_type?: string;
  exam_name?: string | null;
  result?: string;
};

export type ExtractedRecord = {
  id: string;
  row_index: number;
  source_text: string | null;
  fields: ExtractedFields;
  confidence: Record<string, number>;
  warnings: string[];
};

export type DocumentDetail = DocumentSummary & { records: ExtractedRecord[] };

export type ScaleTemplate = {
  key: string;
  name: string;
  description: string;
  max_points: string;
  points: Record<string, string>;
};

export type AcademicResult = {
  id: string;
  subject_id: string;
  subject_name: string;
  subject_code: string | null;
  component: "theory" | "lab" | "combined";
  status: "present" | "absent" | "withheld" | "missing";
  marks_obtained: string | null;
  max_marks: string | null;
  grade: string | null;
  grade_points: string | null;
  credits: string | null;
  attempt_number: number;
  grading_scale_id: string | null;
};

export type AcademicAssessment = {
  id: string;
  document_id: string | null;
  semester: number | null;
  exam_type: string;
  exam_name: string | null;
  results: AcademicResult[];
};

/** Extract a readable message from a FastAPI error body. */
export function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const item = d as { msg?: string; loc?: unknown[] };
          const msg = (item.msg ?? "Invalid value").replace(/^Value error, /, "");
          const row = item.loc?.find((p) => typeof p === "number");
          return typeof row === "number" ? `Row ${row + 1}: ${msg}` : msg;
        })
        .join(" ");
    }
  }
  return fallback;
}

// --------------------------------------------------------------------------- //
// Analytics and topics
// --------------------------------------------------------------------------- //

export type ScoreOut = { percent: number; basis: "marks" | "grade_points" };
export type AggregateOut = {
  value: number | null;
  basis: string;
  counted: number;
  excluded: number;
  reason: string | null;
};
export type Band = "strong" | "developing" | "needs_attention" | "no_score";
export type SubjectAnalysis = {
  id: string;
  name: string;
  is_custom: boolean;
  mapped_topics: number;
  band: Band;
  latest: ScoreOut | null;
  latest_note: string | null;
  best: ScoreOut | null;
  credits: number | null;
  sittings: {
    semester: number | null;
    exam_type: string;
    score: ScoreOut | null;
    note: string | null;
    components: string[];
  }[];
  notes: string[];
};
export type SemesterAnalysis = {
  semester: number | null;
  results: number;
  marks_percentage: AggregateOut;
  credit_weighted_percentage: AggregateOut;
  gpa: AggregateOut;
};
export type Overview = {
  policy: { version: string; subject_bands: { strong_at: number; attention_below: number } };
  counts: { subjects: number; results: number; assessments: number; semesters: number };
  overall: Record<"marks_percentage" | "credit_weighted_percentage" | "gpa", AggregateOut>;
  semesters: SemesterAnalysis[];
  trend: { direction: string; change_points: number | null; explanation: string };
  spread_points: number | null;
  subjects: SubjectAnalysis[];
  grade_distribution: Record<string, number>;
  data_gaps: string[];
  methodology: string[];
};

export type MasteryClass = "strong" | "developing" | "needs_attention" | "insufficient_evidence";
export type TopicEvidence = {
  id: string;
  kind: string;
  description: string;
  observed_at: string;
  removable: boolean;
};
export type TopicAnalysis = {
  id: string;
  slug: string;
  name: string;
  estimated_study_minutes: number | null;
  subjects: { id: string; name: string; importance: number }[];
  classification: MasteryClass;
  direct_observations: number;
  reasons: string[];
  subject_messages: string[];
  next_action: string;
  rule_version: string;
  evidence: TopicEvidence[];
};

export type CurriculumSubject = {
  id: string;
  slug: string;
  name: string;
  code: string | null;
  aliases: string[];
  is_custom: boolean;
  topics: { id: string; slug: string; name: string; importance: number }[];
};

export type TrustStatus = "verified" | "imported" | "retired";
export type KnowledgeTopicCoverage = {
  id: string;
  slug: string;
  name: string;
  concepts: number;
  verified_concepts: number;
  documents: number;
  questions: number;
};
export type KnowledgeOverview = {
  concepts: number;
  verified_concepts: number;
  documents: number;
  questions: number;
  allow_unreviewed: boolean;
  subjects: { id: string; name: string; topics: KnowledgeTopicCoverage[] }[];
};
export type KnowledgeTopic = {
  slug: string;
  name: string;
  concepts: { slug: string; name: string; trust_status: TrustStatus }[];
};
export type KnowledgeSearchMatch = {
  slug: string;
  name: string;
  topic_slug: string;
  topic_name: string;
  trust_status: TrustStatus;
  score: number;
  matched_terms: Record<string, number>;
  name_match: string | null;
  name_bonus: number;
};
export type KnowledgeSearch = {
  query: string;
  method: string;
  unmatched_terms: string[];
  allow_unreviewed: boolean;
  results: KnowledgeSearchMatch[];
};
export type KnowledgeConcept = {
  slug: string;
  name: string;
  aliases: string[];
  definition: string;
  attributes: Record<string, string>;
  difficulty: number;
  topic_slug: string;
  topic_name: string;
  trust_status: TrustStatus;
  reviewed_by: string | null;
  reviewed_on: string | null;
  content_version: string;
  origin: string | null;
  documents: { kind: string; title: string; body: string; steps: string[]; depth: number }[];
  relations: { kind: string; direction: "in" | "out"; slug: string; name: string }[];
  further_reading: {
    title: string;
    authors: string | null;
    citation: string | null;
    url: string | null;
  }[];
  question_count: number;
};

// --------------------------------------------------------------------------- //
// Tutor
// --------------------------------------------------------------------------- //

export type TutorAction = "simplify" | "example" | "check" | "deeper";
export type SectionKind =
  | "definition"
  | "facts"
  | "explanation"
  | "procedure"
  | "example"
  | "misconception"
  | "check"
  | "table"
  | "list"
  | "steps"
  | "code"
  | "note"
  | "summary";
export type AnswerOrigin = {
  kind: "knowledge" | "solver" | "analysis" | "template";
  concept: string | null;
  document: string | null;
  solver: string | null;
  trust: TrustStatus | null;
};
export type AnswerItem = {
  text: string;
  detail: string | null;
  concept: string | null;
  topic: string | null;
};
export type CheckQuestion = { slug: string; prompt: string; kind: string; options: string[] };
export type AnswerSection = {
  kind: SectionKind;
  title: string;
  text: string | null;
  steps: string[];
  columns: string[];
  rows: string[][];
  items: AnswerItem[];
  code: string | null;
  question: CheckQuestion | null;
  origin: AnswerOrigin;
};
export type ConceptRef = {
  slug: string;
  name: string;
  topic_slug: string;
  topic_name: string;
  trust: TrustStatus;
};
export type Suggestion = {
  label: string;
  action: TutorAction | "ask";
  query: string | null;
  // On a clarifying question's option: the concept slug that option stands for.
  concept?: string | null;
};
export type TutorAnswer = {
  status: "answered" | "clarify" | "abstained";
  handler: string;
  handler_label: string;
  intent: string;
  concepts: ConceptRef[];
  sections: AnswerSection[];
  review: { all_reviewed: boolean; label: string | null; unreviewed: string[] };
  personalisation: {
    topic: string | null;
    classification: string | null;
    level: "overview" | "balanced" | "guided" | "deeper";
    explanation: string;
  } | null;
  interpretation: string[];
  clarification: { question: string; options: Suggestion[] } | null;
  missing: string | null;
  suggestions: Suggestion[];
  further_reading: {
    title: string;
    authors: string | null;
    citation: string | null;
    url: string | null;
  }[];
  limitations: string[];
  rules_version: string;
};
export type AskResult = { conversation_id: string; message_id: string; answer: TutorAnswer };
export type ConversationSummary = {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string | null;
  messages: number;
};
export type TutorMessage = {
  id: string;
  role: "student" | "tutor";
  text: string;
  created_at: string;
  answer: TutorAnswer | null;
};
export type ConversationDetail = {
  id: string;
  title: string | null;
  retention_days: number;
  messages: TutorMessage[];
};
export type CheckResult = {
  correct: boolean;
  expected: string;
  explanation: string;
  recorded_as_evidence: boolean;
};
export type TutorInfo = {
  retention_days: number;
  rules_version: string;
  solvers: string[];
  allow_unreviewed: boolean;
};

// --------------------------------------------------------------------------- //
// Practice (diagnostic quizzes) and study plan
// --------------------------------------------------------------------------- //

export type QuizSummary = { id: string; submitted_at: string; correct: number; total: number };
export type PracticeTopic = {
  slug: string;
  name: string;
  subjects: string[];
  questions: number;
  classification: MasteryClass;
  quizzes: QuizSummary[];
  open_quiz: string | null;
};
export type QuizQuestion = {
  slug: string;
  prompt: string;
  options: string[];
  style: "conceptual" | "application" | string;
  difficulty: number;
  concept: string | null;
  trust: TrustStatus;
};
export type QuizOutcome = {
  classification: MasteryClass;
  reasons: string[];
  next_action: string;
  direct_observations: number;
};
export type Quiz = {
  id: string;
  topic_slug: string;
  topic_name: string;
  created_at: string;
  available: number;
  questions: QuizQuestion[];
  submitted_at: string | null;
  correct: number | null;
  marked: {
    slug: string;
    chosen: number;
    correct_option: number;
    correct: boolean;
    explanation: string;
  }[];
  before: QuizOutcome | null;
  after: QuizOutcome | null;
  recorded_as_evidence: boolean;
};
export type PlanTerm = { value: number; weight: number; contribution: number; why: string };
export type PlanItemStatus = "pending" | "lesson_completed" | "skipped";
export type PlanItem = {
  id: string;
  topic_slug: string;
  topic_name: string;
  position: number;
  priority: string;
  status: PlanItemStatus;
  breakdown: {
    classification: MasteryClass;
    minutes: number | null;
    terms: Record<string, PlanTerm>;
    after: string[];
    moved_for: string | null;
    goal: boolean;
    next_step: string;
  };
};
export type StudyPlan = {
  id: string;
  created_at: string;
  formula_version: string;
  parameters: {
    goal_topics: string[];
    weights: Record<string, number>;
    policy_version: string;
    left_out_strong: string[];
  };
  items: PlanItem[];
};
