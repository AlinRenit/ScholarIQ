import Link from "next/link";

import { Card } from "@/components/ui";
import type { ExamSummary } from "@/lib/api";
import { formatMarks } from "@/lib/exams";

/** Cross-exam view of confirmed question-level marks: the module that cost the
 * most marks, the weakest topics and whether a weakness repeats. */
export function ExamSummaryCard({ summary: s }: { summary: ExamSummary }) {
  if (s.confirmed === 0) {
    return (
      <Card title="Exam questions">
        <p className="text-sm text-ink-muted">
          {s.drafts > 0
            ? `You have ${s.drafts} draft exam breakdown(s). Confirm one to see which modules and topics cost you marks.`
            : "Break an exam down by question to see which modules and topics cost you marks."}{" "}
          <Link href="/exam-breakdown" className="underline">
            Open Exam Breakdown
          </Link>
        </p>
      </Card>
    );
  }
  const focus = [...s.modules]
    .filter((m) => Number(m.possible) > 0)
    .sort((a, b) => Number(b.marks_lost) - Number(a.marks_lost))[0];
  const weak = s.topics.filter((t) => Number(t.marks_lost) > 0).slice(0, 5);
  return (
    <Card title={`Exam questions (${s.confirmed} confirmed exam${s.confirmed === 1 ? "" : "s"})`}>
      {focus && Number(focus.marks_lost) > 0 ? (
        <p className="text-sm">
          Module needing the most attention:{" "}
          <strong>
            {focus.subject_name}, Module {focus.number}: {focus.name}
          </strong>{" "}
          ({formatMarks(focus.marks_lost)} marks lost, {focus.percentage}% scored across{" "}
          {focus.exams} exam{focus.exams === 1 ? "" : "s"}).
        </p>
      ) : (
        <p className="text-sm text-ink-muted">No module has lost marks in your confirmed exams.</p>
      )}
      {weak.length > 0 && (
        <ul className="mt-3 divide-y divide-line text-sm">
          {weak.map((t) => (
            <li
              key={t.topic_id}
              className="flex flex-wrap items-baseline justify-between gap-2 py-2"
            >
              <span>
                {t.name}
                {t.repeated && (
                  <span className="ml-2 text-xs font-medium text-warn">
                    ▲ Weak in {t.weak_in_exams} exams
                  </span>
                )}
              </span>
              <span className="text-xs tabular-nums text-ink-muted">
                {formatMarks(t.marks_lost)} lost ({t.percentage}%)
                {t.plan_position !== null && `, #${t.plan_position} in study plan`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-ink-muted">
        These are exam results, not topic mastery. They feed your{" "}
        <Link href="/study-plan" className="underline">
          study plan
        </Link>{" "}
        as topic evidence.{" "}
        <Link href="/exam-breakdown" className="underline">
          All breakdowns
        </Link>
      </p>
    </Card>
  );
}
