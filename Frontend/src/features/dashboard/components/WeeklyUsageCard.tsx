import type { WeeklyData } from "../types";
import { WeeklyPairBarChart } from "./WeeklyPairBarChart";

type Props = { data: WeeklyData };

export function WeeklyUsageCard({ data }: Props) {
  const diff = data.thisWeekTotal - data.prevWeekTotal;
  const diffLabel = `${diff >= 0 ? "+" : ""}${diff.toFixed(1)}`;
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <header className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-ink-1">주간 전력 소모량</h4>
        <div className="flex border border-line-2 text-[11px]">
          {["주", "월", "연"].map((label, idx) => (
            <span
              key={label}
              className={`px-2 py-1 ${idx === 0 ? "bg-ink-1 text-canvas" : "text-ink-3"}`}
            >
              {label}
            </span>
          ))}
        </div>
      </header>
      <div className="mt-3">
        <WeeklyPairBarChart data={data.days} />
      </div>
      <div className="mt-2 grid grid-cols-4 gap-2 border-t border-line-3 pt-3">
        <Stat label="이번 주 합계" value={`${data.thisWeekTotal} kWh`} />
        <Stat label="지난 주" value={`${data.prevWeekTotal} kWh`} />
        <Stat label="차이" value={diffLabel} />
        <Stat label="평균/일" value={`${data.avgPerDay} kWh`} />
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-3">{label}</span>
      <div className="text-lg font-semibold tabular-nums text-ink-1">{value}</div>
    </div>
  );
}
