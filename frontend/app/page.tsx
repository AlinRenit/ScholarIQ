import Link from "next/link";

import { SemesterTrendChart, SubjectScoreChart } from "@/components/dashboard/Charts";
import { StatTile } from "@/components/dashboard/StatTile";
import { ExamSummaryCard } from "@/components/exams/ExamSummaryCard";
import { Card, Notice, PageHeader } from "@/components/ui";
import type {
  ExamSummary,
  MasteryClass,
  Overview,
  Profile,
  SubjectAnalysis,
  TopicAnalysis,
} from "@/lib/api";
import { BAND, MASTERY, Pill } from "@/lib/labels";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";

const MASTERY_ORDER: MasteryClass[] = [
  "needs_attention",
  "developing",
  "strong",
  "insufficient_evidence",
];

function semesterLabel(s: number | null) {
  return s === null ? "No semester" : `Sem ${s}`;
}

function SubjectList({ subjects, empty }: { subjects: SubjectAnalysis[]; empty: string }) {
  if (subjects.length === 0) return <p className="text-sm text-ink-muted">{empty}</p>;
  return (
    <ul className="divide-y divide-line text-sm">
      {subjects.map((s) => (
        <li key={s.id} className="flex items-center justify-between gap-3 py-2">
          <span>{s.name}</span>
          <span className="tabular-nums text-ink-muted">
            {s.latest ? `${s.latest.percent}%` : "No score"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default async function DashboardPage() {
  const profile = await serverGet<Profile>("/api/profile");
  if (!profile.ok) {
    return (
      <>
        <PageHeader title="Dashboard" />
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

  const [overview, topics, exams] = await Promise.all([
    serverGet<Overview>("/api/analytics/overview"),
    serverGet<TopicAnalysis[]>("/api/topics"),
    serverGet<ExamSummary>("/api/exam-breakdowns/summary"),
  ]);
  if (!overview.ok) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Notice tone="error" title="Could not load your analysis.">
          {overview.message}
        </Notice>
      </>
    );
  }
  const o = overview.data;

  if (o.counts.results === 0) {
    return (
      <>
        <PageHeader title="Dashboard" description={`Welcome, ${profile.data.display_name}.`} />
        <Notice title="No confirmed results yet">
          Import a marksheet in{" "}
          <Link href="/academics" className="underline">
            My Academics
          </Link>{" "}
          and confirm it. The dashboard only shows figures computed from results you have confirmed.
        </Notice>
        {exams.ok && exams.data.confirmed > 0 && (
          <div className="mt-6">
            <ExamSummaryCard summary={exams.data} />
          </div>
        )}
      </>
    );
  }

  const bands = o.policy.subject_bands;
  const markBars = o.subjects
    .filter((s) => s.latest?.basis === "marks")
    .map((s) => ({
      name: s.name,
      percent: s.latest!.percent,
      band: BAND[s.band].label,
    }));
  const gradeOnly = o.subjects.filter((s) => s.latest && s.latest.basis !== "marks").length;
  const trendPoints = o.semesters
    .filter((s) => s.semester !== null && s.marks_percentage.value !== null)
    .map((s) => ({
      semester: semesterLabel(s.semester),
      percent: s.marks_percentage.value!,
      counted: s.marks_percentage.counted,
    }));
  const byScore = (a: SubjectAnalysis, b: SubjectAnalysis) =>
    (b.latest?.percent ?? 0) - (a.latest?.percent ?? 0);
  const strong = o.subjects.filter((s) => s.band === "strong").sort(byScore);
  const attention = o.subjects
    .filter((s) => s.band === "needs_attention")
    .sort((a, b) => byScore(b, a));
  const topicCounts = new Map<MasteryClass, number>();
  if (topics.ok) {
    for (const t of topics.data) {
      topicCounts.set(t.classification, (topicCounts.get(t.classification) ?? 0) + 1);
    }
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Computed from ${o.counts.results} confirmed results across ${o.counts.subjects} subjects. Every figure below says what it counts.`}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          label="Overall percentage"
          value={o.overall.marks_percentage.value}
          suffix="%"
          agg={o.overall.marks_percentage}
          detail="Total marks obtained ÷ total maximum marks, latest attempt per subject."
        />
        <StatTile
          label="Credit-weighted percentage"
          value={o.overall.credit_weighted_percentage.value}
          suffix="%"
          agg={o.overall.credit_weighted_percentage}
          detail="Each subject's percentage weighted by its credits."
        />
        <StatTile
          label="GPA"
          value={o.overall.gpa.value}
          agg={o.overall.gpa}
          detail="Credit-weighted grade points on your marksheet's own scale."
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Card title="Latest score by subject (% of maximum marks)">
            {markBars.length > 0 ? (
              <>
                <SubjectScoreChart
                  bars={markBars}
                  strongAt={bands.strong_at}
                  attentionBelow={bands.attention_below}
                />
                <p className="mt-2 text-xs text-ink-muted">
                  Vertical lines mark {bands.attention_below * 100}% (below this a subject may need
                  attention) and {bands.strong_at * 100}% (strong exam result).
                  {gradeOnly > 0 &&
                    ` ${gradeOnly} subject(s) with only grades are listed below but not charted, because grade points and marks are not mixed.`}
                </p>
              </>
            ) : (
              <p className="text-sm text-ink-muted">
                None of your results include marks, so there is nothing to chart on a marks scale.
                Grade-based results still appear in the lists below.
              </p>
            )}
          </Card>
        </div>
        <div className="lg:col-span-2">
          <Card title="Semester trend (% of maximum marks)">
            {trendPoints.length >= 2 ? (
              <SemesterTrendChart points={trendPoints} />
            ) : (
              <p className="text-sm text-ink-muted">
                A trend needs marks from at least two semesters.
              </p>
            )}
            <p className="mt-2 text-sm text-ink-muted">{o.trend.explanation}</p>
          </Card>
        </div>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card title="Strongest exam results">
          <SubjectList
            subjects={strong}
            empty={`No subject is at or above ${bands.strong_at * 100}% yet.`}
          />
        </Card>
        <Card title="Subjects that may need attention">
          <SubjectList
            subjects={attention}
            empty={`No subject is below ${bands.attention_below * 100}%.`}
          />
          {attention.length > 0 && (
            <p className="mt-3 text-xs text-ink-muted">
              A subject score alone does not say which topics are weak. See{" "}
              <Link href="/topics" className="underline">
                Topics
              </Link>{" "}
              for what the evidence does and does not show.
            </p>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card title="Topics">
          {topics.ok ? (
            <>
              <ul className="flex flex-wrap gap-2">
                {MASTERY_ORDER.map((m) => (
                  <li key={m}>
                    <Pill
                      {...MASTERY[m]}
                      label={`${MASTERY[m].label}: ${topicCounts.get(m) ?? 0}`}
                    />
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-sm text-ink-muted">
                A topic is classified only after it has at least five direct observations, such as
                topic tests or quiz answers. Until then it is shown as insufficient evidence.{" "}
                <Link href="/topics" className="underline">
                  Open Topics
                </Link>
              </p>
            </>
          ) : (
            <p className="text-sm text-ink-muted">{topics.message}</p>
          )}
        </Card>
        <Card title="Gaps in your data">
          {o.data_gaps.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
              {o.data_gaps.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-muted">No gaps found in your confirmed results.</p>
          )}
        </Card>
      </div>

      {exams.ok && (
        <div className="mt-6">
          <ExamSummaryCard summary={exams.data} />
        </div>
      )}

      <details className="mt-6 rounded-lg border border-line bg-surface p-5">
        <summary className="cursor-pointer text-sm font-semibold">
          How these figures are calculated (rules version {o.policy.version})
        </summary>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-muted">
          {o.methodology.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </details>
    </>
  );
}
