import { useState } from "react";
import type { EmailToggleKey, EmailToggles } from "../types";

type Props = { initial: EmailToggles };

const TOGGLES: Array<{ key: EmailToggleKey; label: string; desc: string }> = [
  {
    key: "anomaly",
    label: "이상 탐지",
    desc: "가전 이상 작동·과소비 감지 시 즉시 알림",
  },
  {
    key: "cashback",
    label: "캐시백 정산",
    desc: "월별 정산·달성 알림",
  },
  {
    key: "weeklyReport",
    label: "주간 리포트",
    desc: "매주 월요일 사용량·절약 요약",
  },
  {
    key: "policy",
    label: "정책 안내",
    desc: "KEPCO 요금제·DR 프로그램 정책 변경",
  },
];

export function EmailNotificationToggleCard({ initial }: Props) {
  const [toggles, setToggles] = useState<EmailToggles>(initial);

  const update = (key: EmailToggleKey) => (checked: boolean) =>
    setToggles((prev) => ({ ...prev, [key]: checked }));

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="email-toggle-heading"
    >
      <header>
        <h3
          id="email-toggle-heading"
          className="text-base font-semibold text-ink-1"
        >
          이메일 수신 항목
        </h3>
      </header>
      <ul className="mt-4 flex flex-col gap-3">
        {TOGGLES.map((t) => (
          <li
            key={t.key}
            className="flex items-start justify-between gap-4 border-b border-line-2/60 pb-3 last:border-0 last:pb-0"
          >
            <div>
              <p className="text-sm text-ink-1">{t.label}</p>
              <p className="mt-0.5 text-xs text-ink-3">{t.desc}</p>
            </div>
            <label className="cursor-pointer">
              <input
                type="checkbox"
                role="switch"
                aria-label={`${t.label} 이메일 수신`}
                checked={toggles[t.key]}
                onChange={(e) => update(t.key)(e.target.checked)}
                className="h-4 w-4"
              />
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
