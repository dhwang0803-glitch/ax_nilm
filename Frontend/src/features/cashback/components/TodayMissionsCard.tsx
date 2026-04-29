import type { Mission } from "../types";

type Props = { missions: Mission[] };

function StatusPill({ status }: { status: Mission["status"] }) {
  if (status === "done") {
    return (
      <span className="inline-block bg-ink-1 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-canvas">
        완료
      </span>
    );
  }
  return (
    <span className="inline-block bg-fill-2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ink-2">
      대기
    </span>
  );
}

export function TodayMissionsCard({ missions }: Props) {
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <h4 className="text-sm font-semibold text-ink-1">오늘의 미션</h4>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="border-b border-line-3 text-left">
            <th className="py-1.5 font-medium text-ink-3">미션</th>
            <th className="py-1.5 text-right font-medium text-ink-3">예상 절감</th>
            <th className="py-1.5 text-right font-medium text-ink-3">상태</th>
          </tr>
        </thead>
        <tbody>
          {missions.map((m) => (
            <tr key={m.id} className="border-b border-line-3 last:border-b-0">
              <td className="py-2 text-ink-1">{m.title}</td>
              <td className="py-2 text-right font-mono tabular-nums text-ink-1">
                {m.expectedSavingsKwh.toFixed(1)} kWh
              </td>
              <td className="py-2 text-right">
                <StatusPill status={m.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
