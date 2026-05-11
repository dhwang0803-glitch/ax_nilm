import { useInsights } from "./api";
import { AnomalyHighlightCard } from "./components/AnomalyHighlightCard";
import { InsightsKpiSection } from "./components/InsightsKpiSection";
import { RecommendationsTable } from "./components/RecommendationsTable";
import { WeeklyTrendCard } from "./components/WeeklyTrendCard";

export function InsightsPage() {
  const { data, isLoading, isError, refetch } = useInsights();

  if (isLoading) return <InsightsSkeleton />;

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-3">
        <header>
          <h2 className="text-2xl font-semibold text-ink-1">AI 진단</h2>
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

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-ink-1">AI 진단</h2>
          <p className="mt-1 text-sm text-ink-3">
            NILM 모델이 가전별 사용 패턴을 분석해 이상·절약 권고를 제공합니다.
          </p>
        </div>
        <p className="font-mono text-xs text-ink-3">
          마지막 분석: {data.generatedAt} · 모델 {data.modelVersion}
        </p>
      </header>
      <InsightsKpiSection
        kpi={data.kpi}
        sampleHouseholds={data.sampleHouseholds}
      />
      <AnomalyHighlightCard highlights={data.anomalyHighlights} />
      <RecommendationsTable recommendations={data.recommendations} />
      <WeeklyTrendCard data={data.weeklyTrend} />
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-[60px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="grid grid-cols-3 gap-4">
        <div className="h-[110px] animate-pulse border border-line-2 bg-fill-1" />
        <div className="h-[110px] animate-pulse border border-line-2 bg-fill-1" />
        <div className="h-[110px] animate-pulse border border-line-2 bg-fill-1" />
      </div>
      <div className="h-[180px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[260px] animate-pulse border border-line-2 bg-fill-1" />
      <div className="h-[260px] animate-pulse border border-line-2 bg-fill-1" />
    </div>
  );
}
