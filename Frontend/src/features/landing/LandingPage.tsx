import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export function LandingPage() {
  const user = useAuth((s) => s.user);
  if (user) {
    return <Navigate to="/home" replace />;
  }
  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-line-2 bg-canvas px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="bg-ink-1 px-2 py-1 font-mono text-xs text-canvas">ax</span>
            <span className="text-sm font-semibold">에너지캐시백</span>
          </div>
          <Link
            to="/auth/login"
            className="border border-ink-1 bg-ink-1 px-4 py-2 text-sm text-canvas"
          >
            로그인
          </Link>
        </div>
      </header>
      <main className="px-8 py-12">
        <h2 className="text-4xl font-bold">전기요금, 줄인 만큼 돌려받으세요</h2>
        <p className="mt-4 text-ink-2">Phase 01 에서 본 구현 — 미니멀 히어로 변형 B</p>
      </main>
    </div>
  );
}
