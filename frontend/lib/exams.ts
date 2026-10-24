// Pure helpers for the exam-breakdown editor: converting between the API shape
// and the editable form, and checking values before they are sent. The server
// repeats every check; these exist so mistakes show next to the field.

import type {
  AttemptStatus,
  ExamBreakdownDetail,
  ExamQuestion,
  ExamSubjectTopic,
  QuestionMapping,
  TopicSuggestion,
} from "@/lib/api";

export type EditorMapping = {
  topic_id: string | null;
  module_id: string | null;
  /** Percentage of the question as typed; blank means "split equally". */
  share: string;
};

export type EditorQuestion = {
  key: string;
  id: string | null;
  label: string;
  section: string;
  context: string | null;
  text: string;
  page: number | null;
  max_marks: string;
  marks_obtained: string;
  attempt_status: AttemptStatus;
  is_optional: boolean;
  choice_group: string;
  needs_review: boolean;
  parse_confidence: number | null;
  paper_module: string | null;
  mappings: EditorMapping[];
  suggestion: TopicSuggestion | null;
  counted: boolean | null;
  exclusion: string | null;
};

export type EditorHeader = {
  title: string;
  held_on: string;
  declared_total: string;
  assessment_id: string;
};

const NUMBER = /^\d+(\.\d{1,2})?$/;

let counter = 0;
function nextKey(): string {
  counter += 1;
  return `new-${counter}`;
}

function shareToPercent(m: QuestionMapping, count: number): string {
  if (count <= 1) return "";
  const pct = Number(m.share) * 100;
  return Number.isFinite(pct) ? String(Math.round(pct * 100) / 100) : "";
}

export function fromQuestion(q: ExamQuestion): EditorQuestion {
  return {
    key: q.id,
    id: q.id,
    label: q.label,
    section: q.section ?? "",
    context: q.context,
    text: q.text,
    page: q.page,
    max_marks: q.max_marks ? trimMark(q.max_marks) : "",
    marks_obtained: q.marks_obtained ? trimMark(q.marks_obtained) : "",
    attempt_status: q.attempt_status,
    is_optional: q.is_optional,
    choice_group: q.choice_group ?? "",
    needs_review: q.needs_review,
    parse_confidence: q.parse_confidence === null ? null : Number(q.parse_confidence),
    paper_module: q.paper_module,
    mappings: q.mappings.map((m) => ({
      topic_id: m.topic_id,
      module_id: m.module_id,
      share: shareToPercent(m, q.mappings.length),
    })),
    suggestion: q.suggestion,
    counted: q.counted,
    exclusion: q.exclusion,
  };
}

export function fromDetail(d: ExamBreakdownDetail): {
  header: EditorHeader;
  questions: EditorQuestion[];
} {
  return {
    header: {
      title: d.title,
      held_on: d.held_on ?? "",
      declared_total: d.declared_total ? trimMark(d.declared_total) : "",
      assessment_id: d.assessment_id ?? "",
    },
    questions: d.questions.map(fromQuestion),
  };
}

export function blankQuestion(after?: EditorQuestion): EditorQuestion {
  return {
    key: nextKey(),
    id: null,
    label: after ? nextLabel(after.label) : "1",
    section: after?.section ?? "",
    context: null,
    text: "",
    page: null,
    max_marks: "",
    marks_obtained: "",
    attempt_status: "unknown",
    is_optional: false,
    choice_group: after?.is_optional ? after.choice_group : "",
    needs_review: false,
    parse_confidence: null,
    paper_module: null,
    mappings: [],
    suggestion: null,
    counted: null,
    exclusion: null,
  };
}

const ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"];

/** "3" -> "4", "2(b)" -> "2(c)", "2(b)(i)" -> "2(b)(ii)"; anything else gets no guess. */
export function nextLabel(label: string): string {
  const top = /^(\d+)$/.exec(label);
  if (top) return String(Number(top[1]) + 1);
  // A second bracket level is roman numerals, as on most papers.
  const roman = /^(.*\)\()([ivx]+)\)$/.exec(label);
  if (roman) {
    const i = ROMAN.indexOf(roman[2]!);
    return i >= 0 && i < ROMAN.length - 1 ? `${roman[1]}${ROMAN[i + 1]})` : "";
  }
  const letter = /^(.*\()([a-y])\)$/.exec(label);
  if (letter) return `${letter[1]}${String.fromCharCode(letter[2]!.charCodeAt(0) + 1)})`;
  return "";
}

