import type { AnomalyHighlight, InsightSeverity } from "../types";

type Props = {
  highlights: AnomalyHighlight[];
};

const SEVERITY_LABEL: Record<InsightSeverity, string> = {
  low: "낮음",
  medium: "중간",
  high: "높음",
};

const SEVERITY_PILL: Record<InsightSeverity, string> = {
  low: "bg-fill-2 text-ink-2",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-red-100 text-red-700",
};

export function AnomalyHighlightCard({ highlights }: Props) {
  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="insights-highlight-heading"
    >
      <h3
        id="insights-highlight-heading"
        className="text-base font-semibold text-ink-1"
      >
        최근 이상 사용
      </h3>
      {highlights.length === 0 ? (
        <p className="mt-4 text-sm text-ink-3">
          최근 7일 내 이상 사용이 감지되지 않았습니다.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-3">
          {highlights.map((hl) => (
            <li
              key={hl.id}
              className="border border-line-2 bg-fill-1 p-4"
            >
              <div className="flex items-baseline justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-ink-1">
                    {hl.appliance}
                  </span>
                  <span
                    className={`px-2 py-0.5 text-xs ${SEVERITY_PILL[hl.severity]}`}
                  >
                    {SEVERITY_LABEL[hl.severity]}
                  </span>
                </div>
                <span className="font-mono text-xs text-ink-3">
                  {hl.detectedAt}
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-1">{hl.headline}</p>
              <p className="mt-1 text-sm text-ink-2">{hl.recommendation}</p>
              <button
                type="button"
                onClick={() => alert("준비 중입니다")}
                className="mt-3 bg-fill-2 px-3 py-1 text-xs text-ink-2"
              >
                자세히
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
