import type { AnomalySeverity, AnomalyStatus } from "../types";

export type AnomalyPeriod = "month" | "30d" | "90d";

export type AnomalyFilterState = {
  period: AnomalyPeriod;
  severities: AnomalySeverity[];
  statuses: AnomalyStatus[];
  appliance: string | null;
};

type Props = {
  state: AnomalyFilterState;
  onChange: (next: AnomalyFilterState) => void;
  appliances: string[];
};

const SEVERITY_LABEL: Record<AnomalySeverity, string> = {
  low: "낮음",
  medium: "중간",
  high: "높음",
};

const STATUS_LABEL: Record<AnomalyStatus, string> = {
  open: "미해결",
  resolved: "해결",
};

const PERIOD_OPTIONS: Array<{ value: AnomalyPeriod; label: string }> = [
  { value: "month", label: "이번 달" },
  { value: "30d", label: "지난 30일" },
  { value: "90d", label: "지난 90일" },
];

function pillClass(active: boolean) {
  return `px-3 py-1 text-xs ${
    active ? "bg-ink-1 text-canvas" : "bg-fill-2 text-ink-2"
  }`;
}

export function FilterPillsCard({ state, onChange, appliances }: Props) {
  const toggleSeverity = (s: AnomalySeverity) => {
    const next = state.severities.includes(s)
      ? state.severities.filter((v) => v !== s)
      : [...state.severities, s];
    onChange({ ...state, severities: next });
  };

  const toggleStatus = (s: AnomalyStatus) => {
    const next = state.statuses.includes(s)
      ? state.statuses.filter((v) => v !== s)
      : [...state.statuses, s];
    onChange({ ...state, statuses: next });
  };

  const toggleAppliance = (a: string) => {
    onChange({ ...state, appliance: state.appliance === a ? null : a });
  };

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="filter-pills-heading"
    >
      <h3
        id="filter-pills-heading"
        className="text-base font-semibold text-ink-1"
      >
        필터
      </h3>

      <div className="mt-4 flex items-center gap-3 text-sm">
        <label htmlFor="filter-period" className="text-ink-3">
          기간
        </label>
        <select
          id="filter-period"
          value={state.period}
          onChange={(e) =>
            onChange({ ...state, period: e.target.value as AnomalyPeriod })
          }
          className="border border-line-2 bg-canvas px-2 py-1 text-sm"
        >
          {PERIOD_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <PillRow label="심각도">
        {(["low", "medium", "high"] as AnomalySeverity[]).map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={state.severities.includes(s)}
            onClick={() => toggleSeverity(s)}
            className={pillClass(state.severities.includes(s))}
          >
            {SEVERITY_LABEL[s]}
          </button>
        ))}
      </PillRow>

      <PillRow label="상태">
        {(["open", "resolved"] as AnomalyStatus[]).map((s) => (
          <button
            key={s}
            type="button"
            aria-pressed={state.statuses.includes(s)}
            onClick={() => toggleStatus(s)}
            className={pillClass(state.statuses.includes(s))}
          >
            {STATUS_LABEL[s]}
          </button>
        ))}
      </PillRow>

      <PillRow label="가전">
        {appliances.map((a) => (
          <button
            key={a}
            type="button"
            aria-pressed={state.appliance === a}
            onClick={() => toggleAppliance(a)}
            className={pillClass(state.appliance === a)}
          >
            {a}
          </button>
        ))}
      </PillRow>
    </section>
  );
}

function PillRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-3 flex items-center gap-2 text-sm">
      <span className="w-12 text-ink-3">{label}</span>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
