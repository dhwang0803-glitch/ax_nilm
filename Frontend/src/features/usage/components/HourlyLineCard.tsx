import type { HourlyDatum } from "../types";
import { HourlyLineChart } from "./HourlyLineChart";

type Props = { data: HourlyDatum[] };

export function HourlyLineCard({ data }: Props) {
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <header className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-ink-1">시간대별 평균 (24h)</h4>
        <div className="flex items-center gap-3 text-[11px] text-ink-3">
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-fill-3" /> 평균
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-ink-1" /> 오늘
          </span>
        </div>
      </header>
      <div className="mt-3">
        <HourlyLineChart data={data} />
      </div>
    </section>
  );
}
