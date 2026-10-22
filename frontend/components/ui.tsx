import type { ReactNode } from "react";

import type { CheckStatus } from "@/lib/api";

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header className="mb-8">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      {description && <p className="mt-2 max-w-2xl text-ink-muted">{description}</p>}
    </header>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      {title && <h2 className="mb-3 text-sm font-semibold text-ink">{title}</h2>}
      {children}
    </section>
  );
}

const STATUS_STYLES: Record<CheckStatus, string> = {
  ok: "bg-ok-soft text-ok",
  degraded: "bg-warn-soft text-warn",
  failed: "bg-bad-soft text-bad",
};

const STATUS_LABELS: Record<CheckStatus, string> = {
  ok: "OK",
  degraded: "Degraded",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: CheckStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warn" | "error";
  title: string;
  children?: ReactNode;
}) {
  const styles = {
    info: "border-line bg-surface",
    warn: "border-warn/30 bg-warn-soft",
    error: "border-bad/30 bg-bad-soft",
  }[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-lg border p-4 ${styles}`}>
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-ink-muted">{children}</div>}
    </div>
  );
}
