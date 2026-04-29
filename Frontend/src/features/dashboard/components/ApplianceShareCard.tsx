import type { ApplianceBreakdownItem } from "../types";

type Props = { items: ApplianceBreakdownItem[] };

export function ApplianceShareCard({ items }: Props) {
  return (
    <section className="border border-line-2 bg-canvas p-4">
      <h4 className="text-sm font-semibold text-ink-1">가전별 점유</h4>
      <ul className="mt-3 flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.name}>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-ink-2">{item.name}</span>
              <span className="font-mono tabular-nums text-ink-2">{item.sharePercent}%</span>
            </div>
            <div className="mt-1 h-1.5 bg-fill-2">
              <div
                className="h-full bg-ink-2"
                style={{ width: `${item.sharePercent}%` }}
                role="progressbar"
                aria-valuenow={item.sharePercent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${item.name} ${item.sharePercent}%`}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
