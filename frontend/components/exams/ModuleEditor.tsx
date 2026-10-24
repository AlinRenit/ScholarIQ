"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type CurriculumSubject } from "@/lib/api";

type Row = { key: string; id: string | null; number: string; name: string };

const field =
  "rounded border border-line bg-canvas px-2 py-1 text-sm focus:border-accent focus:outline-none";

/** Group a custom subject's topics into syllabus modules. Curriculum subjects
 * get their modules from the curriculum files, so this is shown only for the
 * student's own subjects. */
export function ModuleEditor({ subject }: { subject: CurriculumSubject }) {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>(
    (subject.modules ?? []).map((m) => ({
      key: m.id,
      id: m.id,
      number: String(m.number),
      name: m.name,
    })),
  );
  const [assign, setAssign] = useState<Record<string, string>>(
    Object.fromEntries(subject.topics.map((t) => [t.id, t.module_id ?? ""])),
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save() {
    setError(null);
    setSaved(false);
    const numbers = rows.map((r) => Number(r.number));
    if (
      rows.some(
        (r) => !r.name.trim() || !Number.isInteger(Number(r.number)) || Number(r.number) < 1,
      )
    ) {
      setError("Every module needs a whole number of 1 or more and a name.");
      return;
    }
    if (new Set(numbers).size !== numbers.length) {
      setError("Two modules have the same number.");
      return;
    }
    setBusy(true);
    const res = await fetch(`/api/curriculum/subjects/${subject.id}/modules`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        modules: rows.map((r) => ({
          id: r.id,
          number: Number(r.number),
          name: r.name.trim(),
          topic_ids: Object.entries(assign)
            .filter(([, k]) => k === r.key)
            .map(([t]) => t),
        })),
      }),
    }).catch(() => null);
    const body: unknown = await res?.json().catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(body, "Could not save the modules."));
      return;
    }
    setSaved(true);
    router.refresh();
  }

  return (
    <details className="rounded-lg border border-line bg-surface p-5">
      <summary className="cursor-pointer text-sm font-semibold">
        Modules of {subject.name} ({rows.length})
      </summary>
      <p className="mt-2 text-sm text-ink-muted">
        This is your own subject, so you decide its modules. Save your questions before changing
        modules: the page reloads with the new modules.
      </p>
      <ul className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <li key={r.key} className="flex flex-wrap items-center gap-2">
            <label className="text-xs">
              Number{" "}
              <input
                value={r.number}
                inputMode="numeric"
                onChange={(e) =>
                  setRows(rows.map((x, j) => (j === i ? { ...x, number: e.target.value } : x)))
                }
                className={`${field} w-14`}
              />
            </label>
            <label className="flex-1 text-xs">
              <span className="sr-only">Module name</span>
              <input
                value={r.name}
                aria-label={`Name of module ${r.number}`}
                onChange={(e) =>
                  setRows(rows.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                }
                className={`${field} w-full`}
              />
            </label>
            <Button
              variant="secondary"
              onClick={() => {
                setRows(rows.filter((_, j) => j !== i));
                setAssign(
                  Object.fromEntries(
                    Object.entries(assign).map(([t, k]) => [t, k === r.key ? "" : k]),
                  ),
                );
              }}
            >
              Remove
            </Button>
          </li>
        ))}
      </ul>
      <Button
        className="mt-2"
        variant="secondary"
        onClick={() => {
          const next = Math.max(0, ...rows.map((r) => Number(r.number) || 0)) + 1;
          setRows([
            ...rows,
            { key: `new-${Date.now()}`, id: null, number: String(next), name: "" },
          ]);
        }}
      >
        Add a module
      </Button>

      {subject.topics.length > 0 && rows.length > 0 && (
        <fieldset className="mt-4">
          <legend className="text-xs font-semibold">Which module is each topic in?</legend>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {subject.topics.map((t) => (
              <li key={t.id}>
                <label className="flex items-center justify-between gap-2 text-sm">
                  {t.name}
                  <select
                    value={assign[t.id] ?? ""}
                    onChange={(e) => setAssign({ ...assign, [t.id]: e.target.value })}
                    className={field}
                  >
                    <option value="">No module</option>
                    {rows.map((r) => (
                      <option key={r.key} value={r.key}>
                        Module {r.number}
                        {r.name ? `: ${r.name}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-bad">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="mt-3 text-sm text-ok">
          ✓ Modules saved.
        </p>
      )}
      <Button className="mt-3" onClick={() => void save()} disabled={busy}>
        {busy ? "Saving…" : "Save modules"}
      </Button>
    </details>
  );
}
