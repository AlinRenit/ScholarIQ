import Link from "next/link";

import { CheckQuestionCard } from "@/components/tutor/CheckQuestionCard";
import type {
  AnswerOrigin,
  AnswerSection,
  ConceptRef,
  Suggestion,
  TutorAction,
  TutorAnswer,
} from "@/lib/api";
import { Pill, TRUST } from "@/lib/labels";
import { paragraphs } from "@/lib/text";

export const ACTIONS: { action: TutorAction; label: string }[] = [
  { action: "simplify", label: "Explain more simply" },
  { action: "example", label: "Show a worked example" },
  { action: "check", label: "Test my understanding" },
  { action: "deeper", label: "Go deeper" },
];

const LEVELS: Record<NonNullable<TutorAnswer["personalisation"]>["level"], string> = {
  overview: "Brief overview",
  balanced: "Standard depth",
  guided: "Step by step",
  deeper: "In depth",
};

const SECTION_ACCENT: Partial<Record<AnswerSection["kind"], string>> = {
  definition: "border-l-accent",
  misconception: "border-l-warn",
  check: "border-l-ok",
  note: "border-l-line",
};

const conceptHref = (slug: string) => `/knowledge-base/concepts/${encodeURIComponent(slug)}`;
const topicHref = (slug: string) => `/knowledge-base/topics/${encodeURIComponent(slug)}`;

// A section built from several concepts (a comparison table) lists their slugs
// separated by spaces.
const conceptSlugs = (concept: string | null) => concept?.split(/\s+/).filter(Boolean) ?? [];

function originLabel(o: AnswerOrigin, names: Map<string, string>): string | null {
  if (o.kind === "solver") return `Computed by the ${o.solver ?? "local"} solver`;
  if (o.kind === "analysis") {
    return o.solver === "python-ast"
      ? "Static analysis; the code was not run"
      : "Worked out from your recorded results";
  }
  if (o.kind === "knowledge" && o.concept) {
    const list = conceptSlugs(o.concept).map((slug) => names.get(slug) ?? slug);
    return `From the knowledge base: ${list.join(", ")}`;
  }
  return null;
}

