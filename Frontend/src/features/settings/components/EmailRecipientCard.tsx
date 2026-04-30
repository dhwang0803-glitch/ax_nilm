import { useState } from "react";

type Props = { primaryEmail: string; initialAlternate: string | null };

export function EmailRecipientCard({ primaryEmail, initialAlternate }: Props) {
  const [useAlternate, setUseAlternate] = useState(initialAlternate !== null);
  const [alternate, setAlternate] = useState(initialAlternate ?? "");

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="email-recipient-heading"
    >
      <header>
        <h3
          id="email-recipient-heading"
          className="text-base font-semibold text-ink-1"
        >
          수신 이메일
        </h3>
        <p className="mt-1 text-sm text-ink-3">
          이상 탐지·캐시백 알림을 받을 이메일 주소입니다.
        </p>
      </header>

      <dl className="mt-4 grid grid-cols-[140px_1fr] items-center gap-y-3 text-sm">
        <dt className="text-ink-3">가입 이메일</dt>
        <dd className="text-ink-1">{primaryEmail}</dd>
      </dl>

      <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-sm text-ink-2">
        <input
          type="checkbox"
          checked={useAlternate}
          onChange={(e) => setUseAlternate(e.target.checked)}
          className="h-4 w-4"
        />
        다른 주소 사용
      </label>

      {useAlternate && (
        <div className="mt-3 grid grid-cols-[140px_1fr] items-center gap-3 text-sm">
          <label htmlFor="alt-email" className="text-ink-3">
            대체 주소
          </label>
          <input
            id="alt-email"
            type="email"
            placeholder="예: alerts@mydomain.com"
            value={alternate}
            onChange={(e) => setAlternate(e.target.value)}
            className="border border-line-2 bg-canvas px-2 py-1.5 text-sm"
          />
        </div>
      )}
    </section>
  );
}
