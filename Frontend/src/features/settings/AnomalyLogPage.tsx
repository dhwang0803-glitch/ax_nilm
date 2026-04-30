import { useMemo, useState } from "react";
import { KpiCard } from "../../components/KpiCard";
import { useAnomalyEvents } from "./api";
import {
  FilterPillsCard,
  type AnomalyFilterState,
} from "./components/FilterPillsCard";
import { AnomalyEventsTable } from "./components/AnomalyEventsTable";
import { ExportToolbar } from "./components/ExportToolbar";
import type { AnomalyEvent } from "./types";

const TODAY = new Date("2026-04-30");
const MS_PER_DAY = 86_400_000;

const INITIAL_FILTER: AnomalyFilterState = {
  period: "month",
  severities: [],
  statuses: [],
  appliance: null,
};

function periodCutoff(period: AnomalyFilterState["period"]): Date {
  if (period === "month") return new Date("2026-04-01");
  if (period === "30d") return new Date(TODAY.getTime() - 30 * MS_PER_DAY);
  return new Date(TODAY.getTime() - 90 * MS_PER_DAY);
}

function applyFilter(
  events: AnomalyEvent[],
  state: AnomalyFilterState
): AnomalyEvent[] {
  const cutoff = periodCutoff(state.period);
  return events.filter((ev) => {
    const t = new Date(ev.occurredAt.replace(" ", "T"));
    if (t < cutoff) return false;
    if (
      state.severities.length > 0 &&
      !state.severities.includes(ev.severity)
    ) {
      return false;
    }
    if (state.statuses.length > 0 && !state.statuses.includes(ev.status)) {
      return false;
    }
    if (state.appliance && ev.appliance !== state.appliance) return false;
    return true;
  });
}

function formatResponseMinutes(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return `${m}분`;
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`;
}

export function AnomalyLogPage() {
  const { data, isLoading, isError, refetch } = useAnomalyEvents();
  const [filter, setFilter] = useState<AnomalyFilterState>(INITIAL_FILTER);

  const filtered = useMemo(
    () => (data ? applyFilter(data.events, filter) : []),
    [data, filter]
  );

  const appliances = useMemo(
    () =>
      data ? Array.from(new Set(data.events.map((e) => e.appliance))) : [],
    [data]
  );

  if (isLoading) return <AnomalyLogSkeleton />;

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="text-2xl font-semibold text-ink-1">이상 탐지 내역</h2>
        </header>
        <div className="border border-line-2 bg-canvas p-6">
          <p className="text-sm text-ink-2">데이터를 불러올 수 없습니다.</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-3 border border-ink-1 bg-ink-1 px-3 py-1.5 text-xs text-canvas"
          >
            재시도
          </button>
        </div>
      </div>
    );
  }

  const unresolvedFiltered = filtered.filter((e) => e.status === "open").length;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-ink-1">이상 탐지 내역</h2>
          <p className="mt-1 text-sm text-ink-3">
            과거 감지된 이벤트를 조회하고 CSV/JSON/PDF 로 내보낼 수 있습니다.
          </p>
        </div>
        <ExportToolbar />
      </header>

      <div className="grid grid-cols-3 gap-3">
        <KpiCard
          title="이번 달 이벤트"
          value={filtered.length}
          unit="건"
          foot={`전체 ${data.kpi.monthCount}건 중`}
        />
        <KpiCard
          title="평균 응답 시간"
          value={formatResponseMinutes(data.kpi.avgResponseMinutes)}
        />
        <KpiCard
          title="미해결"
          value={unresolvedFiltered}
          unit="건"
          foot={`전체 ${data.kpi.unresolvedCount}건 중`}
        />
      </div>

      <FilterPillsCard
        state={filter}
        onChange={setFilter}
        appliances={appliances}
      />

      <AnomalyEventsTable events={filtered} />
    </div>
  );
}

function AnomalyLogSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="h-[100px] animate-pulse border border-line-2 bg-fill-1" />
        <div className="h-[100px] animate-pulse border border-line-2 bg-fill-1" />
        <div className="h-[100px] animate-pulse border border-line-2 bg-fill-1" />
      </div>
      <div className="h-[180px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[320px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
