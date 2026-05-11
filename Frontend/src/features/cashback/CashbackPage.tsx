import { MonthlyBarChart } from "../../components/charts/MonthlyBarChart";
import { WeeklyPairBarChart } from "../../components/charts/WeeklyPairBarChart";
import { useCashbackTracker } from "./api";
import { GoalProgressCard } from "./components/GoalProgressCard";
import { TodayMissionsCard } from "./components/TodayMissionsCard";

export function CashbackPage() {
  const { data, isLoading, isError, refetch } = useCashbackTracker();

  if (isLoading) {
    return <CashbackSkeleton />;
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-[28px] font-semibold text-ink-1">목표 트래커</h1>
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
      <header>
        <h1 className="text-[28px] font-semibold text-ink-1">목표 트래커</h1>
        <p className="text-sm text-ink-3">월간 절감 목표 + 진행 상황</p>
      </header>

      <GoalProgressCard goal={data.goal} />

      <div className="grid grid-cols-2 gap-4">
        <section className="border border-line-2 bg-canvas p-4">
          <h4 className="text-sm font-semibold text-ink-1">주간 전력 소모량</h4>
          <div className="mt-3">
            <WeeklyPairBarChart data={data.weekly.days} height={160} />
          </div>
        </section>
        <section className="border border-line-2 bg-canvas p-4">
          <h4 className="text-sm font-semibold text-ink-1">월별 전력 소모량</h4>
          <div className="mt-3">
            <MonthlyBarChart
              data={data.monthly.months}
              currentMonth={data.monthly.currentMonth}
              height={160}
            />
          </div>
        </section>
      </div>

      <TodayMissionsCard missions={data.missions} />
    </div>
  );
}

function CashbackSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[28px] font-semibold text-ink-1">목표 트래커</h1>
      <div className="h-24 animate-pulse border border-line-2 bg-fill-1" />
      <div className="grid grid-cols-2 gap-4">
        <div className="h-[200px] animate-pulse border border-line-2 bg-fill-1" />
        <div className="h-[200px] animate-pulse border border-line-2 bg-fill-1" />
      </div>
      <div className="h-[180px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
