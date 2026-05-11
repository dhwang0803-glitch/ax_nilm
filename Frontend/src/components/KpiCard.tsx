type Props = {
  title: string;
  value: string | number;
  unit?: string;
  delta?: string;
  deltaDir?: "up" | "down" | "neutral";
  foot?: string;
};

export function KpiCard({ title, value, unit, delta, foot }: Props) {
  return (
    <div className="border border-line-2 bg-canvas p-4">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-3">{title}</span>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="font-mono text-3xl font-semibold tabular-nums text-ink-1">{value}</span>
        {unit && <span className="text-sm text-ink-3">{unit}</span>}
      </div>
      {(delta || foot) && (
        <div className="mt-2 flex items-center justify-between gap-2 text-xs">
          {delta ? <span className="text-ink-2">{delta}</span> : <span />}
          {foot ? <span className="text-ink-3">{foot}</span> : null}
        </div>
      )}
    </div>
  );
}
