import type { ApplianceBreakdownRow } from "../types";

type Props = { rows: ApplianceBreakdownRow[] };

export function ApplianceBreakdownCard({ rows }: Props) {
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <h4 className="text-sm font-semibold text-ink-1">가전별 분해 (이번 주)</h4>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="border-b border-line-3 text-left">
            <th className="py-1.5 font-medium text-ink-3">가전</th>
            <th className="py-1.5 text-right font-medium text-ink-3">kWh</th>
            <th className="py-1.5 text-right font-medium text-ink-3">점유</th>
            <th className="py-1.5 text-right font-medium text-ink-3">전주 대비</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-b border-line-3 last:border-b-0">
              <td className="py-2 text-ink-1">{row.name}</td>
              <td className="py-2 text-right font-mono tabular-nums text-ink-1">
                {row.kwh.toFixed(1)}
              </td>
              <td className="py-2 text-right font-mono tabular-nums text-ink-2">
                {row.sharePercent}%
              </td>
              <td className="py-2 text-right font-mono tabular-nums text-ink-2">
                {row.weekOverWeekPercent > 0 ? "+" : ""}
                {row.weekOverWeekPercent}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
