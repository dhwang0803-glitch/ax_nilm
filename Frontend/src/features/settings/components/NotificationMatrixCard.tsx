import { useState } from "react";
import type { NotificationKind, NotificationMatrixRow } from "../types";

type Props = { matrix: NotificationMatrixRow[] };

type Channel = "email" | "sms" | "push";

const KIND_LABEL: Record<NotificationKind, string> = {
  anomaly: "이상 탐지",
  cashback: "캐시백 정산",
  weeklyReport: "주간 리포트",
  system: "시스템 공지",
};

const CHANNELS: Array<{ key: Channel; label: string }> = [
  { key: "email", label: "이메일" },
  { key: "sms", label: "SMS" },
  { key: "push", label: "푸시" },
];

export function NotificationMatrixCard({ matrix }: Props) {
  const [rows, setRows] = useState<NotificationMatrixRow[]>(matrix);

  const toggle = (kind: NotificationKind, channel: Channel) => {
    setRows((prev) =>
      prev.map((row) =>
        row.kind === kind ? { ...row, [channel]: !row[channel] } : row
      )
    );
  };

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="notification-matrix-heading"
    >
      <header className="flex items-center justify-between">
        <h3
          id="notification-matrix-heading"
          className="text-base font-semibold text-ink-1"
        >
          알림 종류 / 채널
        </h3>
        <button
          type="button"
          className="bg-fill-2 px-3 py-1 text-xs text-ink-2"
          onClick={() => alert("준비 중입니다")}
        >
          저장
        </button>
      </header>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="border-b border-line-2 text-left text-ink-3">
            <th scope="col" className="py-2 font-normal">
              알림
            </th>
            {CHANNELS.map((c) => (
              <th
                key={c.key}
                scope="col"
                className="py-2 text-center font-normal"
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.kind} className="border-b border-line-2/60">
              <th
                scope="row"
                className="py-3 text-left font-normal text-ink-1"
              >
                {KIND_LABEL[row.kind]}
              </th>
              {CHANNELS.map((c) => {
                const id = `notif-${row.kind}-${c.key}`;
                const label = `${KIND_LABEL[row.kind]} ${c.label}`;
                return (
                  <td key={c.key} className="py-3 text-center">
                    <input
                      id={id}
                      type="checkbox"
                      aria-label={label}
                      checked={row[c.key]}
                      onChange={() => toggle(row.kind, c.key)}
                      className="h-4 w-4"
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
