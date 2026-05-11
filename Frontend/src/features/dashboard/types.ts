export type DashboardKpis = {
  monthlyUsageKwh: number;
  monthlyDeltaPercent: number;
  estimatedCashbackKrw: number;
  cashbackRateKrwPerKwh: number;
  estimatedBillKrw: number;
};

export type WeeklyDay = { day: string; thisWeek: number; prevWeek: number };

export type WeeklyData = {
  days: WeeklyDay[];
  thisWeekTotal: number;
  prevWeekTotal: number;
  avgPerDay: number;
};

export type MonthlyEntry = { month: number; kwh: number };

export type MonthlyData = {
  year: number;
  months: MonthlyEntry[];
  currentMonth: number;
};

export type ApplianceBreakdownItem = { name: string; sharePercent: number };

export type DashboardSummary = {
  kpis: DashboardKpis;
  weekly: WeeklyData;
  monthly: MonthlyData;
  applianceBreakdown: ApplianceBreakdownItem[];
};
