"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { QuestionCard } from "@/components/exams/QuestionCard";
import { Button } from "@/components/ui-client";
import {
  errorMessage,
  type AcademicAssessment,
  type ExamBreakdownDetail,
  type PaperUploadResult,
} from "@/lib/api";
import {
  blankQuestion,
  clearSuggestions,
  formatMarks,
  fromDetail,
  toPayload,
  validate,
  withTopic,
  type EditorHeader,
  type EditorQuestion,
} from "@/lib/exams";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,.txt";
const field =
  "w-full rounded border border-line bg-canvas px-2 py-1.5 text-sm focus:border-accent focus:outline-none";

type Message = { tone: "ok" | "error" | "warn"; text: string; items?: string[] };

async function send(
  url: string,
  init: RequestInit,
): Promise<{ ok: boolean; status: number; body: unknown }> {
  const res = await fetch(url, init).catch(() => null);
  const body: unknown = await res?.json().catch(() => null);
  return { ok: !!res?.ok, status: res?.status ?? 0, body };
}

export function BreakdownEditor({
  initial,
  assessments,
  maxMb,
}: {
  initial: ExamBreakdownDetail;
  assessments: AcademicAssessment[];
  maxMb: number;
}) {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [detail, setDetail] = useState(initial);
  const start = fromDetail(initial);
  const [header, setHeader] = useState<EditorHeader>(start.header);
  const [questions, setQuestions] = useState<EditorQuestion[]>(start.questions);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const confirmed = detail.status === "confirmed";
  const pendingSuggestions = clearSuggestions(questions);

  function load(d: ExamBreakdownDetail) {
    const next = fromDetail(d);
    setDetail(d);
    setHeader(next.header);
    setQuestions(next.questions);
    setErrors({});
    setDirty(false);
  }

  function edit(next: EditorQuestion[]) {
    setQuestions(next);
    setDirty(true);
  }

  async function upload(file: File) {
    setMessage(null);
    if (
      dirty &&
      !window.confirm("Reading a paper replaces the questions you have not saved. Continue?")
    ) {
      return;
    }
    if (
      questions.length > 0 &&
      !window.confirm("Replace the current questions with the ones read from this paper?")
    ) {
      return;
    }
    setBusy("upload");
    const form = new FormData();
    form.append("file", file);
    // The student already agreed above to replace any questions in the editor.
    const r = await send(`/api/exam-breakdowns/${detail.id}/paper?replace=true`, {
      method: "POST",
      body: form,
    });
    setBusy(null);
    if (!r.ok) {
      setMessage({ tone: "error", text: errorMessage(r.body, "The paper could not be uploaded.") });
      return;
    }
    const out = r.body as PaperUploadResult;
    load(out.breakdown);
    if (out.error) {
      setMessage({
        tone: "error",
        text: `The paper could not be read: ${out.error} You can still enter the questions by hand.`,
      });
    } else if (out.questions_found === 0) {
      setMessage({
        tone: "warn",
        text: "No questions were recognised on this paper. Add them by hand below.",
        items: out.warnings,
      });
    } else {
      setMessage({
        tone: out.warnings.length ? "warn" : "ok",
        text: `Found ${out.questions_found} question(s). Check every number, mark and topic before confirming.`,
        items: out.warnings,
      });
    }
  }

  async function save(andConfirm: boolean): Promise<void> {
    setMessage(null);
    const found = validate(questions);
    setErrors(found);
    const problems = Object.keys(found).length;
    if (!header.title.trim()) {
      setMessage({ tone: "error", text: "Give the exam a name." });
      return;
    }
    if (header.declared_total.trim() && !(Number(header.declared_total) > 0)) {
      setMessage({ tone: "error", text: "The paper total must be a number greater than zero." });
      return;
    }
    if (problems) {
      setMessage({
        tone: "error",
        text: `${problems} question(s) need fixing before they can be saved. The problems are shown next to each question.`,
      });
      return;
    }
    setBusy(andConfirm ? "confirm" : "save");
    const r = await send(`/api/exam-breakdowns/${detail.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(toPayload(header, questions, detail.choice_rules)),
    });
    if (!r.ok) {
      setBusy(null);
      setMessage({ tone: "error", text: errorMessage(r.body, "Could not save the breakdown.") });
      return;
    }
    const saved = r.body as ExamBreakdownDetail;
    load(saved);
    if (!andConfirm) {
      setBusy(null);
      setMessage({
        tone: "ok",
        text: confirmed
          ? "Saved. Your analysis and study plan were updated."
          : "Saved as a draft. Nothing is counted until you confirm.",
      });
      return;
    }
    const c = await send(`/api/exam-breakdowns/${detail.id}/confirm`, { method: "POST" });
    setBusy(null);
    if (!c.ok) {
      setMessage({ tone: "error", text: errorMessage(c.body, "Could not confirm the breakdown.") });
      return;
    }
    router.push(`/exam-breakdown/${detail.id}/analysis`);
    router.refresh();
  }

  async function reopen() {
    setBusy("reopen");
    const r = await send(`/api/exam-breakdowns/${detail.id}/reopen`, { method: "POST" });
    setBusy(null);
    if (!r.ok) {
      setMessage({ tone: "error", text: errorMessage(r.body, "Could not return to draft.") });
      return;
    }
    setDetail({ ...detail, status: "draft" });
    setMessage({
      tone: "ok",
      text: "Returned to draft. This exam no longer counts towards your topics or study plan.",
    });
  }

  async function remove() {
    if (
      !window.confirm("Delete this breakdown and its question marks? Other exams are not affected.")
    ) {
      return;
    }
    setBusy("delete");
    const res = await fetch(`/api/exam-breakdowns/${detail.id}`, { method: "DELETE" }).catch(
      () => null,
    );
    setBusy(null);
    if (!res?.ok) {
      setMessage({ tone: "error", text: "Could not delete the breakdown." });
      return;
    }
    router.push("/exam-breakdown");
    router.refresh();
  }

  function useSuggestions() {
    edit(
      questions.map((q) => {
        const topic = pendingSuggestions.get(q.key);
        return topic ? withTopic(q, topic) : q;
      }),
    );
  }

  const setH = (k: keyof EditorHeader, v: string) => {
    setHeader({ ...header, [k]: v });
    setDirty(true);
  };
  const totalOfQuestions = questions.reduce(
    (sum, q) => (q.is_optional ? sum : sum + (Number(q.max_marks) || 0)),
    0,
  );
  const messageStyle = {
    ok: "border-ok/30 bg-ok-soft",
    warn: "border-warn/30 bg-warn-soft",
    error: "border-bad/30 bg-bad-soft",
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">
            {detail.subject_name}{" "}
            <span
              className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium ${
                confirmed ? "bg-ok-soft text-ok" : "bg-canvas text-ink-muted"
              }`}
            >
              {confirmed ? "✓ Confirmed" : "Draft"}
            </span>
          </h2>
          {confirmed && (
            <Link href={`/exam-breakdown/${detail.id}/analysis`} className="text-sm underline">
              View the analysis
            </Link>
          )}
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Exam name</span>
            <input
              value={header.title}
              onChange={(e) => setH("title", e.target.value)}
              maxLength={200}
              className={field}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Date</span>
            <input
              type="date"
              value={header.held_on}
              onChange={(e) => setH("held_on", e.target.value)}
              className={field}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Paper total (optional)</span>
            <input
              inputMode="decimal"
              value={header.declared_total}
              onChange={(e) => setH("declared_total", e.target.value)}
              placeholder="e.g. 100"
              className={field}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Linked result</span>
            <select
              value={header.assessment_id}
              onChange={(e) => setH("assessment_id", e.target.value)}
              className={field}
            >
              <option value="">Not linked</option>
              {assessments.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.exam_name || (a.semester !== null ? `Semester ${a.semester}` : "Exam")}
                </option>
              ))}
            </select>
          </label>
        </div>
        {detail.recorded && (
          <p className="mt-3 text-xs text-ink-muted">
            Recorded result for {detail.recorded.assessment_label}:{" "}
            {formatMarks(detail.recorded.marks_obtained)} of{" "}
            {formatMarks(detail.recorded.max_marks)}. The question marks are compared with it, never
            written over it.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-dashed border-line bg-surface p-5">
        <h2 className="text-sm font-semibold">Question paper</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Upload the paper (PDF, PNG, JPEG or TXT, up to {maxMb} MB) to read the questions and marks
          automatically, or add the questions by hand. The paper is read on this server; nothing is
          sent anywhere else.
        </p>
        {detail.paper && (
          <p className="mt-2 text-xs text-ink-subtle">
            Current paper: {detail.paper.filename}
            {detail.paper.source ? ` (read as ${detail.paper.source})` : ""}
            {detail.paper.error ? `. It could not be read: ${detail.paper.error}` : ""}
          </p>
        )}
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          aria-label="Choose a question paper file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
            e.target.value = "";
          }}
        />
        <Button
          className="mt-3"
          variant="secondary"
          disabled={busy !== null}
          onClick={() => fileInput.current?.click()}
        >
          {busy === "upload"
            ? "Reading paper…"
            : detail.paper
              ? "Upload a different paper"
              : "Upload question paper"}
        </Button>
      </section>

      {message && (
        <div
          role={message.tone === "error" ? "alert" : "status"}
          className={`rounded-lg border px-4 py-3 text-sm ${messageStyle[message.tone]}`}
        >
          <p>{message.text}</p>
          {message.items && message.items.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-ink-muted">
              {message.items.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {detail.warnings.length > 0 && (
        <div
          className="rounded-lg border border-warn/30 bg-warn-soft px-4 py-3 text-sm"
          role="status"
        >
          <p className="font-medium">Please check</p>
          <ul className="mt-1 list-disc pl-5 text-ink-muted">
            {detail.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <section aria-labelledby="questions-heading">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 id="questions-heading" className="text-sm font-semibold">
            Questions ({questions.length})
            {questions.length > 0 && (
              <span className="ml-2 font-normal text-ink-muted">
                compulsory marks add up to {Math.round(totalOfQuestions * 100) / 100}
              </span>
            )}
          </h2>
          {pendingSuggestions.size > 0 && (
            <Button variant="secondary" onClick={useSuggestions}>
              Use {pendingSuggestions.size} clear topic suggestion(s)
            </Button>
          )}
        </div>
        {questions.length === 0 ? (
          <p className="rounded-lg border border-line bg-surface p-4 text-sm text-ink-muted">
            No questions yet. Upload the paper above or add the first question.
          </p>
        ) : (
          <ol className="space-y-3">
            {questions.map((q, i) => (
              <QuestionCard
                key={q.key}
                question={q}
                index={i}
                topics={detail.topics}
                modules={detail.modules}
                errors={errors[q.key] ?? []}
                onChange={(next) => edit(questions.map((x) => (x.key === q.key ? next : x)))}
                onRemove={() => edit(questions.filter((x) => x.key !== q.key))}
              />
            ))}
          </ol>
        )}
        <Button
          className="mt-3"
          variant="secondary"
          onClick={() => edit([...questions, blankQuestion(questions[questions.length - 1])])}
        >
          Add a question
        </Button>
      </section>

      <div className="sticky bottom-0 -mx-1 flex flex-wrap items-center gap-2 border-t border-line bg-canvas/95 px-1 py-3">
        <Button onClick={() => void save(!confirmed)} disabled={busy !== null}>
          {busy === "confirm" ? "Confirming…" : confirmed ? "Save changes" : "Save and confirm"}
        </Button>
        {!confirmed && (
          <Button variant="secondary" onClick={() => void save(false)} disabled={busy !== null}>
            {busy === "save" ? "Saving…" : "Save draft"}
          </Button>
        )}
        {confirmed && (
          <Button variant="secondary" onClick={() => void reopen()} disabled={busy !== null}>
            Return to draft
          </Button>
        )}
        <Button variant="danger" onClick={() => void remove()} disabled={busy !== null}>
          Delete
        </Button>
        {dirty && <span className="text-xs text-ink-muted">Unsaved changes</span>}
      </div>
    </div>
  );
}
