import { CapabilityPanel } from "@/components/SystemPanels";
import { Card, Notice, PageHeader } from "@/components/ui";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const info = await load(() => api.systemInfo());

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your academic overview will appear here once you import a marksheet."
      />

      {info.error ? (
        <Notice tone="error" title="The ScholarIQ API is not reachable.">
          Start the backend (see the README) and reload this page.
        </Notice>
      ) : (
        <Notice title="No academic records yet">
          Marksheet import arrives in Milestone 2. Until then there is nothing to analyse, and
          this dashboard does not show sample data.
        </Notice>
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card title="How ScholarIQ reaches its conclusions">
          <ul className="space-y-2 text-sm text-ink-muted">
            <li>Marks are parsed locally and confirmed by you before they are used.</li>
            <li>
              A subject score is treated as weak evidence about its topics, not proof of what you
              understand.
            </li>
            <li>Diagnostic quizzes add topic-level evidence over time.</li>
            <li>
              Answers come from a curated knowledge base and deterministic handlers. When the
              knowledge base cannot answer, the tutor says so.
            </li>
          </ul>
        </Card>
        {info.data && <CapabilityPanel capabilities={info.data.capabilities} />}
      </div>
    </>
  );
}
