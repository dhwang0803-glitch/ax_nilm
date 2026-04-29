import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { CHART_COLORS } from "../../lib/chart-colors";

export type MonthlyDatum = {
  month: number;
  kwh: number;
};

type Props = {
  data: MonthlyDatum[];
  currentMonth: number;
  height?: number;
};

export function MonthlyBarChart({ data, currentMonth, height = 180 }: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 16, right: 0, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey="month"
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
        <Bar dataKey="kwh">
          {data.map((d) => (
            <Cell
              key={d.month}
              fill={d.month === currentMonth ? CHART_COLORS.highlight : CHART_COLORS.main}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
