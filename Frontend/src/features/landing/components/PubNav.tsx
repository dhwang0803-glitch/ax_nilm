import { Link } from "react-router-dom";

export function PubNav() {
  return (
    <header className="border-b border-line-2 bg-canvas">
      <div className="mx-auto flex max-w-[1280px] items-center justify-between px-10 py-3.5">
        <span className="text-sm font-semibold text-ink-1">에너지캐시백</span>
        <nav className="flex items-center gap-6 text-sm text-ink-2">
          <a href="#features" className="hover:text-ink-1">
            특징
          </a>
          <a href="#faq" className="hover:text-ink-1">
            FAQ
          </a>
        </nav>
        <Link
          to="/auth/login"
          className="inline-flex items-center border border-ink-1 bg-ink-1 px-3 py-1.5 text-xs font-medium text-canvas"
        >
          시작하기
        </Link>
      </div>
    </header>
  );
}
