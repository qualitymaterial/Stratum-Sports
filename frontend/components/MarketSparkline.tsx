"use client";

import { Line, LineChart, ResponsiveContainer } from "recharts";

export function MarketSparkline({ values }: { values: number[] }) {
  const data = values.map((value, idx) => ({ idx, value }));
  if (data.length === 0) {
    return <div className="h-16 w-full rounded border border-borderTone bg-panelSoft" />;
  }

  return (
    <div className="h-16 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <Line
            type="monotone"
            dataKey="value"
            dot={false}
            stroke="#47c7a6"
            strokeWidth={2}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
