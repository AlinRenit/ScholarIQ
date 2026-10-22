import { Card, StatusBadge } from "@/components/ui";
import type { Capability, Readiness } from "@/lib/api";

const CHECK_LABELS: Record<string, string> = {
  database: "Database",
  upload_storage: "Upload storage",
  knowledge_content: "Knowledge content",
  ocr: "OCR (Tesseract)",
  no_external_ai: "No external AI configured",
};

export function ReadinessPanel({ readiness }: { readiness: Readiness }) {
  return (
    <Card title="System status">
      <div className="mb-3 flex items-center gap-2 text-sm">
        <span className="text-ink-muted">Overall</span>
        <StatusBadge status={readiness.status} />
      </div>
      <ul className="divide-y divide-line text-sm">
        {readiness.checks.map((c) => (
          <li key={c.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>
              {CHECK_LABELS[c.name] ?? c.name}
              {!c.required && <span className="ml-1 text-xs text-ink-subtle">(optional)</span>}
            </span>
            <span className="flex items-center gap-2">
              <span className="text-xs text-ink-muted">{c.detail}</span>
              <StatusBadge status={c.status} />
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function CapabilityPanel({ capabilities }: { capabilities: Capability[] }) {
  return (
    <Card title="What works today">
      <ol className="space-y-2 text-sm">
        {capabilities.map((c) => (
          <li key={c.key} className="flex items-start justify-between gap-3">
            <span className={c.status === "available" ? "text-ink" : "text-ink-muted"}>
              <span className="mr-2 font-mono text-xs text-ink-subtle">M{c.milestone}</span>
              {c.label}
            </span>
            <span
              className={`shrink-0 text-xs ${c.status === "available" ? "text-ok" : "text-ink-subtle"}`}
            >
              {c.status === "available" ? "Available" : "Planned"}
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
