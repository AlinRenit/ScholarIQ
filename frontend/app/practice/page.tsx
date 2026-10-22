import Link from "next/link";

import { StartQuizButton } from "@/components/practice/StartQuizButton";
import { Notice, PageHeader } from "@/components/ui";
import type { PracticeTopic, Profile } from "@/lib/api";
import { MASTERY, Pill } from "@/lib/labels";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Practice" };

const date = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export default async function PracticePage() {
  const item = navItem("/practice");
  const profile = await serverGet<Profile>("/api/profile");
  if (!profile.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        {profile.status === 401 ? (
          <Notice title="Create a profile to take quizzes">
            Quiz results are stored as evidence about your topics, so they need a profile. Go to{" "}
            <Link href="/academics" className="underline">
              My Academics
            </Link>{" "}
            to create one.
          </Notice>
        ) : (
          <Notice tone="error" title="The ScholarIQ API is not reachable.">
            {profile.message}
          </Notice>
        )}
      </>
    );
  }

  const topics = await serverGet<PracticeTopic[]>("/api/practice/topics");
  if (!topics.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        <Notice tone="error" title="Could not load quiz topics.">
          {topics.message}
        </Notice>
      </>
    );
  }

  const recent = topics.data
    .flatMap((t) => t.quizzes.map((q) => ({ ...q, topic: t.name, slug: t.slug })))
    .sort((a, b) => b.submitted_at.localeCompare(a.submitted_at))
    .slice(0, 5);
  const groups = new Map<string, PracticeTopic[]>();
  for (const t of topics.data) {
    const key = t.subjects[0] ?? "Other";
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }

  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <div className="mb-8 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-line bg-surface p-5 text-sm text-ink-muted">
          <p>
            Each quiz has up to five questions from the topic, mixing understanding and applying it,
            easiest first. Questions you have seen least come first, and answer options are
            shuffled. After you submit, every answer is explained and the result is added to the
            topic&apos;s evidence; five answered questions are enough to classify a topic.
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface p-5">
          <h2 className="text-sm font-semibold">Recent results</h2>
          {recent.length === 0 ? (
            <p className="mt-2 text-sm text-ink-muted">No quizzes taken yet.</p>
          ) : (
            <ul className="mt-2 space-y-1.5 text-sm">
              {recent.map((q) => (
                <li key={q.id} className="flex justify-between gap-3">
                  <Link href={`/practice/quiz/${q.id}`} className="truncate underline">
                    {q.topic}
                  </Link>
                  <span className="shrink-0 text-ink-muted">
                    {q.correct} of {q.total} · {date(q.submitted_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="space-y-8">
        {[...groups.entries()].map(([subject, list]) => (
          <section key={subject}>
            <h2 className="mb-3 text-lg font-semibold">{subject}</h2>
            <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
              {list.map((t) => {
                const last = t.quizzes[0];
                return (
                  <li
                    key={t.slug}
                    className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{t.name}</span>
                        <Pill {...MASTERY[t.classification]} />
                      </div>
                      <p className="text-xs text-ink-muted">
                        {t.questions} questions ·{" "}
                        {last
                          ? `last quiz ${last.correct} of ${last.total} on ${date(last.submitted_at)}` +
                            (t.quizzes.length > 1 ? ` · ${t.quizzes.length} quizzes taken` : "")
                          : "not tried yet"}
                      </p>
                    </div>
                    <StartQuizButton
                      topic={t.slug}
                      openQuiz={t.open_quiz}
                      variant={t.quizzes.length ? "secondary" : "primary"}
                    />
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
