"use client";

import { Button } from "@/components/ui-client";
import type { ExamModule, ExamSubjectTopic } from "@/lib/api";
import { type EditorQuestion, topicModuleName, withModuleOnly, withTopic } from "@/lib/exams";

const STATUSES = [
  ["unknown", "Not known yet"],
  ["attempted", "Attempted"],
  ["not_attempted", "Not attempted"],
] as const;

const input =
  "w-full rounded border bg-canvas px-2 py-1 text-sm focus:border-accent focus:outline-none";

export function QuestionCard({
  question: q,
  index,
  topics,
  modules,
  errors,
  onChange,
  onRemove,
}: {
  question: EditorQuestion;
  index: number;
  topics: ExamSubjectTopic[];
  modules: ExamModule[];
  errors: string[];
  onChange: (q: EditorQuestion) => void;
  onRemove: () => void;
}) {
  const set = <K extends keyof EditorQuestion>(field: K, value: EditorQuestion[K]) =>
    onChange({ ...q, [field]: value });
  const id = (field: string) => `q-${q.key}-${field}`;
  const lowConfidence = q.parse_confidence !== null && q.parse_confidence < 0.8;
  const topicName = (tid: string) => topics.find((t) => t.id === tid)?.name ?? "Unknown topic";
  const moduleName = (mid: string) => {
    const m = modules.find((x) => x.id === mid);
    return m ? `Module ${m.number}: ${m.name}` : "Unknown module";
  };
  const byModule = [
    ...modules.map((m) => ({
      label: `Module ${m.number}: ${m.name}`,
      items: topics.filter((t) => t.module_id === m.id),
    })),
    { label: "Not in a module", items: topics.filter((t) => !t.module_id) },
  ].filter((g) => g.items.length > 0);
  const mappedTopics = new Set(q.mappings.map((m) => m.topic_id).filter(Boolean));
  const s = q.suggestion;
  const suggestions = s?.candidates.filter((c) => !mappedTopics.has(c.topic_id)) ?? [];

  return (
    <li
      className={`rounded-lg border bg-surface p-4 ${
        q.needs_review ? "border-warn" : "border-line"
      }`}
      aria-label={`Question ${q.label || index + 1}`}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <label className="block text-xs" htmlFor={id("label")}>
          <span className="mb-1 block font-medium">Question</span>
          <input
            id={id("label")}
            value={q.label}
            onChange={(e) => set("label", e.target.value)}
            placeholder="e.g. 2(b)(i)"
            className={`${input} border-line font-mono`}
          />
        </label>
        <label className="block text-xs" htmlFor={id("max")}>
          <span className="mb-1 block font-medium">Maximum marks</span>
          <input
            id={id("max")}
            inputMode="decimal"
            value={q.max_marks}
            onChange={(e) => set("max_marks", e.target.value)}
            placeholder="unknown"
            className={`${input} ${q.max_marks ? "border-line" : "border-warn bg-warn-soft"}`}
          />
        </label>
        <label className="block text-xs" htmlFor={id("got")}>
          <span className="mb-1 block font-medium">Marks obtained</span>
          <input
            id={id("got")}
            inputMode="decimal"
            value={q.attempt_status === "not_attempted" ? "" : q.marks_obtained}
            disabled={q.attempt_status === "not_attempted"}
            onChange={(e) => {
              const v = e.target.value;
              onChange({
                ...q,
                marks_obtained: v,
                attempt_status:
                  v.trim() && q.attempt_status === "unknown" ? "attempted" : q.attempt_status,
              });
            }}
            placeholder="blank = unknown"
            className={`${input} border-line`}
          />
        </label>
        <label className="block text-xs" htmlFor={id("status")}>
          <span className="mb-1 block font-medium">Attempt</span>
          <select
            id={id("status")}
            value={q.attempt_status}
            onChange={(e) =>
              set("attempt_status", e.target.value as EditorQuestion["attempt_status"])
            }
            className={`${input} border-line`}
          >
            {STATUSES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs" htmlFor={id("section")}>
          <span className="mb-1 block font-medium">Section</span>
          <input
            id={id("section")}
            value={q.section}
            onChange={(e) => set("section", e.target.value)}
            className={`${input} border-line`}
          />
        </label>
        <div className="flex items-end justify-end">
          <Button variant="secondary" onClick={onRemove} aria-label={`Remove question ${q.label}`}>
            Remove
          </Button>
        </div>
      </div>

      {q.context && <p className="mt-3 text-xs text-ink-subtle">Part of: {q.context}</p>}
      <label className="mt-2 block text-xs" htmlFor={id("text")}>
        <span className="mb-1 block font-medium">Question text</span>
        <textarea
          id={id("text")}
          value={q.text}
          rows={2}
          onChange={(e) => set("text", e.target.value)}
          className={`${input} border-line`}
        />
      </label>

      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={q.is_optional}
            onChange={(e) => set("is_optional", e.target.checked)}
          />
          Optional (part of a choice)
        </label>
        {q.is_optional && (
          <label className="flex items-center gap-1.5">
            Choice group
            <input
              value={q.choice_group}
              onChange={(e) => set("choice_group", e.target.value)}
              placeholder="e.g. Part B"
              className={`${input} w-40 border-line`}
            />
          </label>
        )}
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={q.needs_review}
            onChange={(e) => set("needs_review", e.target.checked)}
          />
          Uncertain: leave out of the results until checked
        </label>
        {q.parse_confidence !== null && (
          <span className={lowConfidence ? "text-warn" : "text-ink-subtle"}>
            Read from the paper{q.page ? ` (page ${q.page})` : ""}, confidence{" "}
            {Math.round(q.parse_confidence * 100)}%{lowConfidence ? ": please check" : ""}
          </span>
        )}
      </div>

      <fieldset className="mt-3 rounded-md border border-line p-3">
        <legend className="px-1 text-xs font-semibold">Module and topic</legend>
        {q.mappings.length === 0 ? (
          <p className="text-xs text-ink-muted">
            Not mapped. Unmapped questions count in the overall total but not in any module or
            topic.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {q.mappings.map((m, i) => (
              <li
                key={m.topic_id ?? m.module_id}
                className="flex flex-wrap items-center gap-2 text-sm"
              >
                <span>
                  {m.topic_id ? (
                    <>
                      {topicName(m.topic_id)}
                      <span className="text-xs text-ink-subtle">
                        {" "}
                        {topicModuleName(m.topic_id, topics, modules) ?? "(not in a module)"}
                      </span>
                    </>
                  ) : (
                    <>
                      {moduleName(m.module_id!)}{" "}
                      <span className="text-xs text-ink-subtle">
                        (module only, topic not known)
                      </span>
                    </>
                  )}
                </span>
                {q.mappings.length > 1 && (
                  <label className="flex items-center gap-1 text-xs">
                    Share
                    <input
                      inputMode="decimal"
                      value={m.share}
                      placeholder="equal"
                      onChange={(e) =>
                        set(
                          "mappings",
                          q.mappings.map((x, j) => (j === i ? { ...x, share: e.target.value } : x)),
                        )
                      }
                      className={`${input} w-16 border-line`}
                      aria-label={`Share of question ${q.label} for this topic, in percent`}
                    />
                    %
                  </label>
                )}
                <button
                  type="button"
                  className="text-xs text-ink-muted underline"
                  onClick={() =>
                    set(
                      "mappings",
                      q.mappings.filter((_, j) => j !== i),
                    )
                  }
                >
                  remove
                </button>
              </li>
            ))}
          </ul>
        )}

        {s && s.status !== "none" && suggestions.length > 0 && (
          <div className="mt-2 text-xs">
            <p className="text-ink-muted">
              {s.status === "clear"
                ? "Suggested from the question text:"
                : "Several topics match; choose one or more:"}
            </p>
            <ul className="mt-1 flex flex-wrap gap-2">
              {suggestions.map((c) => (
                <li key={c.topic_id}>
                  <button
                    type="button"
                    onClick={() => onChange(withTopic(q, c.topic_id))}
                    className="rounded-full border border-accent/40 bg-accent-soft px-2 py-0.5 text-accent hover:opacity-90"
                    title={`Matched words: ${c.matched.join(", ")}`}
                  >
                    + {c.topic_name}
                    {topicModuleName(c.topic_id, topics, modules)
                      ? ` (${topicModuleName(c.topic_id, topics, modules)})`
                      : ""}
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-ink-subtle">
              Matched words: {suggestions[0]!.matched.join(", ")}. Suggestions are only a starting
              point.
            </p>
          </div>
        )}
        {s && s.status === "none" && q.mappings.length === 0 && (
          <p className="mt-2 text-xs text-ink-subtle">
            No topic matches the text closely enough to suggest one.
          </p>
        )}

        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <label className="block text-xs">
            <span className="mb-1 block">Add a topic</span>
            <select
              value=""
              onChange={(e) => e.target.value && onChange(withTopic(q, e.target.value))}
              className={`${input} border-line`}
            >
              <option value="">Choose a topic…</option>
              {byModule.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.items.map((t) => (
                    <option key={t.id} value={t.id} disabled={mappedTopics.has(t.id)}>
                      {t.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          {modules.length > 0 && (
            <label className="block text-xs">
              <span className="mb-1 block">Or only the module</span>
              <select
                value=""
                onChange={(e) => e.target.value && onChange(withModuleOnly(q, e.target.value))}
                className={`${input} border-line`}
              >
                <option value="">Choose a module…</option>
                {modules.map((m) => (
                  <option key={m.id} value={m.id}>
                    Module {m.number}: {m.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </fieldset>

      {q.exclusion && (
        <p className="mt-2 text-xs text-warn">Not counted in the results: {q.exclusion}.</p>
      )}
      {errors.length > 0 && (
        <ul role="alert" className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-bad">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
