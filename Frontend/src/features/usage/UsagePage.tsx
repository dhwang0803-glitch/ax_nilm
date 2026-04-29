import { MonthlyBarChart } from "../../components/charts/MonthlyBarChart";
import { WeeklyPairBarChart } from "../../components/charts/WeeklyPairBarChart";
import { useUsageAnalysis } from "./api";
import { ApplianceBreakdownCard } from "./components/ApplianceBreakdownCard";
import { HourlyLineCard } from "./components/HourlyLineCard";
import { UsageToolbar } from "./components/UsageToolbar";

export function UsagePage() {
  const { data, isLoading, isError, refetch } = useUsageAnalysis();

  if (isLoading) {
    return <UsageSkeleton />;
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-[28px] font-semibold text-ink-1">사용량 분석</h1>
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

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-[28px] font-semibold text-ink-1">사용량 분석</h1>
          <p className="text-sm text-ink-3">NILM 가전별 분해 결과</p>
        </div>
        <UsageToolbar />
      </header>

      <section className="border border-line-2 bg-canvas p-4">
        <header className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-ink-1">
            주간 전력 소모량 — 지난 주 vs 이번 주
          </h4>
          <div className="flex items-center gap-3 text-[11px] text-ink-3">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 bg-fill-3" /> 지난 주
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 bg-ink-2" /> 이번 주
            </span>
          </div>
        </header>
        <div className="mt-3">
          <WeeklyPairBarChart data={data.weekly.days} />
        </div>
      </section>

      <div className="grid grid-cols-2 gap-4">
        <HourlyLineCard data={data.hourly.hours} />
        <ApplianceBreakdownCard rows={data.applianceBreakdown} />
      </div>

      <section className="border border-line-2 bg-canvas p-4">
        <h4 className="text-sm font-semibold text-ink-1">월별 전력 소모량 — 추세</h4>
        <div className="mt-3">
          <MonthlyBarChart
            data={data.monthly.months}
            currentMonth={data.monthly.currentMonth}
            height={160}
          />
        </div>
      </section>
    </div>
  );
}

function UsageSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[28px] font-semibold text-ink-1">사용량 분석</h1>
      <div className="h-[260px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="grid grid-cols-2 gap-4">
        <div className="h-[240px] animate-pulse border border-line-2 bg-fill-1" />
        <div className="h-[240px] animate-pulse border border-line-2 bg-fill-1" />
      </div>
      <div className="h-[200px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
