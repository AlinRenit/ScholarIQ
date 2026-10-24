import Link from "next/link";

import { NewBreakdownForm } from "@/components/exams/NewBreakdownForm";
import { Card, Notice, PageHeader } from "@/components/ui";
import type {
  AcademicAssessment,
  CurriculumSubject,
  ExamBreakdownSummary,
  Profile,
} from "@/lib/api";
import { formatMarks } from "@/lib/exams";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Exam Breakdown" };

export default async function ExamBreakdownPage() {
  const item = navItem("/exam-breakdown");
  const profile = await serverGet<Profile>("/api/profile");
  if (!profile.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        {profile.status === 401 ? (
          <Notice title="Create a profile to get started">
            Go to{" "}
            <Link href="/academics" className="underline">
              My Academics
            </Link>{" "}
            to create a local profile first.
          </Notice>
        ) : (
          <Notice tone="error" title="The ScholarIQ API is not reachable.">
            {profile.message}
          </Notice>
        )}
      </>
    );
  }

  const [breakdowns, subjects, assessments] = await Promise.all([
    serverGet<ExamBreakdownSummary[]>("/api/exam-breakdowns"),
    serverGet<CurriculumSubject[]>("/api/curriculum/subjects"),
    serverGet<AcademicAssessment[]>("/api/academics/assessments"),
  ]);

  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <div className="space-y-8">
        <section aria-labelledby="breakdowns-heading">
          <h2 id="breakdowns-heading" className="mb-3 text-sm font-semibold">
            Your exam breakdowns
          </h2>
          {!breakdowns.ok ? (
            <Notice tone="error" title="Could not load your breakdowns.">
              {breakdowns.message}
            </Notice>
          ) : breakdowns.data.length === 0 ? (
            <Notice title="No exam breakdowns yet">
              Start one below. You can upload the question paper or type the questions in.
            </Notice>
          ) : (
            <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
              {breakdowns.data.map((b) => (
                <li key={b.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <div>
                    <Link href={`/exam-breakdown/${b.id}`} className="font-medium underline">
                      {b.title}
                    </Link>
                    <p className="text-xs text-ink-muted">
                      {b.subject_name}
                      {b.held_on ? `, ${b.held_on}` : ""}, {b.question_count} question(s)
                    </p>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <span className="tabular-nums text-ink-muted">
                      {b.possible && Number(b.possible) > 0
                        ? `${formatMarks(b.earned)} of ${formatMarks(b.possible)} (${b.percentage}%)${
                            b.complete ? "" : ", partial"
                          }`
                        : "No marks counted yet"}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        b.status === "confirmed" ? "bg-ok-soft text-ok" : "bg-canvas text-ink-muted"
                      }`}
                    >
                      {b.status === "confirmed" ? "✓ Confirmed" : "Draft"}
                    </span>
                    {b.status === "confirmed" && (
                      <Link href={`/exam-breakdown/${b.id}/analysis`} className="underline">
                        Analysis
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <Card title="Start a new breakdown">
          {subjects.ok ? (
            <NewBreakdownForm
              subjects={subjects.data}
              assessments={assessments.ok ? assessments.data : []}
            />
          ) : (
            <Notice tone="error" title="Could not load subjects.">
              {subjects.message}
            </Notice>
          )}
        </Card>
      </div>
    </>
  );
}
