"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type AcademicAssessment, type CurriculumSubject } from "@/lib/api";

function assessmentLabel(a: AcademicAssessment): string {
  const parts = [
    a.exam_name,
    a.semester !== null ? `Semester ${a.semester}` : null,
    a.exam_type !== "unknown" ? a.exam_type : null,
  ].filter(Boolean);
  return parts.join(", ") || "Exam without a name";
}

export function NewBreakdownForm({
  subjects,
  assessments,
}: {
  subjects: CurriculumSubject[];
  assessments: AcademicAssessment[];
}) {
  const router = useRouter();
  const [assessmentId, setAssessmentId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [title, setTitle] = useState("");
  const [heldOn, setHeldOn] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [existing, setExisting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const assessment = assessments.find((a) => a.id === assessmentId);
  // Subjects of the chosen exam first, then the rest of the curriculum.
  const ordered = useMemo(() => {
    const inExam = new Set(assessment?.results.map((r) => r.subject_id) ?? []);
    const first = subjects.filter((s) => inExam.has(s.id));
    const rest = subjects.filter((s) => !inExam.has(s.id));
    return { first, rest };
  }, [assessment, subjects]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setExisting(null);
    if (!subjectId) {
      setError("Choose the subject of this exam.");
      return;
    }
    setBusy(true);
    const res = await fetch("/api/exam-breakdowns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_id: subjectId,
        assessment_id: assessmentId || null,
        title: title.trim() || null,
        held_on: heldOn || null,
      }),
    }).catch(() => null);
    setBusy(false);
    const body: unknown = await res?.json().catch(() => null);
    if (!res?.ok) {
      setError(errorMessage(body, "Could not create the breakdown."));
      const detail = (body as { detail?: { breakdown_id?: string } } | null)?.detail;
      if (res?.status === 409 && detail?.breakdown_id) setExisting(detail.breakdown_id);
      return;
    }
    router.push(`/exam-breakdown/${(body as { id: string }).id}`);
  }

  const input =
    "w-full rounded border border-line bg-canvas px-2 py-1.5 text-sm focus:border-accent focus:outline-none";
  return (
    <form onSubmit={submit} className="space-y-4" aria-label="New exam breakdown">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Exam</span>
          <select
            value={assessmentId}
            onChange={(e) => setAssessmentId(e.target.value)}
            className={input}
          >
            <option value="">Not in my results (class test, mock exam, …)</option>
            {assessments.map((a) => (
              <option key={a.id} value={a.id}>
                {assessmentLabel(a)}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-ink-muted">
            Linking a recorded exam lets ScholarIQ compare your question marks with the overall mark
            you already confirmed. Nothing in your results is changed.
          </span>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Subject</span>
          <select
            value={subjectId}
            onChange={(e) => setSubjectId(e.target.value)}
            className={input}
            required
          >
            <option value="">Choose a subject</option>
            {ordered.first.length > 0 && (
              <optgroup label="In this exam">
                {ordered.first.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label={ordered.first.length > 0 ? "Other subjects" : "Subjects"}>
              {ordered.rest.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.is_custom ? " (your subject)" : ""}
                </option>
              ))}
            </optgroup>
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Name (optional)</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Mid-term test"
            maxLength={200}
            className={input}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Date (optional)</span>
          <input
            type="date"
            value={heldOn}
            onChange={(e) => setHeldOn(e.target.value)}
            className={input}
          />
        </label>
      </div>
      {error && (
        <p role="alert" className="rounded border border-bad/30 bg-bad-soft px-3 py-2 text-sm">
          {error}{" "}
          {existing && (
            <Link href={`/exam-breakdown/${existing}`} className="underline">
              Open the existing breakdown
            </Link>
          )}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create breakdown"}
      </Button>
    </form>
  );
}
