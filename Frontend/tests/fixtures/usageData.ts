import type { UsageAnalysis } from "../../src/features/usage/types";

const HOURS = Array.from({ length: 24 }, (_, h) => {
  // 가벼운 sin 곡선 + 저녁 피크로 자연스러운 mock
  const base = 1.2;
  const wave = Math.sin(((h - 6) * Math.PI) / 12) * 0.6;
  const eveningSpike = h >= 18 && h <= 22 ? 0.8 : 0;
  return {
    hour: h,
    average: Number((base + wave + eveningSpike).toFixed(2)),
    today: Number((base + 0.2 + Math.sin(((h - 7) * Math.PI) / 12) * 0.7 + (h >= 19 && h <= 22 ? 1.0 : 0)).toFixed(2)),
  };
});

export const mockUsageAnalysis: UsageAnalysis = {
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
  },
  hourly: { hours: HOURS },
  applianceBreakdown: [
    { name: "에어컨/난방", kwh: 16.4, sharePercent: 36, weekOverWeekPercent: 12 },
    { name: "냉장고", kwh: 10.0, sharePercent: 22, weekOverWeekPercent: -2 },
    { name: "세탁/건조", kwh: 8.2, sharePercent: 18, weekOverWeekPercent: 5 },
    { name: "주방", kwh: 5.5, sharePercent: 12, weekOverWeekPercent: 0 },
    { name: "조명/기타", kwh: 5.4, sharePercent: 12, weekOverWeekPercent: -3 },
  ],
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
};
