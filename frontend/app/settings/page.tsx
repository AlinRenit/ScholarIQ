import { CapabilityPanel, ReadinessPanel } from "@/components/SystemPanels";
import { Card, Notice, PageHeader } from "@/components/ui";
import { api, load } from "@/lib/api";
import { navItem } from "@/lib/planned";

export const dynamic = "force-dynamic";
export const metadata = { title: "Settings" };

export default async function SettingsPage() {
  const item = navItem("/settings");
  const [readiness, info] = await Promise.all([
    load(() => api.readiness()),
    load(() => api.systemInfo()),
  ]);

  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <div className="grid gap-6 md:grid-cols-2">
        {readiness.data ? (
          <ReadinessPanel readiness={readiness.data} />
        ) : (
          <Notice tone="error" title="System status unavailable">
            {readiness.error}
          </Notice>
        )}
        {info.data && <CapabilityPanel capabilities={info.data.capabilities} />}
        <Card title="Privacy">
          <ul className="space-y-2 text-sm text-ink-muted">
            <li>Marksheets and questions are processed on this server only.</li>
            <li>No data is sent to AI services. The server refuses to start if AI keys are set.</li>
            <li>Uploaded files are kept for a configurable retention period and then deleted.</li>
            <li>A delete-my-data action arrives with marksheet import in Milestone 2.</li>
          </ul>
        </Card>
      </div>
    </>
  );
}
