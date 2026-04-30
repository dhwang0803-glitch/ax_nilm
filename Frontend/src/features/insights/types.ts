export type InsightSeverity = "low" | "medium" | "high";

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
  headline: string;
  recommendation: string;
  detectedAt: string;
};

export type Recommendation = {
  id: string;
  appliance: string;
  action: string;
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
