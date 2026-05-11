import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { logout as apiLogout } from "../features/auth/api";
import { useAuth } from "../features/auth/useAuth";

export function Topbar() {
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const logoutLocal = useAuth((s) => s.logout);
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    setMenuOpen(false);
    try {
      await apiLogout();
    } catch {
      // 서버 로그아웃 실패해도 클라이언트 세션은 비움
    }
    logoutLocal();
    navigate("/auth/login", { replace: true });
  }

  const initial = user?.name?.[0] ?? "?";

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
        <details
          className="relative"
          open={menuOpen}
          onToggle={(e) => setMenuOpen(e.currentTarget.open)}
        >
          <summary
            className="flex h-7 w-7 cursor-pointer list-none items-center justify-center bg-ink-1 text-xs font-semibold text-canvas marker:hidden"
            aria-label="계정 메뉴"
          >
            {initial}
          </summary>
          <div className="absolute right-0 top-9 z-10 w-44 border border-line-2 bg-canvas py-1 shadow-sm">
            {user && (
              <div className="border-b border-line-3 px-3 py-2 text-xs text-ink-3">
                {user.name}
              </div>
            )}
            <button
              type="button"
              onClick={handleLogout}
              className="w-full px-3 py-2 text-left text-sm text-ink-1 hover:bg-fill-1"
            >
              로그아웃
            </button>
          </div>
        </details>
      </div>
    </header>
  );
}
