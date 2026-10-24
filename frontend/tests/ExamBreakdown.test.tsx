import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisView } from "@/components/exams/AnalysisView";
import { BreakdownEditor } from "@/components/exams/BreakdownEditor";
import type { ExamAnalysis, ExamBreakdownDetail, ExamQuestion } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

function question(over: Partial<ExamQuestion>): ExamQuestion {
  return {
    id: "q1",
    position: 0,
    label: "1",
    section: null,
    context: null,
    text: "Define a stack.",
    page: 1,
    max_marks: "2.00",
    marks_obtained: null,
    attempt_status: "unknown",
    is_optional: false,
    choice_group: null,
    needs_review: false,
    parse_confidence: "0.950",
    paper_module: null,
    mappings: [],
    suggestion: {
      status: "clear",
      candidates: [
        {
          topic_id: "t-stack",
          topic_name: "Stacks and queues",
          module_id: "m2",
          score: 9,
          matched: ["stack"],
        },
      ],
      paper_module_id: null,
    },
    counted: false,
    exclusion: "no mark entered yet",
    ...over,
  };
}

const detail: ExamBreakdownDetail = {
  id: "b1",
  title: "Series test 1",
  subject_id: "s1",
  subject_name: "Data Structures",
  assessment_id: null,
  held_on: null,
  status: "draft",
  question_count: 1,
  earned: null,
  possible: null,
  percentage: null,
  complete: false,
  updated_at: "2026-10-24T10:00:00Z",
  declared_total: null,
  choice_rules: {},
  questions: [question({})],
  modules: [
    { id: "m1", number: 1, name: "Introduction and analysis" },
    { id: "m2", number: 2, name: "Linear data structures" },
  ],
  topics: [
    { id: "t-cx", slug: "complexity", name: "Complexity", module_id: "m1" },
    { id: "t-stack", slug: "stacks-queues", name: "Stacks and queues", module_id: "m2" },
  ],
  paper: null,
  recorded: null,
  warnings: [],
};

