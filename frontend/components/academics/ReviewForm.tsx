"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui-client";
import {
  errorMessage,
  type DocumentDetail,
  type ExtractedFields,
  type ScaleTemplate,
} from "@/lib/api";

type FieldName =
  | "subject_name"
  | "subject_code"
  | "component"
  | "status"
  | "marks_obtained"
  | "max_marks"
  | "grade"
  | "credits"
  | "semester"
  | "exam_type";

type EditableRow = {
  key: string;
  include: boolean;
  values: Record<FieldName, string>;
  confidence: Record<string, number>;
  edited: Set<FieldName>;
  warnings: string[];
  source: string | null;
};

const COMPONENTS = [
  ["combined", "Combined"],
  ["theory", "Theory"],
  ["lab", "Lab / practical"],
] as const;
const STATUSES = [
  ["present", "Present"],
  ["absent", "Absent"],
  ["withheld", "Withheld"],
  ["missing", "Missing"],
] as const;
const EXAM_TYPES = [
  ["unknown", "Not stated"],
  ["regular", "Regular"],
  ["supplementary", "Supplementary"],
  ["backlog", "Backlog"],
  ["internal", "Internal"],
] as const;

function toValues(f: ExtractedFields): Record<FieldName, string> {
  return {
    subject_name: f.subject_name ?? "",
    subject_code: f.subject_code ?? "",
    component: f.component ?? "combined",
    status: f.status ?? "present",
    marks_obtained: f.marks_obtained ?? "",
    max_marks: f.max_marks ?? "",
    grade: f.grade ?? "",
    credits: f.credits ?? "",
    semester: f.semester != null ? String(f.semester) : "",
    exam_type: f.exam_type ?? "unknown",
  };
}

let counter = 0;
function blankRow(template?: EditableRow): EditableRow {
  counter += 1;
  return {
    key: `new-${counter}`,
    include: true,
    values: {
      ...toValues({}),
      semester: template?.values.semester ?? "",
      exam_type: template?.values.exam_type ?? "unknown",
    },
    confidence: {},
    edited: new Set(),
    warnings: [],
    source: null,
  };
}

const orNull = (v: string) => (v.trim() === "" ? null : v.trim());