export function trimMark(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/** Field errors per question key. Empty when everything can be sent. */
export function validate(questions: EditorQuestion[]): Record<string, string[]> {
  const errors: Record<string, string[]> = {};
  const labels = new Map<string, number>();
  for (const q of questions)
    labels.set(q.label.trim().toLowerCase(), (labels.get(q.label.trim().toLowerCase()) ?? 0) + 1);
  for (const q of questions) {
    const out: string[] = [];
    const label = q.label.trim();
    if (!label) out.push("Enter the question number.");
    else if ((labels.get(label.toLowerCase()) ?? 0) > 1)
      out.push("This question number is used twice.");
    const max = q.max_marks.trim();
    const got = q.marks_obtained.trim();
    if (max && (!NUMBER.test(max) || Number(max) <= 0)) {
      out.push("Maximum marks must be a number greater than zero (up to two decimals).");
    }
    if (got) {
      if (!NUMBER.test(got)) out.push("Marks obtained must be a number of zero or more.");
      else if (!max) out.push("Enter the maximum marks before the marks obtained.");
      else if (NUMBER.test(max) && Number(got) > Number(max)) {
        out.push("Marks obtained cannot be more than the maximum marks.");
      }
      if (q.attempt_status === "not_attempted" && Number(got) > 0) {
        out.push("A question that was not attempted cannot earn marks.");
      }
    }
    if (q.mappings.length > 1) {
      const filled = q.mappings.filter((m) => m.share.trim() !== "");
      if (filled.length > 0 && filled.length < q.mappings.length) {
        out.push("Give a share for every topic, or leave all shares blank to split equally.");
      } else if (filled.length > 0) {
        const values = filled.map((m) => Number(m.share));
        if (values.some((v) => !Number.isFinite(v) || v <= 0)) {
          out.push("Each share must be a percentage greater than zero.");
        } else if (Math.abs(values.reduce((a, b) => a + b, 0) - 100) > 0.5) {
          out.push("The shares must add up to 100%.");
        }
      }
    }
    if (out.length) errors[q.key] = out;
  }
  return errors;
}

const blankToNull = (v: string) => (v.trim() === "" ? null : v.trim());

export function toPayload(
  header: EditorHeader,
  questions: EditorQuestion[],
  choiceRules: Record<string, number>,
) {
  return {
    title: header.title.trim(),
    held_on: blankToNull(header.held_on),
    declared_total: blankToNull(header.declared_total),
    assessment_id: blankToNull(header.assessment_id),
    choice_rules: choiceRules,
    questions: questions.map((q) => {
      const status: AttemptStatus =
        q.marks_obtained.trim() !== "" && q.attempt_status === "unknown"
          ? "attempted"
          : q.attempt_status;
      const withShares = q.mappings.length > 1 && q.mappings.every((m) => m.share.trim() !== "");
      return {
        id: q.id,
        label: q.label.trim(),
        section: blankToNull(q.section),
        context: q.context,
        text: q.text,
        page: q.page,
        max_marks: blankToNull(q.max_marks),
        marks_obtained: status === "not_attempted" ? null : blankToNull(q.marks_obtained),
        attempt_status: status,
        is_optional: q.is_optional,
        choice_group: q.is_optional ? blankToNull(q.choice_group) : null,
        needs_review: q.needs_review,
        mappings: q.mappings.map((m) => ({
          topic_id: m.topic_id,
          module_id: m.module_id,
          ...(withShares ? { share: (Number(m.share) / 100).toFixed(4) } : {}),
        })),
      };
    }),
  };
}

/** Map a question to a suggested topic (replacing any module-only mapping). */
export function withTopic(q: EditorQuestion, topicId: string): EditorQuestion {
  if (q.mappings.some((m) => m.topic_id === topicId)) return q;
  const kept = q.mappings.filter((m) => m.topic_id !== null);
  return { ...q, mappings: [...kept, { topic_id: topicId, module_id: null, share: "" }] };
}

export function withModuleOnly(q: EditorQuestion, moduleId: string): EditorQuestion {
  return { ...q, mappings: [{ topic_id: null, module_id: moduleId, share: "" }] };
}

/** Questions with a clear suggestion and no mapping yet. */
export function clearSuggestions(questions: EditorQuestion[]): Map<string, string> {
  const out = new Map<string, string>();
  for (const q of questions) {
    const s = q.suggestion;
    if (q.mappings.length === 0 && s?.status === "clear" && s.candidates[0]) {
      out.set(q.key, s.candidates[0].topic_id);
    }
  }
  return out;
}

export function topicModuleName(
  topicId: string,
  topics: ExamSubjectTopic[],
  modules: { id: string; number: number; name: string }[],
): string | null {
  const t = topics.find((x) => x.id === topicId);
  const m = t?.module_id ? modules.find((x) => x.id === t.module_id) : undefined;
  return m ? `Module ${m.number}: ${m.name}` : null;
}

export function formatMarks(value: string | null): string {
  return value === null ? "–" : trimMark(value);
}