function reply(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("BreakdownEditor", () => {
  beforeEach(() => {
    push.mockReset();
    vi.stubGlobal("confirm", () => true);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows a parsing error and keeps manual entry available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        reply({
          questions_found: 0,
          warnings: [],
          error: "No text could be read from this file.",
          source: null,
          breakdown: { ...detail, questions: [] },
        }),
      ),
    );
    render(<BreakdownEditor initial={{ ...detail, questions: [] }} assessments={[]} maxMb={10} />);
    const input = screen.getByLabelText("Choose a question paper file");
    fireEvent.change(input, { target: { files: [new File(["x"], "paper.pdf")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not be read: No text could be read.*enter the questions by hand/,
    );
    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toBe("/api/exam-breakdowns/b1/paper?replace=true");
    expect(screen.getByRole("button", { name: "Add a question" })).toBeEnabled();
  });

  it("blocks saving with field errors and sends nothing", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<BreakdownEditor initial={detail} assessments={[]} maxMb={10} />);
    fireEvent.change(screen.getByLabelText("Marks obtained"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((a) => a.textContent).join(" ")).toMatch(
      /cannot be more than the maximum marks/,
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("applies a clear suggestion, saves and confirms", async () => {
    const saved = {
      ...detail,
      questions: [
        question({
          marks_obtained: "1.50",
          attempt_status: "attempted",
          mappings: [{ topic_id: "t-stack", module_id: null, share: "1.0000" }],
          counted: true,
          exclusion: null,
        }),
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => (url.endsWith("/confirm") ? reply({}) : reply(saved))),
    );
    render(<BreakdownEditor initial={detail} assessments={[]} maxMb={10} />);
    fireEvent.click(screen.getByRole("button", { name: /Use 1 clear topic suggestion/ }));
    fireEvent.change(screen.getByLabelText("Marks obtained"), { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and confirm" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/exam-breakdown/b1/analysis"));
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/exam-breakdowns/b1");
    const body = JSON.parse(String(init.body));
    expect(body.questions[0]).toMatchObject({
      marks_obtained: "1.5",
      attempt_status: "attempted",
      mappings: [{ topic_id: "t-stack", module_id: null }],
    });
    expect(vi.mocked(fetch).mock.calls[1]![0]).toBe("/api/exam-breakdowns/b1/confirm");
  });

  it("shows the server's reason when confirming fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.endsWith("/confirm")
          ? reply({ detail: "Enter marks for at least one question before confirming." }, 422)
          : reply(detail),
      ),
    );
    render(<BreakdownEditor initial={detail} assessments={[]} maxMb={10} />);
    fireEvent.click(screen.getByRole("button", { name: "Save and confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least one question/);
    expect(push).not.toHaveBeenCalled();
  });
});

const analysis: ExamAnalysis = {
  breakdown: {
    ...detail,
    status: "confirmed",
    earned: "7.50",
    possible: "12.00",
    percentage: 62.5,
  },
  overall: {
    earned: "7.50",
    possible: "12.00",
    percentage: 62.5,
    band: "developing",
    counted: 3,
    total_questions: 4,
    complete: false,
    excluded: [{ reason: "no_mark", text: "no mark entered yet", labels: ["4"] }],
    unmapped: [],
  },
  modules: [
    {
      id: "m1",
      number: 1,
      name: "Introduction and analysis",
      earned: "5.00",
      possible: "6.00",
      percentage: 83.3,
      band: "strong",
      questions: ["1"],
      marks_lost: "1.00",
      lost_by: [{ label: "1", lost: "1.00" }],
      topics: ["Complexity"],
      evidence: "complete",
      left_out: [],
      module_only: [],
    },
    {
      id: "m2",
      number: 2,
      name: "Linear data structures",
      earned: "2.50",
      possible: "6.00",
      percentage: 41.7,
      band: "needs_attention",
      questions: ["2", "3"],
      marks_lost: "3.50",
      lost_by: [
        { label: "3", lost: "2.50" },
        { label: "2", lost: "1.00" },
      ],
      topics: ["Stacks and queues"],
      evidence: "partial",
      left_out: ["4"],
      module_only: ["3"],
    },
  ],
  focus_module_id: "m2",
  topics: [
    {
      id: "t-stack",
      name: "Stacks and queues",
      module_id: "m2",
      module_name: "Linear data structures",
      earned: "1.00",
      possible: "2.00",
      percentage: 50,
      band: "needs_attention",
      questions: ["2"],
      marks_lost: "1.00",
      lost_by: [{ label: "2", lost: "1.00" }],
      partial: false,
      classification: "insufficient_evidence",
      direct_observations: 1,
      min_observations: 5,
      evidence_sufficient: false,
      recommendation: "Revise Stacks and queues first in this subject: most marks were lost in Q2.",
    },
  ],
  recorded: null,
  warnings: [],
  rule_version: "exam-breakdown/1",
};

describe("AnalysisView", () => {
  it("highlights the focus module and labels partial data", () => {
    render(<AnalysisView analysis={analysis} />);
    expect(screen.getByText("62.5%")).toBeInTheDocument();
    expect(screen.getByText(/Partial: some questions are not counted/)).toBeInTheDocument();
    expect(screen.getByText(/Not counted \(no mark entered yet\): Q4/)).toBeInTheDocument();
    const focus = screen.getByText("▲ Needs the most attention").closest("li")!;
    expect(within(focus).getByText(/Module 2: Linear data structures/)).toBeInTheDocument();
    // The focus module starts expanded; another can be opened.
    expect(within(focus).getByRole("button", { name: "Hide details" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(within(focus).getByText(/Mapped to the module only/)).toHaveTextContent("Q3");
    const other = screen.getByText(/Module 1: Introduction/).closest("li")!;
    const toggle = within(other).getByRole("button", { name: "Show topics and questions" });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps exam performance separate from topic mastery", () => {
    render(<AnalysisView analysis={analysis} />);
    const topics = screen.getByRole("heading", { name: /By topic/ }).parentElement!;
    expect(within(topics).getByText("May need attention")).toBeInTheDocument();
    expect(within(topics).getByText("Insufficient evidence")).toBeInTheDocument();
    expect(within(topics).getByText(/1 of 5 direct observations/)).toBeInTheDocument();
    expect(
      screen.getByText(/Exam performance is how you scored on this paper/),
    ).toBeInTheDocument();
  });
});
