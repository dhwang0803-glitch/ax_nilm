import { NavLink } from "react-router-dom";

const mainNav = [
  { to: "/home", label: "대시보드" },
  { to: "/usage", label: "사용량 분석" },
  { to: "/cashback", label: "캐시백" },
  { to: "/insights", label: "AI 진단" },
];

const accountNav = [{ to: "/settings/account", label: "설정" }];

const navClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 border-l-2 px-3 py-2 text-sm ${
    isActive ? "border-ink-1 bg-fill-1 font-semibold" : "border-transparent text-ink-2"
  }`;

export function Sidebar() {
  return (
    <aside className="w-[220px] flex-shrink-0 border-r border-line-2 bg-canvas">
      <div className="border-b border-line-3 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="bg-ink-1 px-2 py-1 font-mono text-xs text-canvas">ax</span>
          <span className="text-sm font-semibold">에너지캐시백</span>
        </div>
      </div>
      <nav className="p-2">
        <div className="px-2 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-3">
          메인
        </div>
        {mainNav.map((item) => (
          <NavLink key={item.to} to={item.to} className={navClass}>
            {item.label}
          </NavLink>
        ))}
        <div className="mt-2 px-2 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-3">
          계정
        </div>
        {accountNav.map((item) => (
          <NavLink key={item.to} to={item.to} className={navClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
