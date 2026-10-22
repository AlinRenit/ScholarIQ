import Link from "next/link";

import { Notice, PageHeader } from "@/components/ui";
import type { KnowledgeTopic } from "@/lib/api";
import { Pill, TRUST } from "@/lib/labels";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";

export default async function KnowledgeTopicPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const topic = await serverGet<KnowledgeTopic>(
    `/api/knowledge/topics/${encodeURIComponent(slug)}`,
  );
  const back = (
    <p className="mb-4 text-sm">
      <Link href="/knowledge-base" className="underline">
        ← Knowledge Base
      </Link>
    </p>
  );
  if (!topic.ok) {
    return (
      <>
        {back}
        <Notice
          tone="error"
          title={topic.status === 404 ? "Topic not found." : "Could not load the topic."}
        >
          {topic.status === 404 ? null : topic.message}
        </Notice>
      </>
    );
  }
  return (
    <>
      {back}
      <PageHeader title={topic.data.name} description="Concepts in this topic, easiest first." />
      {topic.data.concepts.length === 0 ? (
        <Notice title="No concepts yet">This topic has no knowledge-base entries yet.</Notice>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
          {topic.data.concepts.map((c) => (
            <li
              key={c.slug}
              className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
            >
              <Link href={`/knowledge-base/concepts/${c.slug}`} className="underline">
                {c.name}
              </Link>
              <Pill {...TRUST[c.trust_status]} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
