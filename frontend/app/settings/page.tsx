import { AccountSecurity } from "@/components/account/AccountSecurity";
import { DeleteMyData } from "@/components/DeleteMyData";
import { CapabilityPanel, ReadinessPanel } from "@/components/SystemPanels";
import { Card, Notice, PageHeader } from "@/components/ui";
import { api, load, type Profile } from "@/lib/api";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Settings" };

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ deleted?: string }>;
}) {
  const deleted = (await searchParams).deleted === "1";
  const item = navItem("/settings");
  const [readiness, info, profile] = await Promise.all([
    load(() => api.readiness()),
    load(() => api.systemInfo()),
    serverGet<Profile>("/api/profile"),
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
            <li>Extracted text is discarded once you confirm an import.</li>
          </ul>
        </Card>
        {profile.ok && (
          <Card title="Sign-in and security">
            <AccountSecurity profile={profile.data} />
          </Card>
        )}
        <Card title="Your data">
          {profile.ok ? (
            <div className="space-y-3 text-sm text-ink-muted">
              <p>
                Signed in as{" "}
                <span className="font-medium text-ink">{profile.data.display_name}</span>. Deleting
                removes your profile, uploaded files and every academic record.
              </p>
              <DeleteMyData />
            </div>
          ) : (
            <p role="status" className="text-sm text-ink-muted">
              {deleted ? "All your data has been deleted." : "No profile on this browser."}
            </p>
          )}
        </Card>
      </div>
    </>
  );
}
