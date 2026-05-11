import type { SecuritySession } from "../types";

type Props = { sessions: SecuritySession[] };

export function SessionsCard({ sessions }: Props) {
  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="sessions-heading"
    >
      <header>
        <h3 id="sessions-heading" className="text-base font-semibold text-ink-1">
          활성 세션
        </h3>
        <p className="mt-1 text-sm text-ink-3">
          로그인된 디바이스 목록입니다. 낯선 세션은 즉시 로그아웃하세요.
        </p>
      </header>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="border-b border-line-2 text-left text-ink-3">
            <th scope="col" className="py-2 font-normal">
              디바이스
            </th>
            <th scope="col" className="py-2 font-normal">
              위치
            </th>
            <th scope="col" className="py-2 font-normal">
              마지막 활동
            </th>
            <th scope="col" className="py-2 text-right font-normal">
              조치
            </th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.id} className="border-b border-line-2/60">
              <td className="py-3 text-ink-1">
                {s.device}
                {s.current && (
                  <span className="ml-2 bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">
                    현재
                  </span>
                )}
              </td>
              <td className="py-3 text-ink-2">{s.location}</td>
              <td className="py-3 text-ink-2">{s.lastActiveAt}</td>
              <td className="py-3 text-right">
                <button
                  type="button"
                  disabled={s.current}
                  onClick={() => alert("준비 중입니다")}
                  className="bg-fill-2 px-3 py-1 text-xs text-ink-2 disabled:opacity-40"
                >
                  로그아웃
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
