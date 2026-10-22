"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ACTIONS, AnswerView, SuggestionButtons } from "@/components/tutor/AnswerView";
import { Button } from "@/components/ui-client";
import {
  errorMessage,
  type AskResult,
  type ConversationDetail,
  type ConversationSummary,
  type Suggestion,
  type TutorAction,
  type TutorInfo,
  type TutorMessage,
} from "@/lib/api";

// One example per kind of question the tutor handles, all answerable from the
// bundled knowledge base.
export const STARTERS: Suggestion[] = [
  { label: "What is a stack?", action: "ask", query: "What is a stack?" },
  {
    label: "Process vs thread",
    action: "ask",
    query: "What is the difference between a process and a thread?",
  },
  {
    label: "Steps to normalise to 3NF",
    action: "ask",
    query: "steps to normalise a relation to 3NF",
  },
  { label: "Solve T(n) = 2T(n/2) + n", action: "ask", query: "Solve T(n) = 2T(n/2) + n" },
  {
    label: "What to learn before dynamic programming",
    action: "ask",
    query: "prerequisites for dynamic programming",
  },
  { label: "Quiz me on deadlocks", action: "ask", query: "quiz me on deadlocks" },
  { label: "What should I focus on?", action: "ask", query: "What should I focus on?" },
];

const MAX_LENGTH = 4000;

type Pending = { text: string; action: TutorAction | null; meaning?: string | null };

function actionLabel(action: TutorAction | null): string {
  return ACTIONS.find((a) => a.action === action)?.label ?? "Continue";
}