export function ReviewForm({
  document,
  templates,
}: {
  document: DocumentDetail;
  templates: ScaleTemplate[];
}) {
  const router = useRouter();
  const threshold = document.analysis.review_threshold ?? 0.8;
  const [rows, setRows] = useState<EditableRow[]>(() =>
    document.records.map((r) => ({
      key: r.id,
      include: true,
      values: toValues(r.fields),
      confidence: r.confidence,
      edited: new Set(),
      warnings: r.warnings,
      source: r.source_text,
    })),
  );
  const [scaleMode, setScaleMode] = useState<string>("none");
  const [customName, setCustomName] = useState("My institution's scale");
  const [customMax, setCustomMax] = useState("10");
  const [customPoints, setCustomPoints] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const included = rows.filter((r) => r.include);
  const grades = useMemo(
    () =>
      [...new Set(included.map((r) => r.values.grade.trim().toUpperCase()).filter(Boolean))].sort(),
    [included],
  );
  const uncertain = included.filter((r) =>
    Object.entries(r.confidence).some(
      ([k, v]) => v < threshold && !r.edited.has(k as FieldName) && k in r.values,
    ),
  ).length;

  function update(key: string, field: FieldName, value: string) {
    setRows((rs) =>
      rs.map((r) =>
        r.key === key
          ? { ...r, values: { ...r.values, [field]: value }, edited: new Set(r.edited).add(field) }
          : r,
      ),
    );
  }

  function fieldClass(row: EditableRow, field: FieldName): string {
    const c = row.confidence[field];
    const base =
      "w-full rounded border bg-canvas px-2 py-1 text-sm focus:border-accent focus:outline-none";
    if (c === undefined || row.edited.has(field)) return `${base} border-line`;
    if (c < 0.5) return `${base} border-bad bg-bad-soft`;
    if (c < threshold) return `${base} border-warn bg-warn-soft`;
    return `${base} border-line`;
  }

  function fieldLabel(row: EditableRow, field: FieldName, label: string): string {
    const c = row.confidence[field];
    if (c === undefined || row.edited.has(field) || c >= threshold) return label;
    return `${label} (uncertain, please check)`;
  }

  async function submit() {
    setError(null);
    let grading: unknown = null;
    if (grades.length > 0 && scaleMode !== "none") {
      if (scaleMode === "custom") {
        const missing = grades.filter((g) => !customPoints[g]?.trim());
        if (missing.length) {
          setError(`Enter points for: ${missing.join(", ")}.`);
          return;
        }
        grading = {
          custom: {
            name: customName,
            max_points: customMax,
            points: Object.fromEntries(grades.map((g) => [g, customPoints[g]])),
          },
        };
      } else {
        grading = { template: scaleMode };
      }
    }
    const results = included.map((r) => ({
      subject_name: r.values.subject_name.trim(),
      subject_code: orNull(r.values.subject_code),
      component: r.values.component,
      status: r.values.status,
      marks_obtained: r.values.status === "present" ? orNull(r.values.marks_obtained) : null,
      max_marks: orNull(r.values.max_marks),
      grade: orNull(r.values.grade),
      credits: orNull(r.values.credits),
      semester: r.values.semester.trim() === "" ? null : Number(r.values.semester),
      exam_type: r.values.exam_type,
      exam_name: document.analysis.context?.exam_name ?? null,
    }));
    if (results.length === 0) {
      setError("Include at least one row, or delete this upload instead.");
      return;
    }
    setBusy(true);
    const res = await fetch(`/api/documents/${document.id}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ results, grading }),
    }).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      setError(errorMessage(await res?.json().catch(() => null), "Could not save the results."));
      return;
    }
    router.push("/academics");
    router.refresh();
  }

  const docWarnings = [...(document.analysis.notes ?? []), ...(document.analysis.warnings ?? [])];

  return (
    <div className="space-y-6">
      {docWarnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-warn/30 bg-warn-soft p-4 text-sm">
          {docWarnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <p className="text-sm text-ink-muted">
        {included.length} of {rows.length} rows included.{" "}
        {uncertain > 0 ? (
          <span className="text-warn">
            {uncertain} row{uncertain === 1 ? " has" : "s have"} highlighted values to check.
          </span>
        ) : (
          "No values are flagged as uncertain, but please check them all."
        )}
      </p>

      <ol className="space-y-3">
        {rows.map((row, i) => (
          <li
            key={row.key}
            className={`rounded-lg border border-line bg-surface p-4 ${row.include ? "" : "opacity-50"}`}
          >
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  checked={row.include}
                  onChange={(e) =>
                    setRows((rs) =>
                      rs.map((r) => (r.key === row.key ? { ...r, include: e.target.checked } : r)),
                    )
                  }
                />
                Row {i + 1}: include
              </label>
              {row.source && (
                <span className="max-w-full truncate font-mono text-xs text-ink-subtle">
                  read as: {row.source}
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              <Field className="col-span-2" label={fieldLabel(row, "subject_name", "Subject")}>
                <input
                  value={row.values.subject_name}
                  onChange={(e) => update(row.key, "subject_name", e.target.value)}
                  className={fieldClass(row, "subject_name")}
                />
              </Field>
              <Field label={fieldLabel(row, "subject_code", "Code")}>
                <input
                  value={row.values.subject_code}
                  onChange={(e) => update(row.key, "subject_code", e.target.value)}
                  className={fieldClass(row, "subject_code")}
                />
              </Field>
              <Field label="Component">
                <select
                  value={row.values.component}
                  onChange={(e) => update(row.key, "component", e.target.value)}
                  className={fieldClass(row, "component")}
                >
                  {COMPONENTS.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={fieldLabel(row, "status", "Status")}>
                <select
                  value={row.values.status}
                  onChange={(e) => update(row.key, "status", e.target.value)}
                  className={fieldClass(row, "status")}
                >
                  {STATUSES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={fieldLabel(row, "marks_obtained", "Marks obtained")}>
                <input
                  inputMode="decimal"
                  disabled={row.values.status !== "present"}
                  value={row.values.status === "present" ? row.values.marks_obtained : ""}
                  onChange={(e) => update(row.key, "marks_obtained", e.target.value)}
                  className={fieldClass(row, "marks_obtained")}
                />
              </Field>
              <Field label={fieldLabel(row, "max_marks", "Maximum marks")}>
                <input
                  inputMode="decimal"
                  placeholder="unknown"
                  value={row.values.max_marks}
                  onChange={(e) => update(row.key, "max_marks", e.target.value)}
                  className={fieldClass(row, "max_marks")}
                />
              </Field>
              <Field label={fieldLabel(row, "grade", "Grade")}>
                <input
                  value={row.values.grade}
                  onChange={(e) => update(row.key, "grade", e.target.value)}
                  className={fieldClass(row, "grade")}
                />
              </Field>
              <Field label={fieldLabel(row, "credits", "Credits")}>
                <input
                  inputMode="decimal"
                  value={row.values.credits}
                  onChange={(e) => update(row.key, "credits", e.target.value)}
                  className={fieldClass(row, "credits")}
                />
              </Field>
              <Field label={fieldLabel(row, "semester", "Semester")}>
                <input
                  inputMode="numeric"
                  value={row.values.semester}
                  onChange={(e) => update(row.key, "semester", e.target.value)}
                  className={fieldClass(row, "semester")}
                />
              </Field>
              <Field label={fieldLabel(row, "exam_type", "Exam")}>
                <select
                  value={row.values.exam_type}
                  onChange={(e) => update(row.key, "exam_type", e.target.value)}
                  className={fieldClass(row, "exam_type")}
                >
                  {EXAM_TYPES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {row.warnings.length > 0 && (
              <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-warn">
                {row.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>

      <Button
        variant="secondary"
        onClick={() => setRows((rs) => [...rs, blankRow(rs[rs.length - 1])])}
      >
        Add a row
      </Button>

      {grades.length > 0 && (
        <fieldset className="space-y-3 rounded-lg border border-line bg-surface p-4">
          <legend className="px-1 text-sm font-semibold">Grading scale</legend>
          <p className="text-sm text-ink-muted">
            Grades found: {grades.join(", ")}. ScholarIQ does not guess what grades are worth.
            Choose the scale your institution uses, or keep the grades as printed.
          </p>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name="scale"
              checked={scaleMode === "none"}
              onChange={() => setScaleMode("none")}
              className="mt-1"
            />
            <span>Keep grades as printed (no grade points)</span>
          </label>
          {templates.map((t) => {
            const missing = grades.filter((g) => !(g in t.points));
            return (
              <label key={t.key} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="scale"
                  disabled={missing.length > 0}
                  checked={scaleMode === t.key}
                  onChange={() => setScaleMode(t.key)}
                  className="mt-1"
                />
                <span>
                  {t.name}
                  <span className="block text-xs text-ink-subtle">
                    {missing.length > 0
                      ? `Not usable: has no ${missing.join(", ")}.`
                      : t.description}
                  </span>
                </span>
              </label>
            );
          })}
          <label className="flex items-start gap-2 text-sm">
            <input
              type="radio"
              name="scale"
              checked={scaleMode === "custom"}
              onChange={() => setScaleMode("custom")}
              className="mt-1"
            />
            <span>Define the scale myself</span>
          </label>
          {scaleMode === "custom" && (
            <div className="grid gap-3 pl-6 sm:grid-cols-2">
              <Field label="Scale name">
                <input
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  className="w-full rounded border border-line bg-canvas px-2 py-1 text-sm"
                />
              </Field>
              <Field label="Maximum grade points">
                <input
                  inputMode="decimal"
                  value={customMax}
                  onChange={(e) => setCustomMax(e.target.value)}
                  className="w-full rounded border border-line bg-canvas px-2 py-1 text-sm"
                />
              </Field>
              {grades.map((g) => (
                <Field key={g} label={`Points for ${g}`}>
                  <input
                    inputMode="decimal"
                    value={customPoints[g] ?? ""}
                    onChange={(e) => setCustomPoints((p) => ({ ...p, [g]: e.target.value }))}
                    className="w-full rounded border border-line bg-canvas px-2 py-1 text-sm"
                  />
                </Field>
              ))}
            </div>
          )}
        </fieldset>
      )}

      {error && (
        <p role="alert" className="rounded-lg border border-bad/30 bg-bad-soft p-3 text-sm text-bad">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={submit} disabled={busy}>
          {busy ? "Saving…" : `Confirm and save ${included.length} result${included.length === 1 ? "" : "s"}`}
        </Button>
        <span className="text-xs text-ink-subtle">
          Only the values shown here are saved. The extracted text is then discarded.
        </span>
      </div>
    </div>
  );
}

function Field({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block text-xs text-ink-muted ${className}`}>
      <span className="mb-1 block">{label}</span>
      {children}
    </label>
  );
}
