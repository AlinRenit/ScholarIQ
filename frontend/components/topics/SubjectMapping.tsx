"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui-client";
import { errorMessage, type CurriculumSubject } from "@/lib/api";

const select = "mt-1 block w-full rounded-md border border-line bg-canvas px-3 py-1.5";

/** Connect a subject the curriculum does not know to curriculum topics. */
export function SubjectMapping({
  subject,
  curriculum,
}: {
  subject: { id: string; name: string };
  curriculum: CurriculumSubject[];
}) {
  const router = useRouter();
  const [target, setTarget] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(path: string, method: string, body: unknown) {
    setBusy(true);
    setError(null);
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(await res?.json().catch(() => null), "Could not save the mapping."));
      return;
    }
    router.refresh();
  }

  function toggle(id: string) {
    setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  }

  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <h3 className="font-semibold">{subject.name}</h3>
      <p className="mt-1 text-sm text-ink-muted">
        This subject is not in the curriculum, so ScholarIQ cannot tell which topics it covers.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <label className="min-w-56 flex-1 text-sm">
          It is the same subject as
          <select value={target} onChange={(e) => setTarget(e.target.value)} className={select}>
            <option value="">Choose a curriculum subject…</option>
            {curriculum.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="secondary"
          disabled={!target || busy}
          onClick={() =>
            void send("/api/academics/subjects/remap", "POST", {
              from_subject_id: subject.id,
              to_subject_id: target,
            })
          }
        >
          Move my results
        </Button>
      </div>

      <details className="mt-4 text-sm">
        <summary className="cursor-pointer">Or choose the topics it covers</summary>
        <div className="mt-3 max-h-80 space-y-3 overflow-y-auto pr-2">
          {curriculum.map((c) => (
            <fieldset key={c.id}>
              <legend className="font-medium">{c.name}</legend>
              {c.topics.map((t) => (
                <label key={t.id} className="flex items-center gap-2 py-0.5 text-ink-muted">
                  <input
                    type="checkbox"
                    checked={chosen.includes(t.id)}
                    onChange={() => toggle(t.id)}
                  />
                  {t.name}
                </label>
              ))}
            </fieldset>
          ))}
        </div>
        <Button
          className="mt-3"
          disabled={chosen.length === 0 || busy}
          onClick={() =>
            void send(`/api/curriculum/subjects/${subject.id}/topics`, "PUT", { topic_ids: chosen })
          }
        >
          Save {chosen.length} topic(s)
        </Button>
      </details>

      {error && (
        <p role="alert" className="mt-3 text-sm text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
