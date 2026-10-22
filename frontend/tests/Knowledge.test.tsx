import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConceptView } from "@/components/knowledge/ConceptView";
import { SearchResults } from "@/components/knowledge/SearchResults";
import type { KnowledgeConcept, KnowledgeSearch } from "@/lib/api";

const search: KnowledgeSearch = {
  query: "quick sort pivot",
  method: "BM25 (k1 1.2, b 0.75) over concept names.",
  unmatched_terms: ["pivotz"],
  allow_unreviewed: true,
  results: [
    {
      slug: "ds.quicksort",
      name: "Quicksort",
      topic_slug: "ds.sorting-searching",
      topic_name: "Sorting and searching",
      trust_status: "imported",
      score: 17.5,
      matched_terms: { pivot: 2.25, quicksort: 7.25 },
      name_match: "quick sort",
      name_bonus: 8,
    },
  ],
};

const concept: KnowledgeConcept = {
  slug: "ds.stack",
  name: "Stack",
  aliases: ["LIFO"],
  definition: "A last-in first-out collection.",
  attributes: { push_cost: "O(1)" },
  difficulty: 1,
  topic_slug: "ds.stacks-queues",
  topic_name: "Stacks and queues",
  trust_status: "imported",
  reviewed_by: null,
  reviewed_on: null,
  content_version: "2026.10.1",
  origin: "knowledge/data-structures/ds.stacks-queues.yaml",
  documents: [
    { kind: "example", title: "Balanced brackets", body: "Push on open.", steps: [], depth: 1 },
  ],
  relations: [
    { kind: "contrasts_with", direction: "out", slug: "ds.queue", name: "Queue" },
    { kind: "requires", direction: "in", slug: "algo.dfs", name: "Depth-first search" },
  ],
  further_reading: [
    { title: "Algorithms", authors: "Sedgewick and Wayne", citation: null, url: null },
  ],
  question_count: 3,
};

describe("SearchResults", () => {
  it("shows the score breakdown, name bonus and unmatched words", () => {
    render(<SearchResults search={search} />);
    const item = screen.getByRole("listitem");
    expect(within(item).getByRole("link", { name: "Quicksort" })).toHaveAttribute(
      "href",
      "/knowledge-base/concepts/ds.quicksort",
    );
    expect(within(item).getByText("17.50")).toBeInTheDocument();
    // Largest contribution first.
    expect(within(item).getByText("quicksort 7.25 + pivot 2.25")).toBeInTheDocument();
    expect(within(item).getByText(/“quick sort” adds 8.00/)).toBeInTheDocument();
    expect(within(item).getByText("Not yet reviewed by a person")).toBeInTheDocument();
    expect(screen.getByText(/"pivotz"/)).toBeInTheDocument();
  });

  it("says plainly when nothing matches", () => {
    render(<SearchResults search={{ ...search, results: [] }} />);
    expect(screen.getByRole("status")).toHaveTextContent("No concept matches this search");
  });
});

describe("ConceptView", () => {
  it("labels unreviewed content and names relations from this concept's side", () => {
    render(<ConceptView concept={concept} />);
    expect(screen.getByRole("note")).toHaveTextContent("not yet been reviewed by a person");
    expect(screen.getByText("Contrasts with:")).toBeInTheDocument();
    expect(screen.getByText("Needed for:")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Depth-first search" })).toHaveAttribute(
      "href",
      "/knowledge-base/concepts/algo.dfs",
    );
    expect(screen.getByText("Push cost")).toBeInTheDocument();
    expect(screen.getByText("Worked example · Introductory")).toBeInTheDocument();
  });

  it("lists a symmetric relation once and reflows prose", () => {
    render(
      <ConceptView
        concept={{
          ...concept,
          relations: [
            ...concept.relations,
            { kind: "contrasts_with", direction: "in", slug: "ds.queue", name: "Queue" },
          ],
          documents: [
            {
              kind: "explanation",
              title: "Why",
              body: "First line\nwraps here.\n\nSecond paragraph.",
              steps: [],
              depth: 2,
            },
          ],
        }}
      />,
    );
    expect(screen.getAllByRole("link", { name: "Queue" })).toHaveLength(1);
    expect(screen.getByText("First line wraps here.")).toBeInTheDocument();
    expect(screen.getByText("Second paragraph.")).toBeInTheDocument();
  });

  it("keeps sentence-ending line breaks in worked examples", () => {
    render(
      <ConceptView
        concept={{
          ...concept,
          documents: [
            {
              kind: "example",
              title: "Steps",
              body: "A = {1, 2}.\nB is the\nsame set.",
              steps: [],
              depth: 1,
            },
          ],
        }}
      />,
    );
    const para = screen.getByText(/A = \{1, 2\}/);
    expect(para.textContent).toBe("A = {1, 2}.\nB is the same set.");
  });

  it("shows the reviewer instead of the warning for reviewed content", () => {
    render(
      <ConceptView
        concept={{
          ...concept,
          trust_status: "verified",
          reviewed_by: "A. Reviewer",
          reviewed_on: "2026-10-20",
        }}
      />,
    );
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(screen.getByText("Reviewed by A. Reviewer on 2026-10-20.")).toBeInTheDocument();
  });
});
