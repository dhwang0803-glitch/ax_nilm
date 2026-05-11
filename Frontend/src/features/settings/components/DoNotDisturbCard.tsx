import { useMemo, useState } from "react";
import type { DoNotDisturb } from "../types";

type Props = { initial: DoNotDisturb };

function buildHalfHourOptions() {
  const options: Array<{ value: number; label: string }> = [];
  for (let m = 0; m < 24 * 60; m += 30) {
    const hh = String(Math.floor(m / 60)).padStart(2, "0");
    const mm = String(m % 60).padStart(2, "0");
    options.push({ value: m, label: `${hh}:${mm}` });
  }
  return options;
}

export function DoNotDisturbCard({ initial }: Props) {
  const [enabled, setEnabled] = useState(initial.enabled);
  const [startMinutes, setStartMinutes] = useState(initial.startMinutes);
  const [endMinutes, setEndMinutes] = useState(initial.endMinutes);

  const options = useMemo(buildHalfHourOptions, []);

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="do-not-disturb-heading"
    >
      <header className="flex items-center justify-between">
        <h3
          id="do-not-disturb-heading"
          className="text-base font-semibold text-ink-1"
        >
          방해 금지 시간
        </h3>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-2">
          <input
            type="checkbox"
            role="switch"
            aria-label="방해 금지 사용"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-4 w-4"
          />
          {enabled ? "사용" : "사용 안 함"}
        </label>
      </header>
      <p className="mt-2 text-sm text-ink-3">
        설정한 시간대에는 푸시·SMS 발송을 보류합니다 (이상 탐지 긴급 알림 제외).
      </p>
      <div className="mt-4 flex items-center gap-3 text-sm">
        <label htmlFor="dnd-start" className="text-ink-3">
          시작
        </label>
        <select
          id="dnd-start"
          value={startMinutes}
          onChange={(e) => setStartMinutes(Number(e.target.value))}
          disabled={!enabled}
          className="border border-line-2 bg-canvas px-2 py-1 text-sm disabled:opacity-50"
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <span className="text-ink-3">→</span>
        <label htmlFor="dnd-end" className="text-ink-3">
          종료
        </label>
        <select
          id="dnd-end"
          value={endMinutes}
          onChange={(e) => setEndMinutes(Number(e.target.value))}
          disabled={!enabled}
          className="border border-line-2 bg-canvas px-2 py-1 text-sm disabled:opacity-50"
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}
