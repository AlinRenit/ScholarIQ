import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StudyPlanView } from "@/components/plan/StudyPlanView";
import { QuizRunner } from "@/components/practice/QuizRunner";
import type { PlanItem, Quiz, StudyPlan } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

afterEach(() => vi.unstubAllGlobals());

const quiz: Quiz = {
  id: "qz1",
  topic_slug: "ds.stacks-queues",
  topic_name: "Stacks and queues",
  created_at: "2026-10-22T10:00:00Z",
  available: 7,
  questions: [
    {
      slug: "q1",
      prompt: "Which order does a stack follow?",
      options: ["FIFO", "LIFO"],
      style: "conceptual",
      difficulty: 1,
      concept: "Stack",
      trust: "imported",
    },
    {
      slug: "q2",
      prompt: "Which structure suits undo?",
      options: ["Queue", "Stack"],
      style: "application",
      difficulty: 2,
      concept: "Stack",
      trust: "imported",
    },
  ],
  submitted_at: null,
  correct: null,
  marked: [],
  before: null,
  after: null,
  recorded_as_evidence: false,
};

describe("QuizRunner", () => {
  it("needs every answer, then shows marking and the classification change", async () => {
    const marked: Quiz = {
      ...quiz,
      submitted_at: "2026-10-22T10:05:00Z",
      correct: 1,
      recorded_as_evidence: true,
      marked: [
        { slug: "q1", chosen: 0, correct_option: 1, correct: false, explanation: "Last in." },
        { slug: "q2", chosen: 1, correct_option: 1, correct: true, explanation: "Undo pops." },
      ],
      before: {
        classification: "insufficient_evidence",
        reasons: ["0 topic-level observation(s) recorded"],
        next_action: "",
        direct_observations: 0,
      },
      after: {
        classification: "needs_attention",
        reasons: ["Based on 5 topic-level observation(s):", "  Diagnostic quiz: 1 of 2 correct"],
        next_action: "",
        direct_observations: 5,
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(marked)),
    );
    render(<QuizRunner initial={quiz} />);
    expect(screen.getByRole("note")).toHaveTextContent("Not yet reviewed by a person");
    const submit = screen.getByRole("button", { name: "Submit answers" });
    expect(submit).toBeDisabled();
    expect(screen.getByText("2 question(s) left to answer.")).toBeInTheDocument();

    const [first, second] = screen.getAllByRole("group");
    fireEvent.click(within(first!).getByLabelText("FIFO"));
    fireEvent.click(within(second!).getByLabelText("Stack"));
    fireEvent.click(submit);

    expect(await screen.findByText("1 of 2 correct")).toBeInTheDocument();
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ answers: { q1: 0, q2: 1 } });
    expect(screen.getByText("Before this quiz")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Diagnostic quiz: 1 of 2 correct")).toBeInTheDocument();
    expect(screen.getByText("✗ your answer")).toBeInTheDocument();
    expect(screen.getByText("Last in.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit answers" })).toBeNull();
  });
});

const item = (over: Partial<PlanItem> = {}): PlanItem => ({
  id: "i1",
  topic_slug: "db.normalization",
  topic_name: "Normalization",
  position: 0,
  priority: "4.8",
  status: "pending",
  breakdown: {
    classification: "needs_attention",
    minutes: 150,
    terms: {
      need: { value: 1, weight: 3, contribution: 3, why: "Classified needs attention" },
      study_time: { value: 0.5, weight: -0.5, contribution: -0.25, why: "About 150 minutes" },
    },
    after: ["Functional dependencies"],
    moved_for: null,
    goal: false,
    next_step: "Work through it with the tutor step by step, then take a diagnostic quiz.",
  },
  ...over,
});

const plan: StudyPlan = {
  id: "p1",
  created_at: "2026-10-22T10:00:00Z",
  formula_version: "plan-formula/1",
  parameters: {
    goal_topics: [],
    weights: { need: 3, importance: 2, goal: 2, unlocks: 1, recent_result: 1, study_time: 0.5 },
    policy_version: "policy/1",
    left_out_strong: ["Hashing"],
  },
  items: [item()],
};

describe("StudyPlanView", () => {
  it("explains each position and keeps 'studied' separate from mastery", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(item({ status: "lesson_completed" }))),
    );
    render(<StudyPlanView initial={plan} subjects={[]} />);
    expect(screen.getByText(/Comes after Functional dependencies/)).toBeInTheDocument();
    expect(
      screen.getByText(/Left out because your evidence shows them as Strong: Hashing/),
    ).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Need" })).toBeInTheDocument();
    expect(screen.getByText("1 × 3")).toBeInTheDocument();
    expect(screen.getByText("2 h 30 min")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark as studied" }));
    expect(await screen.findByText(/not evidence/)).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe("/api/study-plan/items/i1");
    expect(screen.getByRole("button", { name: "Undo studied" })).toBeInTheDocument();
  });

  it("builds a plan with the chosen goals", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ ...plan, items: [] })),
    );
    render(
      <StudyPlanView
        initial={null}
        subjects={[
          {
            id: "s",
            slug: "dbms",
            name: "DBMS",
            code: null,
            aliases: [],
            is_custom: false,
            topics: [{ id: "t", slug: "db.sql", name: "SQL", importance: 5 }],
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByLabelText("SQL"));
    fireEvent.click(screen.getByRole("button", { name: "Build my plan" }));
    expect(await screen.findByText("Nothing to plan yet.")).toBeInTheDocument();
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({ goal_topics: ["db.sql"] });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Rebuild plan" })).toBeInTheDocument(),
    );
  });
});
