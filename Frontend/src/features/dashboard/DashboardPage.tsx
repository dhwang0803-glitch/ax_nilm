import { KpiCard } from "../../components/KpiCard";
import { useDashboardSummary } from "./api";
import { ApplianceShareCard } from "./components/ApplianceShareCard";
import { MonthlyUsageCard } from "./components/MonthlyUsageCard";
import { WeeklyUsageCard } from "./components/WeeklyUsageCard";

function formatKrw(value: number): string {
  return `₩${value.toLocaleString("ko-KR")}`;
}

function formatPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function DashboardPage() {
  const { data, isLoading, isError, refetch } = useDashboardSummary();

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-[28px] font-semibold text-ink-1">홈</h1>
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

  const monthlyDir = data.kpis.monthlyDeltaPercent < 0 ? "down" : "up";

  return (
    <div className="flex flex-col">
      <h1 className="text-[28px] font-semibold text-ink-1">홈</h1>
      <p className="mb-4 text-sm text-ink-3">분석형 — 데이터 우선 레이아웃</p>
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 flex flex-col gap-4">
          <WeeklyUsageCard data={data.weekly} />
          <MonthlyUsageCard data={data.monthly} />
        </div>
        <div className="flex flex-col gap-4">
          <KpiCard
            title="이번 달 사용량"
            value={data.kpis.monthlyUsageKwh}
            unit="kWh"
            delta={formatPercent(data.kpis.monthlyDeltaPercent)}
            deltaDir={monthlyDir}
          />
          <KpiCard
            title="예상 캐시백"
            value={formatKrw(data.kpis.estimatedCashbackKrw)}
            foot={`단가 ${data.kpis.cashbackRateKrwPerKwh} ₩/kWh`}
          />
          <KpiCard title="예상 요금" value={formatKrw(data.kpis.estimatedBillKrw)} />
          <ApplianceShareCard items={data.applianceBreakdown} />
        </div>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col">
      <h1 className="text-[28px] font-semibold text-ink-1">홈</h1>
      <p className="mb-4 text-sm text-ink-3">불러오는 중…</p>
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2 flex flex-col gap-4">
          <div className="h-[300px] animate-pulse border border-line-2 bg-fill-1" />
          <div className="h-[240px] animate-pulse border border-line-2 bg-fill-1" />
        </div>
        <div className="flex flex-col gap-4">
          <div className="h-24 animate-pulse border border-line-2 bg-fill-1" />
          <div className="h-24 animate-pulse border border-line-2 bg-fill-1" />
          <div className="h-24 animate-pulse border border-line-2 bg-fill-1" />
          <div className="h-48 animate-pulse border border-line-2 bg-fill-1" />
        </div>
      </div>
    </div>
  );
}
