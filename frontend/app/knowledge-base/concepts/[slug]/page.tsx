import Link from "next/link";

import { ConceptView } from "@/components/knowledge/ConceptView";
import { Notice, PageHeader } from "@/components/ui";
import type { KnowledgeConcept } from "@/lib/api";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";

export default async function ConceptPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const concept = await serverGet<KnowledgeConcept>(
    `/api/knowledge/concepts/${encodeURIComponent(slug)}`,
  );
  const back = (
    <p className="mb-4 text-sm">
      <Link href="/knowledge-base" className="underline">
        ← Knowledge Base
      </Link>
    </p>
  );
  if (!concept.ok) {
    return (
      <>
        {back}
        <Notice
          tone="error"
          title={concept.status === 404 ? "Concept not found." : "Could not load the concept."}
        >
          {concept.status === 404 ? null : concept.message}
        </Notice>
      </>
    );
  }
  return (
    <>
      {back}
      <PageHeader title={concept.data.name} />
      <ConceptView concept={concept.data} />
    </>
  );
}
