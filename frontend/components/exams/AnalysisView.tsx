"use client";

import Link from "next/link";
import { useState } from "react";

import type { ExamAnalysis, ExamBand, ExamModuleRow, ExamTopicRow } from "@/lib/api";
import { formatMarks } from "@/lib/exams";
import { BAND, MASTERY, Pill } from "@/lib/labels";

function BandPill({ band }: { band: ExamBand | null }) {
  const b = BAND[band ?? "no_score"];
  return <Pill {...b} />;
}

function Bar({ percentage, label }: { percentage: number | null; label: string }) {
  const value = Math.max(0, Math.min(100, percentage ?? 0));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percentage ?? 0}
      className="h-2 w-full overflow-hidden rounded-full bg-canvas"
    >
      <div className="h-full rounded-full bg-accent" style={{ width: `${value}%` }} />
    </div>
  );
}

function Lost({ row }: { row: { lost_by: { label: string; lost: string }[] } }) {
  const shown = row.lost_by.filter((l) => Number(l.lost) > 0);
  if (shown.length === 0) return <span className="text-ink-subtle">No marks lost</span>;
  return (
    <span>
      Lost in{" "}
      {shown.map((l, i) => (
        <span key={l.label}>
          {i > 0 && ", "}Q{l.label} ({formatMarks(l.lost)})
        </span>
      ))}
    </span>
  );
}

function ratio(r: { earned: string; possible: string; percentage: number | null }) {
  return Number(r.possible) > 0
    ? `${formatMarks(r.earned)} of ${formatMarks(r.possible)} marks (${r.percentage}%)`
    : "No counted marks";
}

function TopicLine({ t }: { t: ExamTopicRow }) {
  const m = t.classification ? MASTERY[t.classification] : MASTERY.insufficient_evidence;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-medium">{t.name}</span>
        <span className="text-sm tabular-nums text-ink-muted">{ratio(t)}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
        <BandPill band={t.band} />
        <span className="text-ink-muted">
          Topic mastery: <Pill {...m} />{" "}
          {!t.evidence_sufficient &&
            `(${Math.min(t.direct_observations, t.min_observations)} of ${t.min_observations} direct observations)`}
        </span>
        {t.partial && (
          <span className="text-warn">Partial: some marks shared with other topics</span>
        )}
      </div>
      <p className="mt-1 text-xs text-ink-muted">
        <Lost row={t} />
      </p>
      <p className="mt-1 text-sm">{t.recommendation}</p>
    </li>
  );
}

