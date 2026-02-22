"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatLine } from "@/lib/oddsFormat";

const STEP_OPTIONS = [0.5, 1, 2, 5, 10];
const MAX_AXIS_TICKS = 7;

function collectNumeric(values: Array<number | null | undefined>) {
  return values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

function pickStep(span: number): number {
  if (span <= 0) {
    return STEP_OPTIONS[0];
  }
  for (const step of STEP_OPTIONS) {
    if (span / step <= MAX_AXIS_TICKS) {
      return step;
    }
  }
  return STEP_OPTIONS[STEP_OPTIONS.length - 1];
}

function buildAxis(values: number[]) {
  if (values.length === 0) {
    return {
      domain: ["auto", "auto"] as [number | string, number | string],
      ticks: undefined as number[] | undefined,
      min: null as number | null,
      max: null as number | null,
      step: null as number | null,
    };
  }

  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = rawMax - rawMin;
  const step = pickStep(span);

  let snappedMin = Math.floor(rawMin / step) * step;
  let snappedMax = Math.ceil(rawMax / step) * step;
  if (snappedMin === snappedMax) {
    snappedMin -= step;
    snappedMax += step;
  }

  const ticks: number[] = [];
  for (let value = snappedMin; value <= snappedMax + step / 10; value += step) {
    ticks.push(Number(value.toFixed(6)));
    if (ticks.length > 20) {
      break;
    }
  }

  return {
    domain: [snappedMin, snappedMax] as [number, number],
    ticks,
    min: rawMin,
    max: rawMax,
    step,
  };
}

export function MovementChart({
  points,
}: {
  points: Array<{
    timestamp: string;
    spreads: number | null;
    totals: number | null;
  }>;
}) {
  const data = points.map((point) => ({
    ...point,
    time: new Date(point.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
  }));

  const spreadAxis = buildAxis(collectNumeric(points.map((point) => point.spreads)));
  const totalAxis = buildAxis(collectNumeric(points.map((point) => point.totals)));

  return (
    <div className="h-96 w-full rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        <span className="rounded border border-borderTone bg-panelSoft px-2 py-1 text-textMute">
          <span className="text-[#47c7a6]">Spread</span>:{" "}
          <span className="text-textMain">
            {spreadAxis.min == null || spreadAxis.max == null
              ? "-"
              : `${formatLine(spreadAxis.min, 1)} -> ${formatLine(spreadAxis.max, 1)}`}
          </span>
          {spreadAxis.step != null && (
            <span className="text-textMute"> (step {formatLine(spreadAxis.step, 1)})</span>
          )}
        </span>
        <span className="rounded border border-borderTone bg-panelSoft px-2 py-1 text-textMute">
          <span className="text-[#f0bc62]">Total</span>:{" "}
          <span className="text-textMain">
            {totalAxis.min == null || totalAxis.max == null
              ? "-"
              : `${formatLine(totalAxis.min, 1)} -> ${formatLine(totalAxis.max, 1)}`}
          </span>
          {totalAxis.step != null && (
            <span className="text-textMute"> (step {formatLine(totalAxis.step, 1)})</span>
          )}
        </span>
      </div>

      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="#1b2533" strokeDasharray="4 4" />
            <XAxis dataKey="time" stroke="#8f9aae" minTickGap={18} />
            <YAxis
              yAxisId="spread"
              stroke="#47c7a6"
              domain={spreadAxis.domain}
              ticks={spreadAxis.ticks}
              width={56}
              label={{
                value: "Spread",
                angle: -90,
                position: "insideLeft",
                style: { fill: "#47c7a6", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" },
              }}
              tickFormatter={(value) => formatLine(Number(value), 1)}
            />
            <YAxis
              yAxisId="total"
              orientation="right"
              stroke="#f0bc62"
              domain={totalAxis.domain}
              ticks={totalAxis.ticks}
              width={56}
              label={{
                value: "Total",
                angle: 90,
                position: "insideRight",
                style: { fill: "#f0bc62", fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase" },
              }}
              tickFormatter={(value) => formatLine(Number(value), 1)}
            />
            <Tooltip
              formatter={(value, name) => {
                const rawValue = Array.isArray(value) ? value[0] : value;
                const numeric = typeof rawValue === "number" ? rawValue : Number(rawValue);
                if (Number.isNaN(numeric)) {
                  return ["-", name];
                }
                return [formatLine(numeric, 1), name];
              }}
              contentStyle={{
                background: "#0d131d",
                border: "1px solid #263244",
                borderRadius: "8px",
                color: "#d6dde7",
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="spreads"
              yAxisId="spread"
              stroke="#47c7a6"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Consensus Spread"
            />
            <Line
              type="monotone"
              dataKey="totals"
              yAxisId="total"
              stroke="#f0bc62"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Consensus Total"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
