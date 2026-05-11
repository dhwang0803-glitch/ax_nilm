import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "../../../lib/chart-colors";
import type { WeeklyTrendPoint } from "../types";

type Props = {
  data: WeeklyTrendPoint[];
};

export function WeeklyTrendCard({ data }: Props) {
  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="insights-trend-heading"
    >
      <h3
        id="insights-trend-heading"
        className="text-base font-semibold text-ink-1"
      >
        주간 진단 추이
      </h3>
      <p className="mt-1 text-sm text-ink-3">
        막대 = 진단 건수 / 라인 = 예상 절약(원)
      </p>
      {data.length === 0 ? (
        <p className="mt-4 text-sm text-ink-3">표시할 데이터가 없습니다.</p>
      ) : (
        <div className="mt-4">
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart
              data={data}
              margin={{ top: 16, right: 8, bottom: 0, left: -16 }}
            >
              <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
              <XAxis
                dataKey="weekLabel"
                tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
                axisLine={{ stroke: CHART_COLORS.line }}
                tickLine={false}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
                axisLine={{ stroke: CHART_COLORS.line }}
                tickLine={false}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
                axisLine={{ stroke: CHART_COLORS.line }}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: CHART_COLORS.fill1 }}
                contentStyle={{
                  background: CHART_COLORS.canvas,
                  border: `1px solid ${CHART_COLORS.line}`,
                  fontSize: 12,
                }}
              />
              <Bar
                yAxisId="left"
                dataKey="diagnosisCount"
                name="진단 건수"
                fill={CHART_COLORS.muted}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="estimatedSavingKrw"
                name="예상 절약"
                stroke={CHART_COLORS.highlight}
                strokeWidth={2}
                dot={{ fill: CHART_COLORS.highlight, r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
