import { describe, expect, it } from "vitest";

import { NAV_ITEMS, isActive } from "@/lib/nav";

describe("navigation", () => {
  it("lists the nine product sections in order", () => {
    expect(NAV_ITEMS.map((n) => n.label)).toEqual([
      "Dashboard",
      "My Academics",
      "Exam Breakdown",
      "Topics",
      "AI-Free Tutor",
      "Practice",
      "Study Plan",
      "Knowledge Base",
      "Settings",
    ]);
  });

  it("matches the dashboard only on the root path", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/topics", "/")).toBe(false);
  });

  it("matches nested routes for a section", () => {
    expect(isActive("/topics/dbms", "/topics")).toBe(true);
    expect(isActive("/topicsx", "/topics")).toBe(false);
  });
});
