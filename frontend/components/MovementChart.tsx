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

  return (
    <div className="h-80 w-full rounded-xl border border-borderTone bg-panel p-4 shadow-terminal">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke="#1b2533" strokeDasharray="4 4" />
          <XAxis dataKey="time" stroke="#8f9aae" minTickGap={18} />
          <YAxis
            yAxisId="spread"
            stroke="#47c7a6"
            domain={["auto", "auto"]}
            width={56}
            tickFormatter={(value) => formatLine(Number(value), 1)}
          />
          <YAxis
            yAxisId="total"
            orientation="right"
            stroke="#f0bc62"
            domain={["auto", "auto"]}
            width={56}
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
  );
}
