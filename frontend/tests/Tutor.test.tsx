import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnswerView } from "@/components/tutor/AnswerView";
import { CheckQuestionCard } from "@/components/tutor/CheckQuestionCard";
import { TutorWorkspace } from "@/components/tutor/TutorWorkspace";
import type { AnswerSection, ConceptRef, TutorAnswer } from "@/lib/api";

const knowledge = (concept: string, document: string | null = null) => ({
  kind: "knowledge" as const,
  concept,
  document,
  solver: null,
  trust: "imported" as const,
});

const section = (s: Partial<AnswerSection> & Pick<AnswerSection, "kind" | "title">) => ({
  text: null,
  steps: [],
  columns: [],
  rows: [],
  items: [],
  code: null,
  question: null,
  origin: knowledge("ds.stack"),
  ...s,
});

const answer = (a: Partial<TutorAnswer> = {}): TutorAnswer => ({
  status: "answered",
  handler: "A",
  handler_label: "Definition and explanation",
  intent: "definition",
  concepts: [
    {
      slug: "ds.stack",
      name: "Stack",
      topic_slug: "ds.stacks-queues",
      topic_name: "Stacks and queues",
      trust: "imported",
    },
  ],
  sections: [
    section({ kind: "definition", title: "Definition", text: "A last-in\nfirst-out collection." }),
    section({ kind: "facts", title: "Key facts", rows: [["Ordering", "LIFO"]] }),
  ],
  review: {
    all_reviewed: false,
    label: "Not yet reviewed by a person",
    unreviewed: ["ds.stack"],
  },
  personalisation: null,
  interpretation: ['Recognised concept "Stack" (ds.stack).'],
  clarification: null,
  missing: null,
  suggestions: [{ label: "Stack vs queue", action: "ask", query: "stack vs queue" }],
  further_reading: [],
  limitations: [],
  rules_version: "tutor-rules/1",
  ...a,
});

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

afterEach(() => vi.unstubAllGlobals());

describe("AnswerView", () => {
  it("labels unreviewed material and says where each section came from", () => {
    render(<AnswerView answer={answer()} />);
    expect(screen.getByRole("note")).toHaveTextContent("Not yet reviewed by a person");
    expect(screen.getByRole("note")).toHaveTextContent("Unreviewed material: Stack.");
    expect(screen.getByText("A last-in first-out collection.")).toBeInTheDocument();
    expect(screen.getAllByText("From the knowledge base: Stack")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Sources" }).parentElement).toHaveTextContent(
      "Stack",
    );
    expect(screen.getByRole("rowheader", { name: "Ordering" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByText("How I read your question")).toBeInTheDocument();
  });

  it("offers actions and suggestions only on the latest answer", () => {
    const onPick = vi.fn();
    const { rerender } = render(<AnswerView answer={answer()} onPick={onPick} latest />);
    fireEvent.click(screen.getByRole("button", { name: "Explain more simply" }));
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ action: "simplify" }));
    fireEvent.click(screen.getByRole("button", { name: "Stack vs queue" }));
    expect(onPick).toHaveBeenLastCalledWith(expect.objectContaining({ query: "stack vs queue" }));

    rerender(<AnswerView answer={answer()} onPick={onPick} latest={false} />);
    expect(screen.queryByRole("button", { name: "Explain more simply" })).toBeNull();
  });

  it("shows a declined answer without inventing content", () => {
    render(
      <AnswerView
        answer={answer({
          status: "abstained",
          handler: "F",
          handler_label: "Not covered",
          concepts: [],
          sections: [],
          review: { all_reviewed: true, label: null, unreviewed: [] },
          missing: "Nothing in the knowledge base covers “krebs cycle”.",
        })}
      />,
    );
    expect(screen.getByText("I can’t answer this from the knowledge base.")).toBeInTheDocument();
    expect(screen.getByText(/krebs cycle/)).toBeInTheDocument();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("asks which meaning was intended", () => {
    const onPick = vi.fn();
    render(
      <AnswerView
        latest
        onPick={onPick}
        answer={answer({
          status: "clarify",
          sections: [],
          review: { all_reviewed: true, label: null, unreviewed: [] },
          clarification: {
            question: "Which did you mean?",
            options: [{ label: "Relation (Relational model)", action: "ask", query: "Explain X" }],
          },
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Relation (Relational model)" }));
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ query: "Explain X" }));
  });
});

describe("CheckQuestionCard", () => {
  it("sends the chosen option and shows the marked result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        json({
          correct: false,
          expected: "LIFO",
          explanation: "Last in, first out.",
          recorded_as_evidence: false,
        }),
      ),
    );
    render(
      <CheckQuestionCard
        question={{
          slug: "q1",
          prompt: "Order?",
          kind: "multiple_choice",
          options: ["FIFO", "LIFO"],
        }}
      />,
    );
    const submit = screen.getByRole("button", { name: "Check answer" });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByLabelText("FIFO"));
    fireEvent.click(submit);
    expect(await screen.findByText(/expected answer is: LIFO/)).toBeInTheDocument();
    expect(screen.getByText(/not recorded/)).toBeInTheDocument();
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      question: "q1",
      response: { option_index: 0 },
    });
  });
});