function SectionBody({ s }: { s: AnswerSection }) {
  return (
    <>
      {s.text &&
        paragraphs(s.text, s.kind === "example" || s.kind === "steps").map((p, i) => (
          <p key={i} className="mt-2 max-w-prose whitespace-pre-line text-sm">
            {p}
          </p>
        ))}
      {s.steps.length > 0 && (
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm">
          {s.steps.map((step, i) => (
            <li key={i} className="whitespace-pre-line">
              {step}
            </li>
          ))}
        </ol>
      )}
      {s.rows.length > 0 && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[20rem] text-left text-sm">
            {s.columns.length > 0 && (
              <thead className="text-ink-muted">
                <tr>
                  {s.columns.map((c, i) => (
                    <th
                      key={i}
                      scope="col"
                      className="border-b border-line py-1.5 pr-4 font-medium"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {s.rows.map((row, i) => (
                <tr key={i} className="border-b border-line last:border-0 align-top">
                  {row.map((cell, j) =>
                    j === 0 ? (
                      <th key={j} scope="row" className="py-1.5 pr-4 font-medium">
                        {cell}
                      </th>
                    ) : (
                      <td key={j} className="py-1.5 pr-4">
                        {cell}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {s.items.length > 0 && (
        <ul className="mt-2 space-y-1.5 text-sm">
          {s.items.map((it, i) => (
            <li key={i}>
              {it.concept ? (
                <Link href={conceptHref(it.concept)} className="font-medium underline">
                  {it.text}
                </Link>
              ) : it.topic ? (
                <Link href={topicHref(it.topic)} className="font-medium underline">
                  {it.text}
                </Link>
              ) : (
                <span className="font-medium">{it.text}</span>
              )}
              {it.detail && <span className="text-ink-muted"> — {it.detail}</span>}
            </li>
          ))}
        </ul>
      )}
      {s.code && (
        <pre className="mt-2 overflow-x-auto rounded-md bg-canvas p-3 text-xs">
          <code>{s.code}</code>
        </pre>
      )}
      {s.question && (
        <div className="mt-2">
          <CheckQuestionCard question={s.question} />
        </div>
      )}
    </>
  );
}

function Sources({ answer }: { answer: TutorAnswer }) {
  const used = new Map<string, ConceptRef>();
  const byslug = new Map(answer.concepts.map((c) => [c.slug, c]));
  for (const s of answer.sections) {
    for (const slug of conceptSlugs(s.origin.concept)) {
      const c = byslug.get(slug);
      if (c) used.set(c.slug, c);
    }
  }
  const solvers = [
    ...new Set(answer.sections.flatMap((s) => (s.origin.solver ? [s.origin.solver] : []))),
  ];
  if (used.size === 0 && solvers.length === 0 && answer.further_reading.length === 0) return null;
  return (
    <div className="space-y-2 text-sm">
      <h3 className="font-semibold">Sources</h3>
      <ul className="space-y-1">
        {[...used.values()].map((c) => (
          <li key={c.slug} className="flex flex-wrap items-center gap-2">
            <Link href={conceptHref(c.slug)} className="underline">
              {c.name}
            </Link>
            <span className="text-ink-muted">in {c.topic_name}</span>
            <Pill {...TRUST[c.trust]} />
          </li>
        ))}
        {solvers.map((s) => (
          <li key={s} className="text-ink-muted">
            {s === "python-ast"
              ? "Static analysis with Python's own parser (your code was not run)"
              : `Local ${s} solver (deterministic; shows its working above)`}
          </li>
        ))}
      </ul>
      {answer.further_reading.length > 0 && (
        <>
          <h4 className="pt-1 font-medium">Further reading</h4>
          <ul className="list-disc space-y-1 pl-5 text-ink-muted">
            {answer.further_reading.map((r) => (
              <li key={r.title}>
                {r.url ? (
                  <a href={r.url} className="underline" rel="noreferrer" target="_blank">
                    {r.title}
                  </a>
                ) : (
                  r.title
                )}
                {r.authors && `, ${r.authors}`}
                {r.citation && ` (${r.citation})`}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export function SuggestionButtons({
  suggestions,
  onPick,
  disabled,
}: {
  suggestions: Suggestion[];
  onPick: (s: Suggestion) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {suggestions.map((s) => (
        <button
          key={`${s.action}:${s.label}`}
          type="button"
          disabled={disabled}
          onClick={() => onPick(s)}
          className="rounded-full border border-line bg-surface px-3 py-1 text-sm hover:bg-canvas disabled:opacity-50"
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}

/** A structured tutor answer: every section says where it came from. */
export function AnswerView({
  answer,
  onPick,
  busy,
  latest,
}: {
  answer: TutorAnswer;
  onPick?: (s: Suggestion) => void;
  busy?: boolean;
  latest?: boolean;
}) {
  const names = new Map(answer.concepts.map((c) => [c.slug, c.name]));
  const canAct = latest && onPick && answer.status === "answered" && answer.concepts.length > 0;
  // The action buttons already offer simplify, example, check and deeper.
  const nextQuestions = canAct
    ? answer.suggestions.filter((s) => s.action === "ask")
    : answer.suggestions;

  return (
    <article className="space-y-4 rounded-lg border border-line bg-surface p-5">
      <header className="flex flex-wrap items-center gap-2 text-sm">
        <span className="rounded-md bg-canvas px-2 py-0.5 font-medium">{answer.handler_label}</span>
        {answer.status === "answered" &&
          answer.concepts.slice(0, 4).map((c) => (
            <Link key={c.slug} href={conceptHref(c.slug)} className="text-ink-muted underline">
              {c.name}
            </Link>
          ))}
      </header>

      {answer.review.label && (
        <div role="note" className="rounded-md border border-warn/30 bg-warn-soft p-3 text-sm">
          <p className="font-medium">
            <span aria-hidden>! </span>
            {answer.review.label}
          </p>
          {answer.review.unreviewed.length > 0 && (
            <p className="mt-1 text-ink-muted">
              Unreviewed material:{" "}
              {answer.review.unreviewed.map((s) => names.get(s) ?? s).join(", ")}.
            </p>
          )}
        </div>
      )}

      {answer.personalisation && (
        <p className="text-sm text-ink-muted">
          <span className="font-medium text-ink">{LEVELS[answer.personalisation.level]}.</span>{" "}
          {answer.personalisation.explanation}
        </p>
      )}

      {answer.status === "clarify" && answer.clarification && (
        <div className="space-y-3">
          <p className="font-medium">{answer.clarification.question}</p>
          {onPick && (
            <SuggestionButtons
              suggestions={answer.clarification.options}
              onPick={onPick}
              disabled={busy || !latest}
            />
          )}
        </div>
      )}

      {answer.status === "abstained" && (
        <div className="rounded-md border border-line bg-canvas p-3 text-sm">
          <p className="font-medium">I can’t answer this from the knowledge base.</p>
          {answer.missing && <p className="mt-1 text-ink-muted">{answer.missing}</p>}
        </div>
      )}

      {/* The decline notice above already states what is missing. */}
      {answer.sections
        .filter((s) => !(answer.status === "abstained" && s.text === answer.missing))
        .map((s, i) => {
          const origin = originLabel(s.origin, names);
          return (
            <section
              key={i}
              className={`border-l-2 pl-4 ${SECTION_ACCENT[s.kind] ?? "border-l-line"}`}
            >
              <h3 className="text-sm font-semibold">{s.title}</h3>
              {origin && <p className="text-xs text-ink-muted">{origin}</p>}
              <SectionBody s={s} />
            </section>
          );
        })}

      {canAct && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          {ACTIONS.map((a) => (
            <button
              key={a.action}
              type="button"
              disabled={busy}
              onClick={() => onPick({ label: a.label, action: a.action, query: null })}
              className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-50"
            >
              {a.label}
            </button>
          ))}
        </div>
      )}

      {latest && onPick && nextQuestions.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">You could ask next</h3>
          <SuggestionButtons suggestions={nextQuestions} onPick={onPick} disabled={busy} />
        </div>
      )}

      <Sources answer={answer} />

      {answer.limitations.length > 0 && (
        <div className="text-sm">
          <h3 className="font-semibold">Limits of this answer</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-ink-muted">
            {answer.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      )}

      {answer.interpretation.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-ink-muted">How I read your question</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-ink-muted">
            {answer.interpretation.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-ink-muted">Decision rules: {answer.rules_version}</p>
        </details>
      )}
    </article>
  );
}
