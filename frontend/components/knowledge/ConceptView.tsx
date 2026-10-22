import Link from "next/link";

import type { KnowledgeConcept } from "@/lib/api";
import { Pill, TRUST } from "@/lib/labels";
import { paragraphs } from "@/lib/text";

const RELATION_LABELS: Record<string, { out: string; in: string }> = {
  requires: { out: "Builds on", in: "Needed for" },
  related_to: { out: "Related", in: "Related" },
  contrasts_with: { out: "Contrasts with", in: "Contrasts with" },
  part_of: { out: "Part of", in: "Includes" },
};

const DOC_KINDS: Record<string, string> = {
  explanation: "Explanation",
  procedure: "Procedure",
  example: "Worked example",
  misconception: "Common mistake",
  exercise: "Exercise",
  reference: "Reference",
};

const DEPTH = ["", "Introductory", "Standard", "Advanced"];

const humanise = (key: string) => key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

export function ConceptView({ concept: c }: { concept: KnowledgeConcept }) {
  const groups = new Map<string, KnowledgeConcept["relations"]>();
  for (const r of c.relations) {
    const label = RELATION_LABELS[r.kind]?.[r.direction] ?? r.kind;
    const group = groups.get(label) ?? [];
    // Symmetric relations can be stored in both directions; list each concept once.
    if (!group.some((g) => g.slug === r.slug)) groups.set(label, [...group, r]);
  }
  const attributes = Object.entries(c.attributes);

  return (
    <article className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
        <Link href={`/knowledge-base/topics/${c.topic_slug}`} className="underline">
          {c.topic_name}
        </Link>
        <span aria-hidden>·</span>
        <span>Difficulty {c.difficulty} of 3</span>
        <Pill {...TRUST[c.trust_status]} />
      </div>

      {c.trust_status === "imported" ? (
        <p role="note" className="rounded-lg border border-warn/30 bg-warn-soft p-3 text-sm">
          This entry has not yet been reviewed by a person. It was written for ScholarIQ from
          standard textbook material; check anything important against the further reading below.
        </p>
      ) : (
        c.reviewed_by && (
          <p className="text-sm text-ink-muted">
            Reviewed by {c.reviewed_by}
            {c.reviewed_on ? ` on ${c.reviewed_on}` : ""}.
          </p>
        )
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">Definition</h2>
        <p>{c.definition}</p>
        {c.aliases.length > 0 && (
          <p className="mt-2 text-sm text-ink-muted">
            Also called or covering: {c.aliases.join(", ")}
          </p>
        )}
      </section>

      {attributes.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">Key facts</h2>
          <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[minmax(10rem,auto)_1fr]">
            {attributes.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-muted">{humanise(k)}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {c.documents.map((d) => (
        <section
          key={`${d.kind}:${d.title}`}
          className="rounded-lg border border-line bg-surface p-4"
        >
          <p className="text-xs text-ink-muted">
            {DOC_KINDS[d.kind] ?? d.kind} · {DEPTH[d.depth] ?? `Depth ${d.depth}`}
          </p>
          <h2 className="mt-1 font-semibold">{d.title}</h2>
          {paragraphs(d.body, d.kind === "example").map((para, i) => (
            <p key={i} className="mt-2 max-w-prose whitespace-pre-line text-sm">
              {para}
            </p>
          ))}
          {d.steps.length > 0 && (
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">
              {d.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
          )}
        </section>
      ))}

      {groups.size > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">Connected concepts</h2>
          <dl className="space-y-1 text-sm">
            {[...groups].map(([label, rels]) => (
              <div key={label}>
                <dt className="inline text-ink-muted">{label}: </dt>
                <dd className="inline">
                  {rels.map((r, i) => (
                    <span key={r.slug}>
                      {i > 0 && ", "}
                      <Link href={`/knowledge-base/concepts/${r.slug}`} className="underline">
                        {r.name}
                      </Link>
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {c.further_reading.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold">Further reading</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {c.further_reading.map((s) => (
              <li key={s.title}>
                {s.url ? (
                  <a href={s.url} className="underline" rel="noreferrer">
                    {s.title}
                  </a>
                ) : (
                  <cite className="not-italic">{s.title}</cite>
                )}
                {s.authors && `, ${s.authors}`}
                {s.citation && ` (${s.citation})`}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-xs text-ink-muted">
        Content version {c.content_version}
        {c.origin ? ` · file ${c.origin}` : ""} · {c.question_count} practice question(s)
      </p>
    </article>
  );
}
