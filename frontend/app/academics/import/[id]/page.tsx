import Link from "next/link";

import { ReviewForm } from "@/components/academics/ReviewForm";
import { Notice, PageHeader } from "@/components/ui";
import type { DocumentDetail, ScaleTemplate } from "@/lib/api";
import { serverGet } from "@/lib/server";

export const dynamic = "force-dynamic";
export const metadata = { title: "Review import" };

const SOURCE: Record<string, string> = {
  pdf_text: "digital PDF text",
  ocr: "OCR (Tesseract)",
  spreadsheet: "spreadsheet",
  csv: "CSV",
  text: "plain text",
};

export default async function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [doc, templates] = await Promise.all([
    serverGet<DocumentDetail>(`/api/documents/${encodeURIComponent(id)}`),
    serverGet<ScaleTemplate[]>("/api/documents/grading-scales"),
  ]);

  if (!doc.ok) {
    return (
      <>
        <PageHeader title="Review import" />
        <Notice tone="error" title="This upload could not be loaded.">
          {doc.message} <Link href="/academics" className="underline">Back to My Academics</Link>
        </Notice>
      </>
    );
  }

  const d = doc.data;
  const source = d.analysis.source ? SOURCE[d.analysis.source] ?? d.analysis.source : null;

  return (
    <>
      <PageHeader
        title="Review import"
        description={`${d.original_filename}${source ? `, read from ${source}` : ""}. Correct anything that is wrong. Highlighted values were hard to read or interpret.`}
      />
      {d.status === "failed" && (
        <Notice tone="error" title="This file could not be read.">
          {d.error}
        </Notice>
      )}
      {d.status === "confirmed" && (
        <Notice title="Already confirmed">
          These results are saved. <Link href="/academics" className="underline">View them</Link>
        </Notice>
      )}
      {d.status === "extracted" && (
        <ReviewForm document={d} templates={templates.ok ? templates.data : []} />
      )}
    </>
  );
}
