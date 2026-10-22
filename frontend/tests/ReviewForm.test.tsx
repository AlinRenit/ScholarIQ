import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewForm } from "@/components/academics/ReviewForm";
import type { DocumentDetail, ScaleTemplate } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const doc: DocumentDetail = {
  id: "doc1",
  original_filename: "marks.pdf",
  media_type: "application/pdf",
  size_bytes: 10,
  status: "extracted",
  parser_name: "header_table",
  error: null,
  created_at: "2026-10-22T00:00:00Z",
  file_retained: true,
  analysis: {
    warnings: ["Grades found (A, D)."],
    grades_seen: ["A", "D"],
    context: { semester: 3, exam_type: "regular", exam_name: "Nov 2025" },
    review_threshold: 0.8,
  },
  records: [
    {
      id: "r1",
      row_index: 0,
      source_text: "Data Structures 100 78 A",
      fields: {
        subject_name: "Data Structures",
        marks_obtained: "78",
        max_marks: "100",
        grade: "A",
        status: "present",
        component: "combined",
        semester: 3,
        exam_type: "regular",
      },
      confidence: { subject_name: 1, marks_obtained: 0.6, max_marks: 1, grade: 1 },
      warnings: ["Please check: marks obtained."],
    },
    {
      id: "r2",
      row_index: 1,
      source_text: "Networks AB",
      fields: { subject_name: "Networks", status: "absent", grade: "D", semester: 3 },
      confidence: { subject_name: 1, status: 1 },
      warnings: [],
    },
  ],
};

const templates: ScaleTemplate[] = [
  {
    key: "ugc_cbcs_10",
    name: "10-point",
    description: "O=10…",
    max_points: "10",
    points: { O: "10", A: "8", F: "0" },
  },
];

describe("ReviewForm", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ results_saved: 2 })))),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("highlights uncertain values until edited", () => {
    render(<ReviewForm document={doc} templates={templates} />);
    const marks = screen.getByLabelText(/Marks obtained \(uncertain/);
    expect(marks.className).toContain("border-warn");
    fireEvent.change(marks, { target: { value: "79" } });
    expect(screen.getAllByLabelText(/^Marks obtained$/)[0]).toHaveValue("79");
  });

  it("disables a template that does not cover every grade", () => {
    render(<ReviewForm document={doc} templates={templates} />);
    expect(screen.getByText(/Not usable: has no D/)).toBeInTheDocument();
  });

  it("submits only included rows and never sends marks for absent results", async () => {
    render(<ReviewForm document={doc} templates={templates} />);
    fireEvent.click(screen.getByRole("button", { name: /Confirm and save 2 results/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/academics"));
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/documents/doc1/confirm");
    const body = JSON.parse(String(init.body));
    expect(body.grading).toBeNull();
    expect(body.results).toHaveLength(2);
    expect(body.results[1]).toMatchObject({ subject_name: "Networks", status: "absent" });
    expect(body.results[1].marks_obtained).toBeNull();
    expect(body.results[0]).toMatchObject({ max_marks: "100", semester: 3 });
  });

  it("requires points for every grade in a custom scale", async () => {
    render(<ReviewForm document={doc} templates={templates} />);
    fireEvent.click(screen.getByLabelText("Define the scale myself"));
    fireEvent.click(screen.getByRole("button", { name: /Confirm and save/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter points for: A, D.");
    expect(fetch).not.toHaveBeenCalled();
  });
});
