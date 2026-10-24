import Link from "next/link";

import { AnalysisView } from "@/components/exams/AnalysisView";
import { Notice, PageHeader } from "@/components/ui";
import type { ExamAnalysis } from "@/lib/api";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Exam analysis" };

export default async function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const analysis = await serverGet<ExamAnalysis>(
    `/api/exam-breakdowns/${encodeURIComponent(id)}/analysis`,
  );
  if (!analysis.ok) {
    return (
      <>
        <PageHeader title="Exam analysis" />
        <Notice tone="error" title="Could not load the analysis.">
          {analysis.message}{" "}
          <Link href="/exam-breakdown" className="underline">
            Back to your breakdowns
          </Link>
        </Notice>
      </>
    );
  }
  const b = analysis.data.breakdown;
  return (
    <>
      <p className="mb-2 flex flex-wrap gap-4 text-sm">
        <Link href="/exam-breakdown" className="text-ink-muted underline">
          ← All exam breakdowns
        </Link>
        <Link href={`/exam-breakdown/${b.id}`} className="text-ink-muted underline">
          Edit questions and marks
        </Link>
      </p>
      <PageHeader
        title={`${b.title}: analysis`}
        description={`${b.subject_name}${b.held_on ? `, ${b.held_on}` : ""}. Performance is total marks scored divided by total marks counted, never an average of percentages.`}
      />
      <AnalysisView analysis={analysis.data} />
    </>
  );
}
