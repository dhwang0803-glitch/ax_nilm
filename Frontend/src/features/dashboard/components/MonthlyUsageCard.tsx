import { MonthlyBarChart } from "../../../components/charts/MonthlyBarChart";
import type { MonthlyData } from "../types";

type Props = { data: MonthlyData };

export function MonthlyUsageCard({ data }: Props) {
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <header className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-ink-1">월별 전력 소모량 — 12개월 추세</h4>
        <span className="bg-fill-2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ink-2">
          {data.year}
        </span>
      </header>
      <div className="mt-3">
        <MonthlyBarChart data={data.months} currentMonth={data.currentMonth} />
      </div>
    </section>
  );
}
