const segments = ["일", "주", "월", "연"] as const;

export function UsageToolbar() {
  function handlePlaceholder(label: string) {
    alert(`${label} 기능은 준비 중입니다.`);
  }

  return (
    <div className="flex items-center gap-2">
      <div className="flex border border-line-2 text-[11px]">
        {segments.map((label, idx) => (
          <button
            key={label}
            type="button"
            onClick={() => (idx === 1 ? undefined : handlePlaceholder(`${label} 단위`))}
            className={`px-2.5 py-1 ${idx === 1 ? "bg-ink-1 text-canvas" : "text-ink-3 hover:bg-fill-1"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => handlePlaceholder("기간 선택")}
        className="border border-line-2 bg-canvas px-3 py-1 text-xs text-ink-1"
      >
        기간 선택
      </button>
      <button
        type="button"
        onClick={() => handlePlaceholder("CSV 내보내기")}
        className="border border-ink-1 bg-ink-1 px-3 py-1 text-xs text-canvas"
      >
        CSV 내보내기
      </button>
    </div>
  );
}
