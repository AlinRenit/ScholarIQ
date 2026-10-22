"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type Quiz } from "@/lib/api";

/** Start a diagnostic quiz on a topic (or resume an open one) and go to it. */
export function StartQuizButton({
  topic,
  openQuiz = null,
  label,
  variant = "primary",
}: {
  topic: string;
  openQuiz?: string | null;
  label?: string;
  variant?: "primary" | "secondary";
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    if (openQuiz) {
      router.push(`/practice/quiz/${openQuiz}`);
      return;
    }
    setBusy(true);
    setError(null);
    const res = await fetch("/api/practice/quizzes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    if (!res?.ok) {
      setBusy(false);
      setError(errorMessage(body, "Could not start the quiz."));
      return;
    }
    router.push(`/practice/quiz/${(body as Quiz).id}`);
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button variant={variant} onClick={start} disabled={busy}>
        {busy ? "Preparing…" : (label ?? (openQuiz ? "Resume quiz" : "Start quiz"))}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-bad">
          {error}
        </span>
      )}
    </span>
  );
}
