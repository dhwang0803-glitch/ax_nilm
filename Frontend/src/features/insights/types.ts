export type InsightSeverity = "low" | "medium" | "high";

export type DiagnosisCategory = "이상" | "사용변화" | "정상";

export type InsightsKpi = {
  weeklyDiagnosisCount: number;
  weeklyDiagnosisDelta: number;
  monthlyEstimatedSavingKrw: number;
  monthlySavingDelta: number;
  modelConfidence: number;
};

export type AnomalyHighlight = {
  id: string;
  appliance: string;
  severity: InsightSeverity;
  category?: DiagnosisCategory;
  headline: string;
  cause?: string;
  detectedAt: string;
  // 점검 권고·예상 절약은 Recommendation으로 통합됨 (UX 일관성)
  recommendation?: string;
  expectedSavingKrw?: number;
};

export type Recommendation = {
  id: string;
  appliance: string;
  action: string;
  description: string;
  estimatedSavingKrw: number;
  confidence: number;
};

export type WeeklyTrendPoint = {
  weekLabel: string;
  diagnosisCount: number;
  estimatedSavingKrw: number;
};

export type InsightsResponse = {
  generatedAt: string;
  modelVersion: string;
  sampleHouseholds: number;
  kpi: InsightsKpi;
  anomalyHighlights: AnomalyHighlight[];
  recommendations: Recommendation[];
  weeklyTrend: WeeklyTrendPoint[];
};
