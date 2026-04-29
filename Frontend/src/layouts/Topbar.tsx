export function Topbar() {
  return (
    <header className="flex items-center justify-between border-b border-line-2 bg-canvas px-6 py-3">
      <div className="text-sm text-ink-2">메인</div>
      <div className="flex items-center gap-3">
        <input
          type="search"
          placeholder="검색…"
          className="w-[240px] border border-line-2 bg-bg px-3 py-1.5 text-sm placeholder:text-ink-4"
        />
        <span className="h-7 w-7 border border-line-2 bg-fill-1" aria-label="알림" />
        <span className="flex h-7 w-7 items-center justify-center bg-ink-1 text-xs font-semibold text-canvas">
          김
        </span>
      </div>
    </header>
  );
}
