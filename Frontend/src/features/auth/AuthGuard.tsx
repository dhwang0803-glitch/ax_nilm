import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";

export function AuthGuard() {
  const user = useAuth((s) => s.user);
  const location = useLocation();
  if (!user) {
    const from = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/auth/login?from=${from}`} replace />;
  }
  return <Outlet />;
}
