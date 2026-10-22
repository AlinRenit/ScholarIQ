"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { DocumentSummary } from "@/lib/api";

const STATUS: Record<DocumentSummary["status"], { label: string; cls: string }> = {
  uploaded: { label: "Uploaded", cls: "bg-canvas text-ink-muted" },
  extracted: { label: "Needs review", cls: "bg-warn-soft text-warn" },
  confirmed: { label: "Confirmed", cls: "bg-ok-soft text-ok" },
  failed: { label: "Could not read", cls: "bg-bad-soft text-bad" },
};

export function DocumentList({ documents }: { documents: DocumentSummary[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  async function remove(doc: DocumentSummary) {
    const what =
      doc.status === "confirmed"
        ? `Delete "${doc.original_filename}" and every result imported from it?`
        : `Delete "${doc.original_filename}"?`;
    if (!window.confirm(what)) return;
    setBusy(doc.id);
    await fetch(`/api/documents/${doc.id}`, { method: "DELETE" }).catch(() => null);
    setBusy(null);
    router.refresh();
  }

  if (documents.length === 0) return null;
  return (
    <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
      {documents.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
          <span className="min-w-0 flex-1 truncate font-medium">{d.original_filename}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS[d.status].cls}`}>
            {STATUS[d.status].label}
          </span>
          {d.status === "extracted" && (
            <Link href={`/academics/import/${d.id}`} className="text-accent underline">
              Review
            </Link>
          )}
          <button
            type="button"
            onClick={() => remove(d)}
            disabled={busy === d.id}
            className="text-ink-subtle hover:text-bad"
          >
            Delete
          </button>
          {d.error && <p className="w-full text-xs text-bad">{d.error}</p>}
        </li>
      ))}
    </ul>
  );
}
