export function DangerZoneCard() {
  return (
    <section
      className="border border-red-400 bg-canvas p-6"
      aria-labelledby="danger-zone-heading"
    >
      <header>
        <h3
          id="danger-zone-heading"
          className="text-base font-semibold text-red-600"
        >
          위험 영역
        </h3>
        <p className="mt-2 text-sm text-ink-2">
          계정을 삭제하면 사용량/캐시백/이상 탐지 기록이 모두 영구적으로 제거되며 복구할 수 없습니다.
        </p>
      </header>
      <button
        type="button"
        onClick={() => alert("계정 삭제는 준비 중입니다")}
        className="mt-4 border border-red-500 bg-canvas px-3 py-1.5 text-xs text-red-600"
      >
        계정 삭제
      </button>
    </section>
  );
}
