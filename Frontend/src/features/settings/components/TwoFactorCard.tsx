import { useState } from "react";

type Props = { initialEnabled: boolean };

export function TwoFactorCard({ initialEnabled }: Props) {
  const [enabled, setEnabled] = useState(initialEnabled);

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="two-factor-heading"
    >
      <header className="flex items-center justify-between">
        <h3
          id="two-factor-heading"
          className="text-base font-semibold text-ink-1"
        >
          2단계 인증
        </h3>
        <span
          className={`px-2 py-0.5 text-xs ${
            enabled ? "bg-emerald-100 text-emerald-700" : "bg-fill-2 text-ink-3"
          }`}
          aria-label={`2단계 인증 상태: ${enabled ? "활성" : "미설정"}`}
        >
          {enabled ? "활성" : "미설정"}
        </span>
      </header>
      <p className="mt-2 text-sm text-ink-3">
        OTP 앱(Google Authenticator 등)으로 로그인 시 6자리 코드를 추가 입력합니다.
      </p>
      <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-sm text-ink-2">
        <input
          type="checkbox"
          role="switch"
          aria-label="2단계 인증 사용"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="h-4 w-4"
        />
        {enabled ? "사용 중" : "사용 안 함"}
      </label>
    </section>
  );
}
