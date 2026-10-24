import Link from "next/link";

import { ExamSummaryCard } from "@/components/exams/ExamSummaryCard";
import { SubjectMapping } from "@/components/topics/SubjectMapping";
import { TopicCard } from "@/components/topics/TopicCard";
import { Notice, PageHeader } from "@/components/ui";
import type {
  CurriculumSubject,
  ExamSummary,
  MasteryClass,
  Overview,
  Profile,
  TopicAnalysis,
} from "@/lib/api";
import { MASTERY, Pill } from "@/lib/labels";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Topics" };

const LEGEND: MasteryClass[] = ["strong", "developing", "needs_attention", "insufficient_evidence"];

export default async function TopicsPage() {
  const item = navItem("/topics");
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
            to create a local profile and import a marksheet.
          </Notice>
        ) : (
          <Notice tone="error" title="The ScholarIQ API is not reachable.">
            {profile.message}
          </Notice>
        )}
      </>
    );
  }

  const [topics, overview, curriculum, exams] = await Promise.all([
    serverGet<TopicAnalysis[]>("/api/topics"),
    serverGet<Overview>("/api/analytics/overview"),
    serverGet<CurriculumSubject[]>("/api/curriculum/subjects"),
    serverGet<ExamSummary>("/api/exam-breakdowns/summary"),
  ]);
  const unmapped = overview.ok
    ? overview.data.subjects.filter((s) => s.is_custom && s.mapped_topics === 0)
    : [];
  const curriculumSubjects = curriculum.ok ? curriculum.data.filter((c) => !c.is_custom) : [];
  if (!topics.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        <Notice tone="error" title="Could not load topics.">
          {topics.message}
        </Notice>
      </>
    );
  }

  // The API sorts by subject then classification; keep that order while grouping.
  const groups = new Map<string, TopicAnalysis[]>();
  for (const t of topics.data) {
    const key = t.subjects[0]?.name ?? "Other";
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }

  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <div className="mb-6 rounded-lg border border-line bg-surface p-4 text-sm text-ink-muted">
        <p>
          Each topic is classified only from topic-level evidence: at least five observations such
          as topic test questions or quiz answers. A subject mark counts as one weak observation,
          because a single exam score cannot show which topics you know. Rules are versioned and
          listed under each topic.
        </p>
        <ul className="mt-3 flex flex-wrap gap-2">
          {LEGEND.map((m) => (
            <li key={m}>
              <Pill {...MASTERY[m]} />
            </li>
          ))}
        </ul>
      </div>

      {exams.ok && exams.data.confirmed > 0 && (
        <div className="mb-10">
          <ExamSummaryCard summary={exams.data} />
        </div>
      )}

      {unmapped.length > 0 && curriculumSubjects.length > 0 && (
        <section className="mb-10">
          <h2 className="mb-1 text-lg font-semibold">Subjects without topics</h2>
          <p className="mb-3 text-sm text-ink-muted">
            These subjects have results but no topics, so they do not appear below.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {unmapped.map((s) => (
              <SubjectMapping key={s.id} subject={s} curriculum={curriculumSubjects} />
            ))}
          </div>
        </section>
      )}

      {groups.size === 0 ? (
        <Notice title="No topics yet">
          Topics appear once your confirmed subjects are mapped to the curriculum. Import a
          marksheet in{" "}
          <Link href="/academics" className="underline">
            My Academics
          </Link>
          .
        </Notice>
      ) : (
        <div className="space-y-10">
          {[...groups].map(([subject, list]) => {
            // A subject's message is identical for each of its topics; show it once.
            const shared = list[0]!.subject_messages.filter((m) =>
              list.every((t) => t.subject_messages.includes(m)),
            );
            return (
              <section key={subject}>
                <h2 className="text-lg font-semibold">{subject}</h2>
                {shared.map((m) => (
                  <p key={m} className="mt-2 rounded-md bg-warn-soft px-3 py-2 text-sm">
                    {m}
                  </p>
                ))}
                <div className="mt-3 grid gap-4 lg:grid-cols-2">
                  {list.map((t) => (
                    <TopicCard key={t.id} topic={t} sharedMessages={shared} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
