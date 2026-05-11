type Props = {
  title: string;
};

export function BrandPanel({ title }: Props) {
  return (
    <div className="flex flex-col justify-between bg-ink-1 px-12 py-16 text-canvas">
      <div className="text-sm font-semibold">에너지캐시백</div>
      <h2 className="text-3xl font-bold leading-tight">{title}</h2>
      <div className="font-mono text-[10px] uppercase tracking-wider text-ink-4">
        © 2026 ax_nilm · KEPCO 협력
      </div>
    </div>
  );
}
