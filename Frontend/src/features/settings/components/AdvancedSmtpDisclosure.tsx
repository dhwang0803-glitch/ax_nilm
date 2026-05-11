export function AdvancedSmtpDisclosure() {
  return (
    <details className="border border-line-2 bg-canvas p-4 text-sm">
      <summary className="cursor-pointer text-ink-2">
        고급 — SMTP / POP 직접 설정
      </summary>
      <p className="mt-2 text-xs text-ink-3">
        기업 사용자는 별도 SMTP 서버를 통한 발송 설정이 가능합니다 — 추후 지원 예정.
      </p>
    </details>
  );
}
