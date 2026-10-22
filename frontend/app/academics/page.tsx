import { CreateProfile } from "@/components/academics/CreateProfile";
import { DocumentList } from "@/components/academics/DocumentList";
import { ResultsTable } from "@/components/academics/ResultsTable";
import { UploadCard } from "@/components/academics/UploadCard";
import { Notice, PageHeader } from "@/components/ui";
import type { AcademicAssessment, DocumentSummary, Profile, SystemInfo } from "@/lib/api";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "My Academics" };

export default async function AcademicsPage() {
  const item = navItem("/academics");
  const profile = await serverGet<Profile>("/api/profile");

  if (!profile.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        {profile.status === 401 ? (
          <CreateProfile />
        ) : (
          <Notice tone="error" title="The ScholarIQ API is not reachable.">
            {profile.message}
          </Notice>
        )}
      </>
    );
  }

  const [docs, assessments, info] = await Promise.all([
    serverGet<DocumentSummary[]>("/api/documents"),
    serverGet<AcademicAssessment[]>("/api/academics/assessments"),
    serverGet<SystemInfo>("/api/system/info"),
  ]);
  const maxMb = info.ok ? Math.floor(info.data.max_upload_bytes / (1024 * 1024)) : 10;

  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <div className="space-y-8">
        <UploadCard maxMb={maxMb} />

        {docs.ok && docs.data.length > 0 && (
          <section>
            <h2 className="mb-3 text-sm font-semibold">Uploads</h2>
            <DocumentList documents={docs.data} />
          </section>
        )}

        <section>
          <h2 className="mb-3 text-sm font-semibold">Confirmed results</h2>
          {assessments.ok && assessments.data.length > 0 ? (
            <ResultsTable assessments={assessments.data} />
          ) : (
            <Notice title="No confirmed results yet">
              Results appear here after you review and confirm an import. Subject analysis and
              topic evidence arrive in Milestone 3.
            </Notice>
          )}
        </section>
      </div>
    </>
  );
}
