import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "../../../lib/chart-colors";
import type { HourlyDatum } from "../types";

type Props = {
  data: HourlyDatum[];
  height?: number;
};

export function HourlyLineChart({ data, height = 180 }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey="hour"
          tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
          axisLine={{ stroke: CHART_COLORS.line }}
          tickLine={false}
          ticks={[0, 6, 12, 18, 23]}
        />
        <YAxis
          tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
          axisLine={{ stroke: CHART_COLORS.line }}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            background: CHART_COLORS.canvas,
            border: `1px solid ${CHART_COLORS.line}`,
            fontSize: 12,
          }}
        />
        <Line
          type="monotone"
          dataKey="average"
          name="평균"
          stroke={CHART_COLORS.muted}
          strokeWidth={1.5}
          strokeDasharray="4 4"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="today"
          name="오늘"
          stroke={CHART_COLORS.highlight}
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
