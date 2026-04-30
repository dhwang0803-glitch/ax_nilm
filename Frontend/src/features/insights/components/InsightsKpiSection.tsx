import { KpiCard } from "../../../components/KpiCard";
import type { InsightsKpi } from "../types";

type Props = {
  kpi: InsightsKpi;
  sampleHouseholds: number;
};

function deltaText(value: number, suffix: string): string {
  const sign = value >= 0 ? "+" : "";
  return `전주 대비 ${sign}${value.toLocaleString()}${suffix}`;
}

function savingDeltaText(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `전월 대비 ${sign}${value.toLocaleString()}원`;
}

export function InsightsKpiSection({ kpi, sampleHouseholds }: Props) {
  const confidencePct = Math.round(kpi.modelConfidence * 100);

  return (
    <section
      className="grid grid-cols-3 gap-4"
      aria-label="진단 요약 KPI"
    >
      <KpiCard
        title="이번 주 진단"
        value={kpi.weeklyDiagnosisCount.toLocaleString()}
        unit="건"
        delta={deltaText(kpi.weeklyDiagnosisDelta, "건")}
      />
      <KpiCard
        title="이번 달 예상 절약"
        value={kpi.monthlyEstimatedSavingKrw.toLocaleString()}
        unit="원"
        delta={savingDeltaText(kpi.monthlySavingDelta)}
      />
      <KpiCard
        title="모델 신뢰도"
        value={confidencePct}
        unit="%"
        foot={`표본 ${sampleHouseholds}세대`}
      />
    </section>
  );
}
