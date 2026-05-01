import type { Recommendation } from "../types";

type Props = {
  recommendations: Recommendation[];
};

export function RecommendationsTable({ recommendations }: Props) {
  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="insights-recommendations-heading"
    >
      <h3
        id="insights-recommendations-heading"
        className="text-base font-semibold text-ink-1"
      >
        추천 조치 ({recommendations.length}건)
      </h3>
      {recommendations.length === 0 ? (
        <p className="mt-4 text-sm text-ink-3">
          현재 권고할 조치가 없습니다. 모델이 학습 데이터를 추가 수집 중입니다.
        </p>
      ) : (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-line-2 text-left text-ink-3">
              <th scope="col" className="py-2 font-normal">
                가전
              </th>
              <th scope="col" className="py-2 font-normal">
                권고 조치
              </th>
              <th scope="col" className="py-2 text-right font-normal">
                예상 절약
              </th>
              <th scope="col" className="py-2 font-normal">
                신뢰도
              </th>
            </tr>
          </thead>
          <tbody>
            {recommendations.map((r) => {
              const pct = Math.round(r.confidence * 100);
              return (
                <tr key={r.id} className="border-b border-line-2/60">
                  <td className="py-3 text-ink-1">{r.appliance}</td>
                  <td className="py-3 text-ink-2">{r.action}</td>
                  <td className="py-3 text-right font-mono tabular-nums text-ink-1">
                    {r.estimatedSavingKrw.toLocaleString()}원
                  </td>
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="h-1.5 w-24 bg-fill-2"
                        role="progressbar"
                        aria-label={`${r.appliance} 신뢰도 ${pct}%`}
                        aria-valuenow={pct}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <div
                          className="h-full bg-ink-1"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="font-mono text-xs tabular-nums text-ink-2">
                        {pct}%
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
