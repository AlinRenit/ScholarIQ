import type { AggregateOut } from "@/lib/api";

/** A headline figure that always says how many results it counts, or why it is missing. */
export function StatTile({
  label,
  value,
  suffix = "",
  agg,
  detail,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  agg: AggregateOut;
  detail: string;
}) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="text-sm text-ink-muted">{label}</h2>
      {value === null ? (
        <p className="mt-2 text-lg font-medium text-ink-muted">Not available</p>
      ) : (
        <p className="mt-1 text-3xl font-semibold tabular-nums">
          {value}
          {suffix}
        </p>
      )}
      <p className="mt-2 text-xs text-ink-muted">
        {value === null ? agg.reason : `${detail} Counts ${agg.counted} result(s).`}
        {value !== null && agg.reason ? ` ${agg.reason}` : ""}
      </p>
    </section>
  );
}
