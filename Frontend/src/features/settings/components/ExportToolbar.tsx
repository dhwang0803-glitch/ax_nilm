const FORMATS: Array<{ key: string; label: string }> = [
  { key: "csv", label: "CSV" },
  { key: "json", label: "JSON" },
  { key: "pdf", label: "PDF" },
];

export function ExportToolbar() {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-ink-3">내보내기</span>
      {FORMATS.map((f) => (
        <button
          key={f.key}
          type="button"
          onClick={() => alert(`${f.label} 내보내기는 준비 중입니다`)}
          className="border border-line-2 bg-canvas px-3 py-1 text-xs text-ink-2"
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
