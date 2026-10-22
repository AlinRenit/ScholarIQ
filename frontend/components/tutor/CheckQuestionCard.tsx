"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type CheckQuestion, type CheckResult } from "@/lib/api";

/** One knowledge-base question, marked by the server against its stored answer. */
export function CheckQuestionCard({ question }: { question: CheckQuestion }) {
  const [choice, setChoice] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const multiple = question.kind === "multiple_choice";

  async function submit(e: FormEvent) {
    e.preventDefault();
    const response = multiple
      ? { option_index: choice }
      : question.kind === "numeric"
        ? { value: text.trim() }
        : { text };
    setBusy(true);
    setError(null);
    const res = await fetch("/api/tutor/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question.slug, response }),
    }).catch(() => null);
    setBusy(false);
    const body: unknown = await res?.json().catch(() => null);
    if (!res?.ok) {
      setError(errorMessage(body, "Could not check your answer."));
      return;
    }
    setResult(body as CheckResult);
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <p className="text-sm font-medium">{question.prompt}</p>
      {multiple ? (
        <fieldset className="space-y-1.5" disabled={result !== null}>
          <legend className="sr-only">Options</legend>
          {question.options.map((opt, i) => (
            <label key={opt} className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name={question.slug}
                checked={choice === i}
                onChange={() => setChoice(i)}
                className="mt-1"
              />
              <span>{opt}</span>
            </label>
          ))}
        </fieldset>
      ) : (
        <label className="block text-sm">
          <span className="sr-only">Your answer</span>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={result !== null}
            inputMode={question.kind === "numeric" ? "decimal" : "text"}
            placeholder={question.kind === "numeric" ? "A number" : "Your answer"}
            className="block w-full max-w-sm rounded-md border border-line bg-canvas px-3 py-2"
          />
        </label>
      )}
      {result === null ? (
        <Button
          type="submit"
          variant="secondary"
          disabled={busy || (multiple ? choice === null : !text.trim())}
        >
          {busy ? "Checking…" : "Check answer"}
        </Button>
      ) : (
        <div
          role="status"
          className={`rounded-md border p-3 text-sm ${
            result.correct ? "border-ok/30 bg-ok-soft" : "border-warn/30 bg-warn-soft"
          }`}
        >
          <p className="font-medium">
            <span aria-hidden>{result.correct ? "✓ " : "✗ "}</span>
            {result.correct ? "Correct." : `Not quite. The expected answer is: ${result.expected}`}
          </p>
          {result.explanation && <p className="mt-1 text-ink-muted">{result.explanation}</p>}
          <p className="mt-2 text-xs text-ink-muted">
            Practice in the tutor is not recorded and does not change your topic results.
          </p>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-bad">
          {error}
        </p>
      )}
    </form>
  );
}
