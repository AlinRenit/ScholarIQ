import Link from "next/link";

import { SearchResults } from "@/components/knowledge/SearchResults";
import { Notice, PageHeader } from "@/components/ui";
import { Button } from "@/components/ui-client";
import type { KnowledgeOverview, KnowledgeSearch } from "@/lib/api";
import { navItem } from "@/lib/planned";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Knowledge Base" };

export default async function KnowledgeBasePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const item = navItem("/knowledge-base");
  const q = ((await searchParams).q ?? "").trim().slice(0, 300);
  const [overview, search] = await Promise.all([
    serverGet<KnowledgeOverview>("/api/knowledge/overview"),
    q ? serverGet<KnowledgeSearch>(`/api/knowledge/search?q=${encodeURIComponent(q)}`) : null,
  ]);

  if (!overview.ok) {
    return (
      <>
        <PageHeader title={item.label} description={item.description} />
        <Notice tone="error" title="Could not load the knowledge base.">
          {overview.message}
        </Notice>
      </>
    );
  }
  const o = overview.data;
  const unreviewed = o.concepts - o.verified_concepts;

  return (
    <>
      <PageHeader title={item.label} description={item.description} />

      <div className="mb-6 space-y-3">
        <p className="text-sm text-ink-muted">
          {o.concepts} concepts, {o.documents} explanations and examples, {o.questions} practice
          questions. {o.verified_concepts} of {o.concepts} concepts have been reviewed by a person.
        </p>
        {unreviewed > 0 &&
          (o.allow_unreviewed ? (
            <Notice
              tone="warn"
              title={`${unreviewed} of ${o.concepts} concepts are not yet reviewed by a person`}
            >
              The tutor and quizzes may use them, and every answer built from one is labelled
              &ldquo;not yet reviewed by a person&rdquo;. Reviewers sign off each concept with{" "}
              <code>python -m scholariq.knowledge.review</code>.
            </Notice>
          ) : (
            <Notice tone="warn" title="Unreviewed entries are switched off">
              Search, the tutor and quizzes use only the {o.verified_concepts} reviewed concepts.
              Unreviewed entries are still listed below.
            </Notice>
          ))}
      </div>

      <form role="search" action="/knowledge-base" className="mb-6 flex flex-wrap gap-2">
        <label htmlFor="kb-q" className="sr-only">
          Search the knowledge base
        </label>
        <input
          id="kb-q"
          name="q"
          defaultValue={q}
          maxLength={300}
          placeholder="For example: quick sort, 3NF, deadlock conditions"
          className="min-w-0 flex-1 rounded-md border border-line bg-canvas px-3 py-2"
        />
        <Button type="submit">Search</Button>
      </form>

      {search && (
        <section aria-labelledby="results-heading" className="mb-8">
          <h2 id="results-heading" className="mb-3 font-semibold">
            Results for &ldquo;{q}&rdquo;
          </h2>
          {search.ok ? (
            <SearchResults search={search.data} />
          ) : (
            <Notice tone="error" title="Search failed.">
              {search.message}
            </Notice>
          )}
        </section>
      )}

      <section aria-labelledby="coverage-heading">
        <h2 id="coverage-heading" className="mb-3 font-semibold">
          Coverage
        </h2>
        <div className="space-y-6">
          {o.subjects.map((s) => (
            <div key={s.id} className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full text-sm">
                <caption className="px-4 pt-3 text-left font-medium">{s.name}</caption>
                <thead className="text-ink-muted">
                  <tr className="border-b border-line">
                    <th scope="col" className="px-4 py-2 text-left font-normal">
                      Topic
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-normal">
                      Concepts
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-normal">
                      Reviewed
                    </th>
                    <th scope="col" className="px-3 py-2 text-right font-normal">
                      Explanations
                    </th>
                    <th scope="col" className="px-4 py-2 text-right font-normal">
                      Questions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {s.topics.map((t) => (
                    <tr key={t.id} className="border-b border-line last:border-0">
                      <th scope="row" className="px-4 py-2 text-left font-normal">
                        {t.concepts > 0 ? (
                          <Link href={`/knowledge-base/topics/${t.slug}`} className="underline">
                            {t.name}
                          </Link>
                        ) : (
                          t.name
                        )}
                      </th>
                      <td className="px-3 py-2 text-right tabular-nums">{t.concepts}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {t.verified_concepts} of {t.concepts}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{t.documents}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{t.questions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
