import Link from "next/link";

import type { KnowledgeSearch } from "@/lib/api";
import { Pill, TRUST } from "@/lib/labels";

const fmt = (n: number) => n.toFixed(2);

/** Search results with the full score breakdown, so a ranking can be checked by hand. */
export function SearchResults({ search }: { search: KnowledgeSearch }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-muted">{search.method}</p>
      {search.unmatched_terms.length > 0 && (
        <p className="text-sm text-ink-muted">
          Not found anywhere in the knowledge base:{" "}
          {search.unmatched_terms.map((t) => `"${t}"`).join(", ")}.
        </p>
      )}
      {search.results.length === 0 ? (
        <p role="status" className="rounded-lg border border-line bg-surface p-4">
          No concept matches this search. The knowledge base covers the Computer Science subjects
          listed below; try the name of a concept or a key term.
        </p>
      ) : (
        <ol className="space-y-3">
          {search.results.map((r, i) => {
            const terms = Object.entries(r.matched_terms).sort((a, b) => b[1] - a[1]);
            return (
              <li key={r.slug} className="rounded-lg border border-line bg-surface p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p>
                    <span className="mr-2 text-ink-muted">{i + 1}.</span>
                    <Link
                      href={`/knowledge-base/concepts/${r.slug}`}
                      className="font-medium underline"
                    >
                      {r.name}
                    </Link>
                    <span className="ml-2 text-sm text-ink-muted">{r.topic_name}</span>
                  </p>
                  <Pill {...TRUST[r.trust_status]} />
                </div>
                <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                  <dt className="text-ink-muted">Score</dt>
                  <dd className="tabular-nums">{fmt(r.score)}</dd>
                  <dt className="text-ink-muted">Matched words</dt>
                  <dd>
                    {terms.length === 0
                      ? "none"
                      : terms.map(([t, s]) => `${t} ${fmt(s)}`).join(" + ")}
                  </dd>
                  {r.name_match && (
                    <>
                      <dt className="text-ink-muted">Names the concept</dt>
                      <dd>
                        &ldquo;{r.name_match}&rdquo; adds {fmt(r.name_bonus)}
                      </dd>
                    </>
                  )}
                </dl>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
