import type { CashbackGoal } from "../types";

type Props = { goal: CashbackGoal };

const STRIPE_PATTERN =
  "repeating-linear-gradient(45deg, var(--ink-3) 0 4px, var(--fill-2) 4px 8px)";

export function GoalProgressCard({ goal }: Props) {
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <header className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-ink-1">
          {goal.month}월 목표 — {goal.targetSavingsPercent}% 절감 / ₩
          {goal.targetCashbackKrw.toLocaleString("ko-KR")}
        </h4>
        <span className="bg-fill-2 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-2">
          D-{goal.daysRemaining}
        </span>
      </header>
      <div
        className="mt-3 flex h-6 border border-line-2 bg-fill-2"
        role="progressbar"
        aria-valuenow={goal.currentSavingsPercent}
        aria-valuemin={0}
        aria-valuemax={goal.targetSavingsPercent}
        aria-label={`목표 진행률: 현재 ${goal.currentSavingsPercent}% / 목표 ${goal.targetSavingsPercent}%`}
      >
        <div
          className="flex items-center bg-ink-2 pl-2 font-mono text-[11px] text-canvas"
          style={{ width: `${goal.progressPercent}%` }}
        >
          {goal.progressPercent}%
        </div>
        <div
          style={{
            width: `${goal.expectedProgressPercent}%`,
            background: STRIPE_PATTERN,
          }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-ink-3">
        <span>현재 {goal.currentSavingsPercent}%</span>
        <span>예상 {goal.expectedSavingsPercent}%</span>
        <span>목표 {goal.targetSavingsPercent}%</span>
      </div>
    </section>
  );
}
