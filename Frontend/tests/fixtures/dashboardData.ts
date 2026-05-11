import type { DashboardSummary } from "../../src/features/dashboard/types";

export const mockDashboardSummary: DashboardSummary = {
  kpis: {
    monthlyUsageKwh: 218,
    monthlyDeltaPercent: -8.4,
    estimatedCashbackKrw: 4820,
    cashbackRateKrwPerKwh: 30,
    estimatedBillKrw: 31200,
  },
  weekly: {
    days: [
      { day: "월", prevWeek: 5.8, thisWeek: 6.2 },
      { day: "화", prevWeek: 6.1, thisWeek: 6.5 },
      { day: "수", prevWeek: 6.5, thisWeek: 6.0 },
      { day: "목", prevWeek: 6.3, thisWeek: 6.8 },
      { day: "금", prevWeek: 7.0, thisWeek: 7.2 },
      { day: "토", prevWeek: 6.8, thisWeek: 6.5 },
      { day: "일", prevWeek: 4.5, thisWeek: 6.3 },
    ],
    thisWeekTotal: 45.5,
    prevWeekTotal: 43.0,
    avgPerDay: 6.5,
  },
  monthly: {
    year: 2026,
    months: [
      { month: 1, kwh: 285 },
      { month: 2, kwh: 252 },
      { month: 3, kwh: 198 },
      { month: 4, kwh: 175 },
      { month: 5, kwh: 168 },
      { month: 6, kwh: 220 },
      { month: 7, kwh: 285 },
      { month: 8, kwh: 312 },
      { month: 9, kwh: 245 },
      { month: 10, kwh: 210 },
      { month: 11, kwh: 218 },
      { month: 12, kwh: 0 },
    ],
    currentMonth: 11,
  },
  applianceBreakdown: [
    { name: "냉난방", sharePercent: 36 },
    { name: "냉장고", sharePercent: 22 },
    { name: "세탁/건조", sharePercent: 18 },
    { name: "주방", sharePercent: 12 },
    { name: "기타", sharePercent: 12 },
  ],
};
