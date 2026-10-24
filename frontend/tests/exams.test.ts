import { describe, expect, it } from "vitest";

import type { ExamQuestion } from "@/lib/api";
import {
  blankQuestion,
  clearSuggestions,
  fromQuestion,
  nextLabel,
  toPayload,
  trimMark,
  validate,
  withModuleOnly,
  withTopic,
  type EditorQuestion,
} from "@/lib/exams";

const header = { title: "Series 1", held_on: "", declared_total: "", assessment_id: "" };

function q(over: Partial<EditorQuestion> = {}): EditorQuestion {
  return { ...blankQuestion(), label: "1", max_marks: "5", ...over };
}

describe("exam helpers", () => {
  it("guesses the next label only when the pattern is obvious", () => {
    expect(nextLabel("3")).toBe("4");
    expect(nextLabel("2(b)")).toBe("2(c)");
    expect(nextLabel("2(b)(i)")).toBe("2(b)(ii)");
    expect(nextLabel("2(b)(iv)")).toBe("2(b)(v)");
    expect(nextLabel("Q2 part one")).toBe("");
    expect(trimMark("5.00")).toBe("5");
    expect(trimMark("2.50")).toBe("2.5");
  });

  it("rejects bad marks next to the question", () => {
    const errors = validate([
      q({ key: "a", max_marks: "0" }),
      q({ key: "b", label: "2", marks_obtained: "6" }),
      q({ key: "c", label: "3", max_marks: "", marks_obtained: "2" }),
      q({ key: "d", label: "3" }),
    ]);
    expect(errors.a).toEqual([expect.stringMatching(/greater than zero/)]);
    expect(errors.b).toEqual([expect.stringMatching(/cannot be more than the maximum/)]);
    expect(errors.c).toContain("Enter the maximum marks before the marks obtained.");
    expect(errors.c).toContain("This question number is used twice.");
    expect(errors.d).toContain("This question number is used twice.");
  });

  it("requires shares to add up to 100 when given", () => {
    const two = [
      { topic_id: "t1", module_id: null, share: "70" },
      { topic_id: "t2", module_id: null, share: "" },
    ];
    expect(validate([q({ key: "a", mappings: two })]).a?.[0]).toMatch(/every topic/);
    const bad = two.map((m) => ({ ...m, share: "40" }));
    expect(validate([q({ key: "a", mappings: bad })]).a?.[0]).toMatch(/add up to 100/);
    const ok = [two[0]!, { ...two[1]!, share: "30" }];
    expect(validate([q({ key: "a", mappings: ok })])).toEqual({});
  });

  it("keeps a blank mark as unknown and an explicit zero as zero", () => {
    const body = toPayload(
      header,
      [
        q({ label: "1", marks_obtained: "" }),
        q({ label: "2", marks_obtained: "0" }),
        q({ label: "3", marks_obtained: "", attempt_status: "not_attempted" }),
      ],
      {},
    );
    expect(body.questions[0]).toMatchObject({ marks_obtained: null, attempt_status: "unknown" });
    expect(body.questions[1]).toMatchObject({ marks_obtained: "0", attempt_status: "attempted" });
    expect(body.questions[2]).toMatchObject({
      marks_obtained: null,
      attempt_status: "not_attempted",
    });
  });

  it("sends shares as fractions only when all are filled", () => {
    const mappings = [
      { topic_id: "t1", module_id: null, share: "60" },
      { topic_id: "t2", module_id: null, share: "40" },
    ];
    const body = toPayload(header, [q({ mappings })], {});
    expect(body.questions[0]!.mappings).toEqual([
      { topic_id: "t1", module_id: null, share: "0.6000" },
      { topic_id: "t2", module_id: null, share: "0.4000" },
    ]);
    const equal = toPayload(
      header,
      [q({ mappings: mappings.map((m) => ({ ...m, share: "" })) })],
      {},
    );
    expect(equal.questions[0]!.mappings[0]).not.toHaveProperty("share");
  });

  it("replaces a module-only mapping with a topic and back", () => {
    const moduleOnly = withModuleOnly(q(), "m1");
    expect(moduleOnly.mappings).toEqual([{ topic_id: null, module_id: "m1", share: "" }]);
    const topic = withTopic(moduleOnly, "t1");
    expect(topic.mappings).toEqual([{ topic_id: "t1", module_id: null, share: "" }]);
    expect(withTopic(topic, "t1")).toBe(topic);
  });

  it("offers only clear suggestions for unmapped questions", () => {
    const candidate = {
      topic_id: "t1",
      topic_name: "Stacks",
      module_id: null,
      score: 9,
      matched: ["stack"],
    };
    const clear = q({
      key: "a",
      suggestion: { status: "clear", candidates: [candidate], paper_module_id: null },
    });
    const ambiguous = q({
      key: "b",
      suggestion: { status: "ambiguous", candidates: [candidate], paper_module_id: null },
    });
    const mapped = withTopic(q({ key: "c", suggestion: clear.suggestion }), "t2");
    expect([...clearSuggestions([clear, ambiguous, mapped])]).toEqual([["a", "t1"]]);
  });

  it("reads shares from the API as percentages", () => {
    const api: ExamQuestion = {
      id: "q1",
      position: 0,
      label: "4(a)",
      section: "Part B",
      context: null,
      text: "Explain",
      page: 1,
      max_marks: "6.00",
      marks_obtained: null,
      attempt_status: "unknown",
      is_optional: true,
      choice_group: "Part B",
      needs_review: false,
      parse_confidence: "0.950",
      paper_module: null,
      mappings: [
        { topic_id: "t1", module_id: null, share: "0.7500" },
        { topic_id: "t2", module_id: null, share: "0.2500" },
      ],
      suggestion: { status: "none", candidates: [], paper_module_id: null },
      counted: false,
      exclusion: "no mark entered yet",
    };
    const e = fromQuestion(api);
    expect(e.max_marks).toBe("6");
    expect(e.marks_obtained).toBe("");
    expect(e.mappings.map((m) => m.share)).toEqual(["75", "25"]);
    expect(e.parse_confidence).toBeCloseTo(0.95);
  });
});
