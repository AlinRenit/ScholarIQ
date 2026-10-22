import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatTile } from "@/components/dashboard/StatTile";
import { TopicCard } from "@/components/topics/TopicCard";
import type { TopicAnalysis } from "@/lib/api";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const topic: TopicAnalysis = {
  id: "t1",
  slug: "db.normalization",
  name: "Normalization",
  estimated_study_minutes: 90,
  subjects: [{ id: "s1", name: "DBMS", importance: 3 }],
  classification: "insufficient_evidence",
  direct_observations: 0,
  reasons: ["0 topic-level observation(s) recorded; at least 5 are needed."],
  subject_messages: ["Your DBMS score suggests this subject may need attention."],
  next_action: "Take a short diagnostic quiz on this topic.",
  rule_version: "topic-rules/1",
  evidence: [
    {
      id: "e1",
      kind: "subject_score_prior",
      description: "DBMS: 42% (weak prior)",
      observed_at: "2026-10-22T00:00:00Z",
      removable: false,
    },
    {
      id: "e2",
      kind: "self_report",
      description: "Self-rated 2 of 5",
      observed_at: "2026-10-22T00:00:00Z",
      removable: true,
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
  refresh.mockReset();
});

describe("TopicCard", () => {
  it("shows the classification with a symbol and label, never colour alone", () => {
    render(<TopicCard topic={topic} />);
    expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
    expect(screen.getByText("○")).toBeInTheDocument();
    expect(screen.getByText(/may need attention/)).toBeInTheDocument();
  });

  it("only lets students remove evidence they entered", () => {
    render(<TopicCard topic={topic} />);
    expect(screen.getAllByRole("button", { name: /^Remove/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Remove: Self-rated 2 of 5" })).toBeInTheDocument();
  });

  it("posts a topic test result and refreshes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ id: "e3" }), { status: 201 }));
    render(<TopicCard topic={topic} />);
    fireEvent.click(screen.getByRole("button", { name: "Add a topic test result" }));
    fireEvent.change(screen.getByLabelText("Marks obtained"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Maximum marks"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Questions"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/topics/t1/evidence");
    expect(JSON.parse(String(init?.body))).toEqual({
      kind: "topic_exam",
      obtained: "7",
      maximum: "10",
      questions: 5,
    });
  });

  it("shows the API's error instead of pretending to save", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "marks obtained exceed maximum marks" }), {
        status: 422,
      }),
    );
    render(<TopicCard topic={topic} />);
    fireEvent.click(screen.getByRole("button", { name: "Rate my confidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("exceed maximum");
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("StatTile", () => {
  const agg = {
    value: null,
    basis: "grade_points",
    counted: 0,
    excluded: 4,
    reason: "No credits.",
  };

  it("explains a missing figure rather than showing zero", () => {
    render(<StatTile label="GPA" value={null} agg={agg} detail="x" />);
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("No credits.")).toBeInTheDocument();
  });

  it("states how many results a figure counts", () => {
    render(
      <StatTile
        label="Overall"
        value={71.5}
        suffix="%"
        agg={{ ...agg, value: 71.5, counted: 6, reason: null }}
        detail="Total marks."
      />,
    );
    expect(screen.getByText("71.5%")).toBeInTheDocument();
    expect(screen.getByText(/Counts 6 result/)).toBeInTheDocument();
  });
});
