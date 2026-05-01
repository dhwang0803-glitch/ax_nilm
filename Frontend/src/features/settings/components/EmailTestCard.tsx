import { useState } from "react";

type Props = { lastTestAt: string | null };

export function EmailTestCard({ lastTestAt }: Props) {
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleSend = () => {
    setResult(null);
    setSending(true);
    setTimeout(() => {
      setResult("테스트 메일을 발송했습니다. 받은편지함을 확인해주세요. (mock)");
      setSending(false);
    }, 200);
  };

  return (
    <section
      className="border border-line-2 bg-canvas p-6"
      aria-labelledby="email-test-heading"
    >
      <header className="flex items-center justify-between">
        <h3
          id="email-test-heading"
          className="text-base font-semibold text-ink-1"
        >
          테스트 메일 발송
        </h3>
        {lastTestAt && (
          <span className="text-xs text-ink-3">
            마지막 발송: {lastTestAt}
          </span>
        )}
      </header>
      <p className="mt-2 text-sm text-ink-3">
        설정된 수신 주소가 정상 작동하는지 확인합니다.
      </p>
      <div className="mt-4">
        <button
          type="button"
          onClick={handleSend}
          disabled={sending}
          className="border border-ink-1 bg-ink-1 px-3 py-1.5 text-xs text-canvas disabled:opacity-50"
        >
          {sending ? "발송 중…" : "테스트 메일 발송"}
        </button>
      </div>
      {result && (
        <p role="status" className="mt-3 text-xs text-emerald-600">
          {result}
        </p>
      )}
    </section>
  );
}
