"use client";

import Link from "next/link";
import { useState } from "react";

import { StartQuizButton } from "@/components/practice/StartQuizButton";
import { Button } from "@/components/ui-client";
import {
  errorMessage,
  type CurriculumSubject,
  type PlanItem,
  type PlanItemStatus,
  type StudyPlan,
} from "@/lib/api";
import { MASTERY, Pill } from "@/lib/labels";

const TERM_LABELS: Record<string, string> = {
  need: "Need",
  importance: "Importance",
  goal: "Your goal",
  unlocks: "Unlocks",
  recent_result: "Recent quiz",
  study_time: "Study time",
};

const fmt = (n: number) => (Math.round(n * 100) / 100).toString();

function hours(minutes: number) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
}

function GoalPicker({
  subjects,
  goals,
  onChange,
}: {
  subjects: CurriculumSubject[];
  goals: Set<string>;
  onChange: (g: Set<string>) => void;
}) {
  function toggle(slug: string) {
    const next = new Set(goals);
    if (next.has(slug)) next.delete(slug);
    else next.add(slug);
    onChange(next);
  }
  return (
    <details className="rounded-lg border border-line bg-surface p-4 text-sm">
      <summary className="cursor-pointer font-medium">
        Goals{goals.size ? ` (${goals.size} chosen)` : ""}: topics you want to prioritise
      </summary>
      <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {subjects.map((s) => (
          <fieldset key={s.id}>
            <legend className="mb-1 font-medium">{s.name}</legend>
            {s.topics.map((t) => (
              <label key={t.slug} className="flex items-center gap-2 py-0.5">
                <input
                  type="checkbox"
                  checked={goals.has(t.slug)}
                  onChange={() => toggle(t.slug)}
                />
                <span>{t.name}</span>
              </label>
            ))}
          </fieldset>
        ))}
      </div>
    </details>
  );
}

