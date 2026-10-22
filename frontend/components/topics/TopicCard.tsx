"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type TopicAnalysis } from "@/lib/api";
import { MASTERY, Pill } from "@/lib/labels";

type Mode = "closed" | "topic_exam" | "self_report";

const input = "mt-1 block w-full rounded-md border border-line bg-canvas px-3 py-1.5";

export function TopicCard({
  topic,
  sharedMessages = [],
}: {
  topic: TopicAnalysis;
  /** Subject messages already shown once above the group, so not repeated per card. */
  sharedMessages?: string[];
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("closed");
  const [obtained, setObtained] = useState("");
  const [maximum, setMaximum] = useState("");
  const [questions, setQuestions] = useState("1");
  const [rating, setRating] = useState("3");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const m = MASTERY[topic.classification];

  async function send(path: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    const res = await fetch(path, init).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(await res?.json().catch(() => null), "Could not save the change."));
      return false;
    }
    router.refresh();
    return true;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const body =
      mode === "topic_exam"
        ? { kind: mode, obtained, maximum, questions: Number(questions) }
        : { kind: mode, rating: Number(rating) };
    const ok = await send(`/api/topics/${topic.id}/evidence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (ok) {
      setMode("closed");
      setObtained("");
      setMaximum("");
    }
  }

  return (
    <article className="rounded-lg border border-line bg-surface p-5">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{topic.name}</h3>
          <p className="text-xs text-ink-muted">
            {topic.direct_observations} direct observation(s)
            {topic.estimated_study_minutes
              ? ` · about ${topic.estimated_study_minutes} min to study`
              : ""}
          </p>
        </div>
        <Pill {...m} />
      </header>

      {topic.subject_messages
        .filter((msg) => !sharedMessages.includes(msg))
        .map((msg) => (
          <p key={msg} className="mt-3 rounded-md bg-warn-soft px-3 py-2 text-sm">
            {msg}
          </p>
        ))}

      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-muted">
        {topic.reasons.map((r) => (
          // Indented reasons are the evidence lines under a "Based on" heading.
          <li key={r} className={r.startsWith("  ") ? "ml-4 list-[circle]" : ""}>
            {r.trim()}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-sm">
        <span className="font-medium">Next step: </span>
        {topic.next_action}
      </p>

      {topic.evidence.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-ink-muted">
            Evidence ({topic.evidence.length})
          </summary>
          <ul className="mt-2 divide-y divide-line">
            {topic.evidence.map((e) => (
              <li key={e.id} className="flex items-start justify-between gap-3 py-2">
                <div>
                  <p>{e.description}</p>
                  <p className="text-xs text-ink-muted">
                    {new Date(e.observed_at).toLocaleDateString()}
                  </p>
                </div>
                {e.removable && (
                  <Button
                    variant="secondary"
                    disabled={busy}
                    aria-label={`Remove: ${e.description}`}
                    onClick={() =>
                      void send(`/api/topics/evidence/${e.id}`, {
                        method: "DELETE",
                      })
                    }
                  >
                    Remove
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {mode === "closed" ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setMode("topic_exam")}>
            Add a topic test result
          </Button>
          <Button variant="secondary" onClick={() => setMode("self_report")}>
            Rate my confidence
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-4 space-y-3 rounded-md border border-line p-4">
          {mode === "topic_exam" ? (
            <>
              <p className="text-sm text-ink-muted">
                Enter a test or quiz that covered only this topic. Each question counts as one
                observation.
              </p>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <label>
                  Marks obtained
                  <input
                    required
                    inputMode="decimal"
                    value={obtained}
                    onChange={(e) => setObtained(e.target.value)}
                    className={input}
                  />
                </label>
                <label>
                  Maximum marks
                  <input
                    required
                    inputMode="decimal"
                    value={maximum}
                    onChange={(e) => setMaximum(e.target.value)}
                    className={input}
                  />
                </label>
                <label>
                  Questions
                  <input
                    required
                    type="number"
                    min={1}
                    max={200}
                    value={questions}
                    onChange={(e) => setQuestions(e.target.value)}
                    className={input}
                  />
                </label>
              </div>
            </>
          ) : (
            <label className="block text-sm">
              How confident do you feel about this topic?
              <select value={rating} onChange={(e) => setRating(e.target.value)} className={input}>
                <option value="1">1 – Not at all</option>
                <option value="2">2 – A little</option>
                <option value="3">3 – Somewhat</option>
                <option value="4">4 – Mostly</option>
                <option value="5">5 – Very</option>
              </select>
              <span className="mt-1 block text-xs text-ink-muted">
                Self-reports carry little weight and can never classify a topic by themselves.
              </span>
            </label>
          )}
          {error && (
            <p role="alert" className="text-sm text-bad">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
            <Button variant="secondary" onClick={() => setMode("closed")}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </article>
  );
}
