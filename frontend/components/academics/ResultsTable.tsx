import type { AcademicAssessment, AcademicResult } from "@/lib/api";

const EXAM: Record<string, string> = {
  regular: "Regular",
  supplementary: "Supplementary",
  backlog: "Backlog",
  internal: "Internal",
  unknown: "Exam type not stated",
};

function num(v: string | null): string {
  return v === null ? "" : String(Number(v));
}

function marks(r: AcademicResult): string {
  if (r.status === "absent") return "Absent";
  if (r.status === "withheld") return "Withheld";
  if (r.marks_obtained === null) return r.status === "missing" ? "Missing" : "—";
  return r.max_marks === null
    ? `${num(r.marks_obtained)} / ?`
    : `${num(r.marks_obtained)} / ${num(r.max_marks)}`;
}

export function ResultsTable({ assessments }: { assessments: AcademicAssessment[] }) {
  return (
    <div className="space-y-6">
      {assessments.map((a) => (
        <section key={a.id} className="overflow-hidden rounded-lg border border-line bg-surface">
          <header className="flex flex-wrap items-baseline gap-x-3 border-b border-line px-4 py-3">
            <h3 className="font-semibold">
              {a.semester ? `Semester ${a.semester}` : "Semester not stated"}
            </h3>
            <span className="text-sm text-ink-muted">
              {EXAM[a.exam_type] ?? a.exam_type}
              {a.exam_name ? ` · ${a.exam_name}` : ""}
            </span>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-subtle">
                <tr>
                  <th className="px-4 py-2 font-medium">Subject</th>
                  <th className="px-4 py-2 font-medium">Component</th>
                  <th className="px-4 py-2 font-medium">Marks</th>
                  <th className="px-4 py-2 font-medium">Grade</th>
                  <th className="px-4 py-2 font-medium">Credits</th>
                  <th className="px-4 py-2 font-medium">Attempt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {a.results.map((r) => (
                  <tr key={r.id}>
                    <td className="px-4 py-2">
                      {r.subject_name}
                      {r.subject_code && (
                        <span className="ml-2 font-mono text-xs text-ink-subtle">
                          {r.subject_code}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 capitalize text-ink-muted">{r.component}</td>
                    <td className="whitespace-nowrap px-4 py-2 tabular-nums">{marks(r)}</td>
                    <td className="px-4 py-2">
                      {r.grade ?? "—"}
                      {r.grade && r.grade_points === null && (
                        <span className="ml-1 text-xs text-ink-subtle">(scale not set)</span>
                      )}
                      {r.grade_points !== null && (
                        <span className="ml-1 text-xs text-ink-subtle">
                          {num(r.grade_points)} pts
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 tabular-nums">{num(r.credits) || "—"}</td>
                    <td className="px-4 py-2 tabular-nums">{r.attempt_number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
