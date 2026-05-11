import { NavLink, Outlet } from "react-router-dom";

const tabs = [
  { to: "/settings/account", label: "프로필 / 한전 연동" },
  { to: "/settings/notifications", label: "알림" },
  { to: "/settings/security", label: "보안" },
  { to: "/settings/anomaly-log", label: "이상 탐지 내역" },
  { to: "/settings/email", label: "이메일 연동" },
];

export function SettingsLayout() {
  return (
    <div className="flex gap-6">
      <nav className="w-[200px] flex-shrink-0">
        <h2 className="px-2 py-2 text-2xl font-semibold">설정</h2>
        <ul className="mt-2 flex flex-col gap-1">
          {tabs.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                end
                className={({ isActive }) =>
                  `block border-l-2 px-3 py-2 text-sm ${
                    isActive
                      ? "border-ink-1 bg-fill-1 font-semibold"
                      : "border-transparent text-ink-2"
                  }`
                }
              >
                {t.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex-1">
        <Outlet />
      </div>
    </div>
  );
}