describe("TutorWorkspace", () => {
  const info = {
    retention_days: 30,
    rules_version: "tutor-rules/1",
    solvers: [],
    allow_unreviewed: true,
  };

  it("asks a question and renders the answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url === "/api/tutor/ask"
          ? json({ conversation_id: "c1", message_id: "m1", answer: answer() })
          : json([
              {
                id: "c1",
                title: "What is a stack?",
                created_at: "",
                last_message_at: "",
                messages: 2,
              },
            ]),
      ),
    );
    render(<TutorWorkspace initialConversations={[]} info={info} />);
    expect(screen.getByText(/deleted 30 days after/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your question"), {
      target: { value: "What is a stack?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Definition and explanation")).toBeInTheDocument();
    expect(screen.getByText("What is a stack?", { selector: "p" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "What is a stack?" })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Go deeper" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4));
    const [, init] = vi.mocked(fetch).mock.calls[2] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      text: "",
      conversation_id: "c1",
      action: "deeper",
      meaning: null,
    });
  });

  it("keeps the question and offers a retry when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ detail: "Too many questions at once; wait a moment." }, 429)),
    );
    render(<TutorWorkspace initialConversations={[]} info={info} />);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "stack" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many questions");
    expect(screen.getByLabelText("Your question")).toHaveValue("stack");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("deletes a conversation after confirmation", async () => {
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))),
    );
    render(
      <TutorWorkspace
        initialConversations={[
          { id: "c1", title: "Stacks", created_at: "", last_message_at: "", messages: 2 },
        ]}
        info={info}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete conversation: Stacks" }));
    await waitFor(() =>
      expect(screen.getByText("No saved conversations yet.")).toBeInTheDocument(),
    );
    expect(vi.mocked(fetch).mock.calls[0]).toEqual([
      "/api/tutor/conversations/c1",
      { method: "DELETE" },
    ]);
  });
});

describe("AnswerView sources", () => {
  it("names every concept behind a comparison table", () => {
    const [stack] = answer().concepts as [ConceptRef];
    const queue: ConceptRef = { ...stack, slug: "ds.queue", name: "Queue" };
    render(
      <AnswerView
        answer={answer({
          concepts: [stack, queue],
          sections: [
            section({
              kind: "table",
              title: "Stack and Queue compared",
              columns: ["", "Stack", "Queue"],
              rows: [["Ordering", "LIFO", "FIFO"]],
              origin: knowledge("ds.stack ds.queue"),
            }),
          ],
        })}
      />,
    );
    expect(screen.getByText("From the knowledge base: Stack, Queue")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Queue" })[0]).toBeInTheDocument();
  });
});