function Item({
  item,
  onStatus,
  busy,
}: {
  item: PlanItem;
  onStatus: (s: PlanItemStatus) => void;
  busy: boolean;
}) {
  const b = item.breakdown;
  const done = item.status === "lesson_completed";
  const skipped = item.status === "skipped";
  return (
    <li className={`rounded-lg border border-line bg-surface p-5 ${skipped ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          <span
            aria-hidden
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-canvas text-sm font-semibold"
          >
            {item.position + 1}
          </span>
          <div className="min-w-0">
            <h3 className="font-semibold">
              <span className="sr-only">Step {item.position + 1}: </span>
              {item.topic_name}
            </h3>
            <p className="text-xs text-ink-muted">
              {b.minutes ? `about ${hours(b.minutes)}` : "no time estimate"}
              {b.goal ? " · your goal" : ""}
            </p>
          </div>
        </div>
        <Pill {...MASTERY[b.classification]} />
      </div>

      {(b.moved_for || b.after.length > 0) && (
        <p className="mt-3 text-sm text-ink-muted">
          {b.moved_for && <>Placed early because {b.moved_for} builds on it. </>}
          {b.after.length > 0 && <>Comes after {b.after.join(", ")}, which it builds on.</>}
        </p>
      )}
      <p className="mt-3 text-sm">{b.next_step}</p>
      {done && (
        <p role="status" className="mt-2 text-sm text-ink-muted">
          <span aria-hidden>✓ </span>Marked as studied. This is your progress note, not evidence:
          the classification changes only when a quiz or test result is added.
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <StartQuizButton topic={item.topic_slug} variant="secondary" label="Take a quiz" />
        <Link
          href={`/knowledge-base/topics/${encodeURIComponent(item.topic_slug)}`}
          className="rounded-md border border-line px-3.5 py-2 text-sm hover:bg-canvas"
        >
          Study material
        </Link>
        {item.status === "pending" ? (
          <>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => onStatus("lesson_completed")}
            >
              Mark as studied
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => onStatus("skipped")}>
              Skip
            </Button>
          </>
        ) : (
          <Button variant="secondary" disabled={busy} onClick={() => onStatus("pending")}>
            {done ? "Undo studied" : "Undo skip"}
          </Button>
        )}
      </div>

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-ink-muted">
          Why this position (priority {fmt(Number(item.priority))})
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-left">
            <thead className="text-ink-muted">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Term
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Reason
                </th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">
                  Value × weight
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  Adds
                </th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(b.terms).map(([k, t]) => (
                <tr key={k} className="border-t border-line align-top">
                  <th scope="row" className="py-1 pr-3 font-medium">
                    {TERM_LABELS[k] ?? k}
                  </th>
                  <td className="py-1 pr-3 text-ink-muted">{t.why}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">
                    {fmt(t.value)} × {fmt(t.weight)}
                  </td>
                  <td className="py-1 text-right tabular-nums">{fmt(t.contribution)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </li>
  );
}

export function StudyPlanView({
  initial,
  subjects,
}: {
  initial: StudyPlan | null;
  subjects: CurriculumSubject[];
}) {
  const [plan, setPlan] = useState(initial);
  const [goals, setGoals] = useState(new Set(initial?.parameters.goal_topics ?? []));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/study-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal_topics: [...goals] }),
    }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(body, "Could not build the plan."));
      return;
    }
    setPlan(body as StudyPlan);
  }

  async function setStatus(item: PlanItem, status: PlanItemStatus) {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/study-plan/items/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(body, "Could not update the plan."));
      return;
    }
    const updated = body as PlanItem;
    setPlan((p) => p && { ...p, items: p.items.map((i) => (i.id === updated.id ? updated : i)) });
  }

  const active = plan?.items.filter((i) => i.status !== "skipped") ?? [];
  const studied = plan?.items.filter((i) => i.status === "lesson_completed").length ?? 0;
  const minutes = active
    .filter((i) => i.status === "pending")
    .reduce((sum, i) => sum + (i.breakdown.minutes ?? 0), 0);
  const counts = new Map<string, number>();
  for (const i of plan?.items ?? []) {
    counts.set(i.breakdown.classification, (counts.get(i.breakdown.classification) ?? 0) + 1);
  }

  return (
    <div className="space-y-6">
      <GoalPicker subjects={subjects} goals={goals} onChange={setGoals} />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={generate} disabled={busy}>
          {busy ? "Working…" : plan ? "Rebuild plan" : "Build my plan"}
        </Button>
        <span className="text-sm text-ink-muted">
          {plan
            ? `Built ${new Date(plan.created_at).toLocaleString("en-GB")} with ${plan.formula_version}. Rebuild after new results or goals.`
            : "Uses your topic classifications, curriculum importance, prerequisites, goals, recent quizzes and study-time estimates."}
        </span>
      </div>
      {error && (
        <p role="alert" className="text-sm text-bad">
          {error}
        </p>
      )}

      {plan && plan.items.length === 0 && (
        <div className="rounded-lg border border-line bg-surface p-5 text-sm">
          <p className="font-medium">Nothing to plan yet.</p>
          <p className="mt-1 text-ink-muted">
            Import a marksheet so your subjects&apos; topics are included, or choose goal topics
            above and rebuild.
          </p>
        </div>
      )}

      {plan && plan.items.length > 0 && (
        <>
          <section
            aria-label="Progress"
            className="grid gap-3 rounded-lg border border-line bg-surface p-5 text-sm sm:grid-cols-3"
          >
            <div>
              <p className="text-ink-muted">Topics in the plan</p>
              <p className="text-2xl font-semibold">{plan.items.length}</p>
              <p className="text-ink-muted">
                {studied} marked as studied
                {plan.items.length - active.length
                  ? `, ${plan.items.length - active.length} skipped`
                  : ""}
              </p>
            </div>
            <div>
              <p className="text-ink-muted">Study time left (estimate)</p>
              <p className="text-2xl font-semibold">{hours(minutes)}</p>
            </div>
            <div className="space-y-1">
              <p className="text-ink-muted">By classification</p>
              <div className="flex flex-wrap gap-1.5">
                {(["needs_attention", "developing", "insufficient_evidence", "strong"] as const)
                  .filter((c) => counts.get(c))
                  .map((c) => (
                    <Pill key={c} {...MASTERY[c]} label={`${MASTERY[c].label}: ${counts.get(c)}`} />
                  ))}
              </div>
            </div>
          </section>
          {plan.parameters.left_out_strong.length > 0 && (
            <p className="text-sm text-ink-muted">
              Left out because your evidence shows them as Strong:{" "}
              {plan.parameters.left_out_strong.join(", ")}. Choose one as a goal to include it.
            </p>
          )}
          <ol className="space-y-3">
            {plan.items.map((i) => (
              <Item key={i.id} item={i} busy={busy} onStatus={(s) => void setStatus(i, s)} />
            ))}
          </ol>
          <details className="rounded-lg border border-line bg-surface p-4 text-sm">
            <summary className="cursor-pointer font-medium">How the order is worked out</summary>
            <div className="mt-2 space-y-2 text-ink-muted">
              <p>
                Each topic gets a priority: need × {plan.parameters.weights.need} + importance ×{" "}
                {plan.parameters.weights.importance} + goal × {plan.parameters.weights.goal} +
                unlocks × {plan.parameters.weights.unlocks} + recent quiz ×{" "}
                {plan.parameters.weights.recent_result} − study time ×{" "}
                {plan.parameters.weights.study_time}.
              </p>
              <p>
                Need comes from the classification (Needs attention 1, Developing 0.6, Insufficient
                evidence 0.5, or 0.7 when a subject mark that includes the topic is low). Importance
                is the curriculum&apos;s 1–5 rating divided by 5. Unlocks counts planned topics that
                build on it. Recent quiz is the share of questions missed in a quiz from the last 30
                days. Study time is the estimate divided by 5 hours.
              </p>
              <p>
                Topics are taken highest priority first, but a topic&apos;s prerequisites in the
                plan always come before it. The score only orders topics; it does not measure
                knowledge.
              </p>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
