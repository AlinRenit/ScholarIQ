"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { StartQuizButton } from "@/components/practice/StartQuizButton";
import { Button } from "@/components/ui-client";
import { errorMessage, type Quiz, type QuizOutcome } from "@/lib/api";
import { MASTERY, Pill, TRUST } from "@/lib/labels";

function Outcome({ title, outcome }: { title: string; outcome: QuizOutcome }) {
  return (
    <div className="space-y-2 rounded-md border border-line bg-canvas p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <Pill {...MASTERY[outcome.classification]} />
      </div>
      <ul className="space-y-1 text-ink-muted">
        {outcome.reasons.map((r, i) => (
          <li key={i} className={r.startsWith("  ") ? "pl-4" : ""}>
            {r.trim()}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Take a diagnostic quiz, or show how a submitted one was marked. */
export function QuizRunner({ initial }: { initial: Quiz }) {
  const [quiz, setQuiz] = useState(initial);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitted = quiz.submitted_at !== null;
  const marked = new Map(quiz.marked.map((m) => [m.slug, m]));
  const unreviewed = quiz.questions.some((q) => q.trust !== "verified");
  const left = quiz.questions.length - Object.keys(answers).length;
  const resultRef = useRef<HTMLElement>(null);
  const justSubmitted = submitted && !initial.submitted_at;

  useEffect(() => {
    if (justSubmitted) resultRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [justSubmitted]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/practice/quizzes/${quiz.id}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(body, "Could not submit the quiz."));
      return;
    }
    setQuiz(body as Quiz);
  }

  return (
    <div className="space-y-6">
      {unreviewed && (
        <div role="note" className="rounded-md border border-warn/30 bg-warn-soft p-3 text-sm">
          <span aria-hidden>! </span>
          {TRUST.imported.label}: these questions and answer keys come from seed content that no one
          has checked yet.
        </div>
      )}

      {submitted && quiz.correct !== null && (
        <section
          ref={resultRef}
          aria-label="Quiz result"
          className="space-y-4 rounded-lg border border-line bg-surface p-5"
        >
          <div>
            <p className="text-sm text-ink-muted">Result</p>
            <p className="text-2xl font-semibold">
              {quiz.correct} of {quiz.questions.length} correct
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              Recorded as topic evidence for {quiz.topic_name}.
            </p>
          </div>
          {quiz.before && quiz.after && (
            <div className="grid gap-3 md:grid-cols-2">
              <Outcome title="Before this quiz" outcome={quiz.before} />
              <Outcome title="After this quiz" outcome={quiz.after} />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <StartQuizButton topic={quiz.topic_slug} label="Take another quiz" />
            <Link href="/study-plan" className="text-sm underline">
              Update my study plan
            </Link>
            <Link href="/topics" className="text-sm underline">
              See all topics
            </Link>
          </div>
          {quiz.available <= quiz.questions.length && (
            <p className="text-xs text-ink-muted">
              This topic has {quiz.available} questions, so another quiz repeats them in a different
              order.
            </p>
          )}
        </section>
      )}

      <form onSubmit={submit} className="space-y-4">
        {quiz.questions.map((q, n) => {
          const m = marked.get(q.slug);
          return (
            <fieldset
              key={q.slug}
              className="space-y-3 rounded-lg border border-line bg-surface p-5"
              disabled={submitted}
            >
              <legend className="sr-only">Question {n + 1}</legend>
              <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                <span>Question {n + 1}</span>
                <span>·</span>
                <span>{q.style === "application" ? "Applying it" : "Understanding"}</span>
                {q.concept && (
                  <>
                    <span>·</span>
                    <span>{q.concept}</span>
                  </>
                )}
              </div>
              <p className="font-medium">{q.prompt}</p>
              <div className="space-y-1.5">
                {q.options.map((opt, i) => {
                  const isRight = m && i === m.correct_option;
                  const isWrongPick = m && i === m.chosen && !m.correct;
                  return (
                    <label
                      key={i}
                      className={`flex items-start gap-2 rounded-md px-2 py-1.5 text-sm ${
                        isRight ? "bg-ok-soft" : isWrongPick ? "bg-bad-soft" : ""
                      }`}
                    >
                      <input
                        type="radio"
                        name={q.slug}
                        className="mt-1"
                        checked={m ? m.chosen === i : answers[q.slug] === i}
                        onChange={() => setAnswers((a) => ({ ...a, [q.slug]: i }))}
                      />
                      <span>
                        {opt}
                        {isRight && (
                          <span className="ml-2 font-medium text-ok">✓ correct answer</span>
                        )}
                        {isWrongPick && (
                          <span className="ml-2 font-medium text-bad">✗ your answer</span>
                        )}
                      </span>
                    </label>
                  );
                })}
              </div>
              {m && (
                <p className="text-sm text-ink-muted">
                  <span className="font-medium text-ink">Why: </span>
                  {m.explanation}
                </p>
              )}
            </fieldset>
          );
        })}

        {!submitted && (
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={busy || left > 0}>
              {busy ? "Marking…" : "Submit answers"}
            </Button>
            <span className="text-sm text-ink-muted">
              {left > 0
                ? `${left} question(s) left to answer.`
                : "Your result will be recorded as evidence for this topic."}
            </span>
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-bad">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}
