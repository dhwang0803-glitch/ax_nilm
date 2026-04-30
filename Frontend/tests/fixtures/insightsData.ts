import type { InsightsResponse } from "../../src/features/insights/types";

export const mockInsights: InsightsResponse = {
  generatedAt: "2026-04-30 09:12",
  modelVersion: "v2.4",
  sampleHouseholds: 79,
  kpi: {
    weeklyDiagnosisCount: 12,
    weeklyDiagnosisDelta: 3,
    monthlyEstimatedSavingKrw: 9840,
    monthlySavingDelta: 1230,
    modelConfidence: 0.92,
  },
  anomalyHighlights: [
    {
      id: "hl-001",
      appliance: "에어컨",
      severity: "high",
      headline: "정상 대비 25% 과소비",
      recommendation: "필터 청소 후 설정 온도를 1℃ 올리면 월 1,200원 절약 예상.",
      detectedAt: "2026-04-29 14:22",
    },
    {
      id: "hl-002",
      appliance: "김치냉장고",
      severity: "medium",
      headline: "평소 대비 12% 추가 소비",
      recommendation: "도어 패킹 점검 권장. 동일 모델 평균 대비 8% 높음.",
      detectedAt: "2026-04-28 09:11",
    },
  ],
  recommendations: [
    {
      id: "rec-001",
      appliance: "에어컨",
      action: "필터 청소 · 설정 온도 +1℃",
      estimatedSavingKrw: 1200,
      confidence: 0.91,
    },
    {
      id: "rec-002",
      appliance: "김치냉장고",
      action: "도어 패킹 점검 · 정온 모드 전환",
      estimatedSavingKrw: 540,
      confidence: 0.78,
    },
    {
      id: "rec-003",
      appliance: "건조기",
      action: "표준 코스 대신 저온 코스 사용 (주 2회 기준)",
      estimatedSavingKrw: 880,
      confidence: 0.85,
    },
    {
      id: "rec-004",
      appliance: "TV",
      action: "대기전력 차단 멀티탭 사용 권장",
      estimatedSavingKrw: 320,
      confidence: 0.69,
    },
    {
      id: "rec-005",
      appliance: "세탁기",
      action: "찬물 세탁 빈도 증가 (주 1회 → 3회)",
      estimatedSavingKrw: 410,
      confidence: 0.74,
    },
    {
      id: "rec-006",
      appliance: "인덕션",
      action: "여열 활용 — 종료 1분 전 전원 차단",
      estimatedSavingKrw: 180,
      confidence: 0.62,
    },
  ],
  weeklyTrend: [
    { weekLabel: "W14", diagnosisCount: 7, estimatedSavingKrw: 6100 },
    { weekLabel: "W15", diagnosisCount: 9, estimatedSavingKrw: 7400 },
    { weekLabel: "W16", diagnosisCount: 8, estimatedSavingKrw: 7050 },
    { weekLabel: "W17", diagnosisCount: 11, estimatedSavingKrw: 8900 },
    { weekLabel: "W18", diagnosisCount: 12, estimatedSavingKrw: 9840 },
  ],
};
