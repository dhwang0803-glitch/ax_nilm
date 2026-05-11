import type { CashbackTracker } from "../../src/features/cashback/types";

export const mockCashbackTracker: CashbackTracker = {
  goal: {
    month: 11,
    targetSavingsPercent: 10,
    targetCashbackKrw: 11900,
    daysRemaining: 15,
    currentSavingsPercent: 8.4,
    expectedSavingsPercent: 9.5,
    progressPercent: 62,
    expectedProgressPercent: 8,
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
  missions: [
    { id: "m1", title: "저녁 19–21시 건조기 미사용", expectedSavingsKwh: 2.1, status: "pending" },
    { id: "m2", title: "대기전력 멀티탭 OFF", expectedSavingsKwh: 0.7, status: "done" },
    { id: "m3", title: "에어컨 26→27℃", expectedSavingsKwh: 1.4, status: "pending" },
  ],
};
