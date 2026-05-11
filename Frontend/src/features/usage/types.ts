import type { MonthlyDatum } from "../../components/charts/MonthlyBarChart";
import type { WeeklyPairDatum } from "../../components/charts/WeeklyPairBarChart";

export type HourlyDatum = {
  hour: number;
  average: number;
  today: number;
};

export type ApplianceBreakdownRow = {
  name: string;
  kwh: number;
  sharePercent: number;
  weekOverWeekPercent: number;
};

export type UsageAnalysis = {
  weekly: {
    days: WeeklyPairDatum[];
    thisWeekTotal: number;
    prevWeekTotal: number;
  };
  hourly: {
    hours: HourlyDatum[];
  };
  applianceBreakdown: ApplianceBreakdownRow[];
  monthly: {
    year: number;
    months: MonthlyDatum[];
    currentMonth: number;
  };
};
