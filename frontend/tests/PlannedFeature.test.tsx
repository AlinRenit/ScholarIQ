import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlannedFeature } from "@/components/PlannedFeature";
import { NAV_ITEMS } from "@/lib/nav";

const tutor = NAV_ITEMS.find((n) => n.href === "/tutor")!;

describe("PlannedFeature", () => {
  it("states the milestone and does not pretend the feature works", () => {
    render(
      <PlannedFeature
        item={tutor}
        capability={{ key: "tutor", label: "Tutor", milestone: 5, status: "planned" }}
        plannedScope={["Answer questions"]}
      />,
    );
    expect(screen.getByRole("heading", { name: "AI-Free Tutor" })).toBeInTheDocument();
    expect(screen.getByText(/Milestone 5/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing here is simulated/)).toBeInTheDocument();
  });

  it("handles an unreachable API", () => {
    render(<PlannedFeature item={tutor} capability={undefined} plannedScope={[]} />);
    expect(screen.getByText(/could not be reached/)).toBeInTheDocument();
  });
});
