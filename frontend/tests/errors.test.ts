import { describe, expect, it } from "vitest";

import { errorMessage } from "@/lib/api";

describe("errorMessage", () => {
  it("passes through string details", () => {
    expect(errorMessage({ detail: "Too many uploads" }, "x")).toBe("Too many uploads");
  });

  it("reads conflict objects", () => {
    expect(errorMessage({ detail: { message: "Already uploaded", document_id: "1" } }, "x")).toBe(
      "Already uploaded",
    );
  });

  it("formats validation errors with row numbers", () => {
    const body = {
      detail: [
        {
          loc: ["body", "results", 2],
          msg: "Value error, X: marks obtained exceed maximum marks",
        },
      ],
    };
    expect(errorMessage(body, "x")).toBe("Row 3: X: marks obtained exceed maximum marks");
  });

  it("falls back for unknown shapes", () => {
    expect(errorMessage(null, "fallback")).toBe("fallback");
  });
});
