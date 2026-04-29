import type { MonthlyDatum } from "../../components/charts/MonthlyBarChart";
import type { WeeklyPairDatum } from "../../components/charts/WeeklyPairBarChart";

export type Mission = {
  id: string;
  title: string;
  expectedSavingsKwh: number;
  status: "pending" | "done";
};

export type CashbackGoal = {
  month: number;                      // 11
  targetSavingsPercent: number;       // 10
  targetCashbackKrw: number;          // 11900
  daysRemaining: number;              // 15
  currentSavingsPercent: number;      // 8.4
  expectedSavingsPercent: number;     // 9.5
  progressPercent: number;            // 진행바 dark 부분 %
  expectedProgressPercent: number;    // 진행바 줄무늬 부분 %
};

export type CashbackTracker = {
  goal: CashbackGoal;
  weekly: { days: WeeklyPairDatum[] };
  monthly: {
    year: number;
    months: MonthlyDatum[];
    currentMonth: number;
  };
  missions: Mission[];
};