function ModuleBlock({
  m,
  topics,
  focus,
}: {
  m: ExamModuleRow;
  topics: ExamTopicRow[];
  focus: boolean;
}) {
  const [open, setOpen] = useState(focus);
  const id = `module-${m.id ?? "none"}`;
  const title = m.number !== null ? `Module ${m.number}: ${m.name}` : m.name;
  return (
    <li
      className={`rounded-lg border p-4 ${focus ? "border-warn bg-warn-soft/40" : "border-line bg-surface"}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-medium">
          {title}
          {focus && (
            <span className="ml-2 text-xs font-semibold text-warn">▲ Needs the most attention</span>
          )}
        </h3>
        <span className="text-sm tabular-nums text-ink-muted">{ratio(m)}</span>
      </div>
      <div className="mt-2">
        <Bar percentage={m.percentage} label={`${title}: ${m.percentage ?? 0}% of the marks`} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
        <BandPill band={m.band} />
        <span>Marks lost: {formatMarks(m.marks_lost)}</span>
        {m.evidence === "partial" && <span className="text-warn">Partial evidence</span>}
        <button
          type="button"
          className="ml-auto underline"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
        >
          {open ? "Hide details" : "Show topics and questions"}
        </button>
      </div>
      {open && (
        <div id={id} className="mt-3 border-t border-line pt-3 text-sm">
          <p className="text-xs text-ink-muted">
            Questions: {m.questions.map((q) => `Q${q}`).join(", ") || "none"}. <Lost row={m} />
          </p>
          {m.module_only.length > 0 && (
            <p className="mt-1 text-xs text-ink-muted">
              Mapped to the module only (topic not known):{" "}
              {m.module_only.map((q) => `Q${q}`).join(", ")}. These count for the module but not for
              any topic.
            </p>
          )}
          {m.left_out.length > 0 && (
            <p className="mt-1 text-xs text-warn">
              Not counted yet: {m.left_out.map((q) => `Q${q}`).join(", ")}.
            </p>
          )}
          {topics.length > 0 ? (
            <ul className="mt-2 divide-y divide-line">
              {topics.map((t) => (
                <TopicLine key={t.id} t={t} />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-ink-muted">No topic-level marks in this module.</p>
          )}
        </div>
      )}
    </li>
  );
}

export function AnalysisView({ analysis: a }: { analysis: ExamAnalysis }) {
  const o = a.overall;
  const focus = a.modules.find((m) => m.id !== null && m.id === a.focus_module_id);
  const weak = a.topics.filter((t) => t.band === "needs_attention" || t.band === "developing");
  return (
    <div className="space-y-8">
      {a.breakdown.status !== "confirmed" && (
        <div role="status" className="rounded-lg border border-warn/30 bg-warn-soft p-4 text-sm">
          This breakdown is a draft. The figures below are a preview and do not count towards your
          topics or study plan until you{" "}
          <Link href={`/exam-breakdown/${a.breakdown.id}`} className="underline">
            confirm it
          </Link>
          .
        </div>
      )}

      <section aria-labelledby="overall-heading" className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-lg border border-line bg-surface p-5 lg:col-span-1">
          <h2 id="overall-heading" className="text-sm font-semibold">
            Exam performance
          </h2>
          <p className="mt-2 text-4xl font-semibold tabular-nums">
            {o.percentage === null ? "–" : `${o.percentage}%`}
          </p>
          <p className="mt-1 text-sm text-ink-muted">
            {formatMarks(o.earned)} of {formatMarks(o.possible)} marks, from {o.counted} of{" "}
            {o.total_questions} question(s)
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <BandPill band={o.band} />
            {!o.complete && (
              <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">
                ▲ Partial: some questions are not counted
              </span>
            )}
          </div>
          {a.recorded && (
            <p className="mt-3 text-xs text-ink-muted">
              Recorded result ({a.recorded.assessment_label}):{" "}
              {formatMarks(a.recorded.marks_obtained)} of {formatMarks(a.recorded.max_marks)}.
            </p>
          )}
        </div>
        <div className="rounded-lg border border-line bg-surface p-5 lg:col-span-2">
          <h2 className="text-sm font-semibold">What to focus on</h2>
          {focus ? (
            <p className="mt-2 text-sm">
              <strong>
                Module {focus.number}: {focus.name}
              </strong>{" "}
              cost the most marks ({formatMarks(focus.marks_lost)} lost, {focus.percentage}%
              scored).
            </p>
          ) : (
            <p className="mt-2 text-sm text-ink-muted">
              No module lost marks, or no question is mapped to a module yet.
            </p>
          )}
          {weak.length > 0 && (
            <p className="mt-2 text-sm">
              Weak topics in this exam:{" "}
              {weak.slice(0, 5).map((t, i) => (
                <span key={t.id}>
                  {i > 0 && ", "}
                  {t.name} ({t.percentage}%)
                </span>
              ))}
              .
            </p>
          )}
          <p className="mt-3 text-xs text-ink-muted">
            Exam performance is how you scored on this paper. Topic mastery is ScholarIQ&apos;s
            overall judgement from all evidence, and needs at least{" "}
            {a.topics[0]?.min_observations ?? 5} direct observations before a topic is classified.
            Confirmed exams also update your{" "}
            <Link href="/study-plan" className="underline">
              study plan
            </Link>
            .
          </p>
        </div>
      </section>

      {(o.excluded.length > 0 || o.unmapped.length > 0 || a.warnings.length > 0) && (
        <section
          className="rounded-lg border border-warn/30 bg-warn-soft p-4 text-sm"
          role="status"
        >
          <h2 className="font-medium">Please check</h2>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-muted">
            {o.excluded.map((e) => (
              <li key={e.reason}>
                Not counted ({e.text}): {e.labels.map((q) => `Q${q}`).join(", ")}
              </li>
            ))}
            {o.unmapped.length > 0 && (
              <li>
                Counted in the total but not mapped to a module or topic:{" "}
                {o.unmapped.map((q) => `Q${q}`).join(", ")}
              </li>
            )}
            {a.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="modules-heading">
        <h2 id="modules-heading" className="mb-3 text-sm font-semibold">
          By module
        </h2>
        {a.modules.length === 0 ? (
          <p className="text-sm text-ink-muted">No question is mapped to a module or topic yet.</p>
        ) : (
          <ul className="space-y-3">
            {a.modules.map((m) => (
              <ModuleBlock
                key={m.id ?? "none"}
                m={m}
                focus={m.id !== null && m.id === a.focus_module_id}
                topics={a.topics.filter((t) => t.module_id === m.id)}
              />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="topics-heading">
        <h2 id="topics-heading" className="mb-3 text-sm font-semibold">
          By topic, most marks lost first
        </h2>
        {a.topics.length === 0 ? (
          <p className="text-sm text-ink-muted">No question is mapped to a topic yet.</p>
        ) : (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface px-4">
            {a.topics.map((t) => (
              <TopicLine key={t.id} t={t} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
