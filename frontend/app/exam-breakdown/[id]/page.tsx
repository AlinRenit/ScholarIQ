import Link from "next/link";

import { BreakdownEditor } from "@/components/exams/BreakdownEditor";
import { ModuleEditor } from "@/components/exams/ModuleEditor";
import { Notice, PageHeader } from "@/components/ui";
import type {
  AcademicAssessment,
  CurriculumSubject,
  ExamBreakdownDetail,
  SystemInfo,
} from "@/lib/api";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Exam Breakdown" };

export default async function BreakdownPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await serverGet<ExamBreakdownDetail>(
    `/api/exam-breakdowns/${encodeURIComponent(id)}`,
  );
  if (!detail.ok) {
    return (
      <>
        <PageHeader title="Exam Breakdown" />
        <Notice
          tone="error"
          title={detail.status === 404 ? "Breakdown not found" : "Could not load the breakdown."}
        >
          {detail.status === 404 ? "It may have been deleted. " : `${detail.message} `}
          <Link href="/exam-breakdown" className="underline">
            Back to your breakdowns
          </Link>
        </Notice>
      </>
    );
  }
  const [assessments, subjects, info] = await Promise.all([
    serverGet<AcademicAssessment[]>("/api/academics/assessments"),
    serverGet<CurriculumSubject[]>("/api/curriculum/subjects"),
    serverGet<SystemInfo>("/api/system/info"),
  ]);
  const subject = subjects.ok
    ? subjects.data.find((s) => s.id === detail.data.subject_id)
    : undefined;
  const maxMb = info.ok ? Math.floor(info.data.max_upload_bytes / (1024 * 1024)) : 10;

  return (
    <>
      <p className="mb-2 text-sm">
        <Link href="/exam-breakdown" className="text-ink-muted underline">
          ← All exam breakdowns
        </Link>
      </p>
      <PageHeader
        title={detail.data.title}
        description="Check each question, enter your marks and map it to a module or topic. Nothing counts until you confirm."
      />
      <div className="space-y-6">
        {subject?.is_custom && (
          <ModuleEditor key={(subject.modules ?? []).map((m) => m.id).join()} subject={subject} />
        )}
        <BreakdownEditor
          key={`${detail.data.updated_at}-${detail.data.modules.map((m) => m.id).join()}`}
          initial={detail.data}
          assessments={assessments.ok ? assessments.data : []}
          maxMb={maxMb}
        />
      </div>
    </>
  );
}
