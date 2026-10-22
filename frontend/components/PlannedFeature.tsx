import { Card, Notice, PageHeader } from "@/components/ui";
import type { Capability } from "@/lib/api";
import type { NavItem } from "@/lib/nav";

/**
 * Honest placeholder for a section whose backend capability is not built yet.
 * It never shows sample data or a fake success state.
 */
export function PlannedFeature({
  item,
  capability,
  plannedScope,
}: {
  item: NavItem;
  capability: Capability | undefined;
  plannedScope: string[];
}) {
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <Notice title="Not available yet">
        {capability
          ? `This section arrives in Milestone ${capability.milestone} (${capability.label}). Nothing here is simulated.`
          : "The API could not be reached, so feature availability is unknown."}
      </Notice>
      <div className="mt-6">
        <Card title="What this section will do">
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
            {plannedScope.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