export function TutorWorkspace({
  initialConversations,
  info,
}: {
  initialConversations: ConversationSummary[];
  info: TutorInfo | null;
}) {
  const [conversations, setConversations] = useState(initialConversations);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<TutorMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [error, setError] = useState<{ message: string; retry: Pending | null } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages.length, pending]);

  async function refreshList() {
    const res = await fetch("/api/tutor/conversations").catch(() => null);
    if (res?.ok) setConversations((await res.json()) as ConversationSummary[]);
  }

  async function open(id: string) {
    setLoadingConversation(true);
    setError(null);
    const res = await fetch(`/api/tutor/conversations/${encodeURIComponent(id)}`).catch(() => null);
    setLoadingConversation(false);
    if (!res?.ok) {
      setError({ message: "Could not open that conversation.", retry: null });
      if (res?.status === 404) void refreshList();
      return;
    }
    const conv = (await res.json()) as ConversationDetail;
    setActive(conv.id);
    setMessages(conv.messages);
  }

  function startNew() {
    setActive(null);
    setMessages([]);
    setError(null);
    setDraft("");
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this conversation? This cannot be undone.")) return;
    const res = await fetch(`/api/tutor/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }).catch(() => null);
    if (!res || (res.status !== 204 && res.status !== 404)) {
      setError({ message: "Could not delete the conversation.", retry: null });
      return;
    }
    setConversations((cs) => cs.filter((c) => c.id !== id));
    if (id === active) startNew();
  }

  async function send(p: Pending) {
    if (pending) return;
    setPending(p);
    setError(null);
    const res = await fetch("/api/tutor/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: p.text,
        conversation_id: active,
        action: p.action,
        meaning: p.meaning ?? null,
      }),
    }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    setPending(null);
    if (!res?.ok) {
      const fallback = res ? "The tutor could not answer." : "The ScholarIQ API is not reachable.";
      setError({ message: errorMessage(body, fallback), retry: p });
      if (p.action === null) setDraft(p.text);
      return;
    }
    const result = body as AskResult;
    const now = new Date().toISOString();
    setMessages((ms) => [
      ...ms,
      {
        id: `${result.message_id}-q`,
        role: "student",
        text: p.text || `[${p.action}]`,
        created_at: now,
        answer: null,
      },
      {
        id: result.message_id,
        role: "tutor",
        text: "",
        created_at: now,
        answer: result.answer,
      },
    ]);
    setActive(result.conversation_id);
    void refreshList();
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    void send({ text, action: null });
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function pick(s: Suggestion) {
    if (s.action === "ask") {
      void send({ text: s.query ?? s.label, action: null, meaning: s.concept ?? null });
    } else void send({ text: "", action: s.action });
  }

  const lastTutor = [...messages].reverse().find((m) => m.role === "tutor")?.id;

  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="space-y-3" aria-label="Conversations">
        <Button variant="secondary" className="w-full" onClick={startNew} disabled={!!pending}>
          New conversation
        </Button>
        {conversations.length === 0 ? (
          <p className="text-sm text-ink-muted">No saved conversations yet.</p>
        ) : (
          <ul className="space-y-1">
            {conversations.map((c) => (
              <li key={c.id} className="group flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void open(c.id)}
                  disabled={!!pending}
                  aria-current={c.id === active ? "true" : undefined}
                  className={`min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface ${
                    c.id === active ? "bg-surface font-medium" : "text-ink-muted"
                  }`}
                >
                  {c.title ?? "Tutor session"}
                </button>
                <button
                  type="button"
                  onClick={() => void remove(c.id)}
                  aria-label={`Delete conversation: ${c.title ?? "Tutor session"}`}
                  className="rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-bad-soft hover:text-bad"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        {info && (
          <p className="text-xs text-ink-muted">
            {info.retention_days > 0
              ? `Conversations are deleted ${info.retention_days} days after their last message.`
              : "Conversations are kept until you delete them."}{" "}
            Questions are never sent to an AI service.
          </p>
        )}
      </aside>

      <section className="min-w-0 space-y-5" aria-label="Tutor conversation">
        {loadingConversation && (
          <p role="status" className="text-sm text-ink-muted">
            Opening conversation…
          </p>
        )}

        {!loadingConversation && messages.length === 0 && !pending && (
          <div className="space-y-4 rounded-lg border border-line bg-surface p-5">
            <div>
              <h2 className="font-semibold">Ask about a topic in the knowledge base</h2>
              <p className="mt-1 text-sm text-ink-muted">
                Answers are assembled from the knowledge base and local solvers, never generated.
                Every section shows where it came from, and when something is not covered the tutor
                says so instead of guessing.
              </p>
            </div>
            <SuggestionButtons suggestions={STARTERS} onPick={pick} />
            {info && (
              <details className="text-sm">
                <summary className="cursor-pointer text-ink-muted">
                  Problems the tutor can work out step by step
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-ink-muted">
                  {info.solvers.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                  <li>
                    Python code pasted in ``` fences: running time by static analysis (the code is
                    never run)
                  </li>
                </ul>
              </details>
            )}
          </div>
        )}

        {messages.map((m) =>
          m.role === "student" ? (
            <div key={m.id} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-accent-soft px-4 py-2 text-sm">
                {/^\[(simplify|example|check|deeper)\]$/.test(m.text)
                  ? actionLabel(m.text.slice(1, -1) as TutorAction)
                  : m.text}
              </p>
            </div>
          ) : m.answer ? (
            <AnswerView
              key={m.id}
              answer={m.answer}
              onPick={pick}
              busy={!!pending}
              latest={m.id === lastTutor}
            />
          ) : (
            <p key={m.id} className="text-sm text-ink-muted">
              {m.text}
            </p>
          ),
        )}

        {pending && (
          <>
            <div className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-accent-soft px-4 py-2 text-sm">
                {pending.text || actionLabel(pending.action)}
              </p>
            </div>
            <p role="status" className="text-sm text-ink-muted">
              Working out the answer…
            </p>
          </>
        )}

        {error && (
          <div role="alert" className="rounded-lg border border-bad/30 bg-bad-soft p-4 text-sm">
            <p className="font-medium">{error.message}</p>
            {error.retry && (
              <Button
                variant="secondary"
                className="mt-2"
                onClick={() => error.retry && void send(error.retry)}
              >
                Try again
              </Button>
            )}
          </div>
        )}

        <div ref={endRef} />

        <form onSubmit={submit} className="sticky bottom-0 space-y-2 bg-canvas pb-2 pt-1">
          <label htmlFor="tutor-question" className="sr-only">
            Your question
          </label>
          <textarea
            id="tutor-question"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={MAX_LENGTH}
            rows={3}
            placeholder="Ask a question, give a problem to solve, or paste code in ``` fences"
            className="block w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          />
          <div className="flex items-center justify-between gap-3 text-xs text-ink-muted">
            <span>Enter to send, Shift+Enter for a new line.</span>
            <Button type="submit" disabled={!draft.trim() || !!pending}>
              {pending ? "Answering…" : "Ask"}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
