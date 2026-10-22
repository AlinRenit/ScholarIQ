"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const INK_MUTED = "var(--color-ink-muted)";
const LINE = "var(--color-line)";
const SERIES = "var(--color-accent)";
const SURFACE = "var(--color-surface)";

function TipBox({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-sm">
      <p className="font-medium text-ink">{title}</p>
      {lines.map((l) => (
        <p key={l} className="text-ink-muted">
          {l}
        </p>
      ))}
    </div>
  );
}

export type TrendPoint = { semester: string; percent: number; counted: number };

/** Single series: marks-based semester percentage. No legend; the heading names it. */
export function SemesterTrendChart({ points }: { points: TrendPoint[] }) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <LineChart data={points} margin={{ top: 12, right: 16, bottom: 4, left: -16 }}>
          <CartesianGrid vertical={false} stroke={LINE} strokeWidth={1} />
          <XAxis
            dataKey="semester"
            tick={{ fill: INK_MUTED, fontSize: 12 }}
            axisLine={{ stroke: LINE }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tick={{ fill: INK_MUTED, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ stroke: LINE }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as TrendPoint | undefined;
              return active && p ? (
                <TipBox
                  title={p.semester}
                  lines={[`${p.percent}% of maximum marks`, `${p.counted} results counted`]}
                />
              ) : null;
            }}
          />
          <Line
            type="linear"
            dataKey="percent"
            stroke={SERIES}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={{ r: 4, fill: SERIES, stroke: SURFACE, strokeWidth: 2 }}
            activeDot={{ r: 6, fill: SERIES, stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export type SubjectBar = { name: string; percent: number; band: string };

/** Latest marks-based score per subject, with the band thresholds as reference lines. */
export function SubjectScoreChart({
  bars,
  strongAt,
  attentionBelow,
}: {
  bars: SubjectBar[];
  strongAt: number;
  attentionBelow: number;
}) {
  return (
    <div className="w-full" style={{ height: 40 + bars.length * 36 }}>
      <ResponsiveContainer>
        <BarChart
          data={bars}
          layout="vertical"
          margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
          barCategoryGap={8}
        >
          <CartesianGrid horizontal={false} stroke={LINE} strokeWidth={1} />
          <XAxis
            type="number"
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tick={{ fill: INK_MUTED, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={130}
            tick={{ fill: INK_MUTED, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <ReferenceLine
            x={attentionBelow * 100}
            stroke={LINE}
            strokeWidth={1.5}
            strokeDasharray="4 4"
            zIndex={0}
          />
          <ReferenceLine
            x={strongAt * 100}
            stroke={LINE}
            strokeWidth={1.5}
            strokeDasharray="4 4"
            zIndex={0}
          />
          <Tooltip
            cursor={{ fill: "var(--color-canvas)" }}
            content={({ active, payload }) => {
              const p = payload?.[0]?.payload as SubjectBar | undefined;
              return active && p ? (
                <TipBox title={p.name} lines={[`${p.percent}% of maximum marks`, p.band]} />
              ) : null;
            }}
          />
          <Bar
            dataKey="percent"
            fill={SERIES}
            maxBarSize={20}
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
            label={{
              position: "right",
              fill: INK_MUTED,
              fontSize: 12,
              formatter: (v: unknown) => `${String(v)}%`,
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
