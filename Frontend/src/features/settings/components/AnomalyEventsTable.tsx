import type { AnomalyEvent, AnomalySeverity, AnomalyStatus } from "../types";

type Props = { events: AnomalyEvent[] };

const SEVERITY_LABEL: Record<AnomalySeverity, string> = {
  low: "낮음",
  medium: "중간",
  high: "높음",
};

const SEVERITY_PILL: Record<AnomalySeverity, string> = {
  low: "bg-fill-2 text-ink-2",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-red-100 text-red-700",
};

const STATUS_LABEL: Record<AnomalyStatus, string> = {
  open: "미해결",
  resolved: "해결",
};

export function AnomalyEventsTable({ events }: Props) {
  if (events.length === 0) {
    return (
      <section className="border border-line-2 bg-canvas p-6">
        <p className="text-sm text-ink-3">
          현재 필터 조건에 해당하는 이벤트가 없습니다.
        </p>
      </section>
    );
  }

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="anomaly-events-heading"
    >
      <h3
        id="anomaly-events-heading"
        className="text-base font-semibold text-ink-1"
      >
        이벤트 ({events.length}건)
      </h3>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="border-b border-line-2 text-left text-ink-3">
            <th scope="col" className="py-2 font-normal">
              발생 시각
            </th>
            <th scope="col" className="py-2 font-normal">
              가전
            </th>
            <th scope="col" className="py-2 font-normal">
              심각도
            </th>
            <th scope="col" className="py-2 font-normal">
              설명
            </th>
            <th scope="col" className="py-2 font-normal">
              상태
            </th>
            <th scope="col" className="py-2 text-right font-normal">
              조치
            </th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={ev.id} className="border-b border-line-2/60">
              <td className="py-3 text-ink-2">{ev.occurredAt}</td>
              <td className="py-3 text-ink-1">{ev.appliance}</td>
              <td className="py-3">
                <span className={`px-2 py-0.5 text-xs ${SEVERITY_PILL[ev.severity]}`}>
                  {SEVERITY_LABEL[ev.severity]}
                </span>
              </td>
              <td className="py-3 text-ink-2">{ev.description}</td>
              <td className="py-3 text-ink-2">{STATUS_LABEL[ev.status]}</td>
              <td className="py-3 text-right">
                <button
                  type="button"
                  onClick={() => alert("준비 중입니다")}
                  className="bg-fill-2 px-3 py-1 text-xs text-ink-2"
                >
                  상세
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
