import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "../../lib/chart-colors";

export type WeeklyPairDatum = {
  day: string;
  thisWeek: number;
  prevWeek: number;
};

type Props = {
  data: WeeklyPairDatum[];
  height?: number;
};

export function WeeklyPairBarChart({ data, height = 200 }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 16, right: 0, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey="day"
          tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
          axisLine={{ stroke: CHART_COLORS.line }}
          tickLine={false}
        />
        <YAxis
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
        <Bar dataKey="prevWeek" name="지난 주" fill={CHART_COLORS.muted} />
        <Bar dataKey="thisWeek" name="이번 주" fill={CHART_COLORS.main} />
      </BarChart>
    </ResponsiveContainer>
  );
}
