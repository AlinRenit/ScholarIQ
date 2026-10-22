import type { Band, MasteryClass, TrustStatus } from "@/lib/api";

// Labels always pair with a symbol so status is never conveyed by colour alone.
export const MASTERY: Record<MasteryClass, { label: string; symbol: string; cls: string }> = {
  strong: { label: "Strong", symbol: "●", cls: "bg-ok-soft text-ok" },
  developing: {
    label: "Developing",
    symbol: "◆",
    cls: "bg-accent-soft text-accent",
  },
  needs_attention: {
    label: "Needs attention",
    symbol: "▲",
    cls: "bg-warn-soft text-warn",
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    symbol: "○",
    cls: "bg-canvas text-ink-muted border border-line",
  },
};

export const BAND: Record<Band, { label: string; symbol: string; cls: string }> = {
  strong: {
    label: "Strong exam result",
    symbol: "●",
    cls: "bg-ok-soft text-ok",
  },
  developing: {
    label: "Mid-range exam result",
    symbol: "◆",
    cls: "bg-accent-soft text-accent",
  },
  needs_attention: {
    label: "May need attention",
    symbol: "▲",
    cls: "bg-warn-soft text-warn",
  },
  no_score: {
    label: "No usable score",
    symbol: "○",
    cls: "bg-canvas text-ink-muted",
  },
};

export function Pill({ symbol, label, cls }: { symbol: string; label: string; cls: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      <span aria-hidden>{symbol}</span>
      {label}
    </span>
  );
}

export const TRUST: Record<TrustStatus, { label: string; symbol: string; cls: string }> = {
  verified: { label: "Reviewed by a person", symbol: "✓", cls: "bg-ok-soft text-ok" },
  imported: {
    label: "Not yet reviewed by a person",
    symbol: "!",
    cls: "bg-warn-soft text-warn",
  },
  retired: { label: "Retired", symbol: "×", cls: "bg-canvas text-ink-muted border border-line" },
};
