import { Navigate, useSearchParams } from "react-router-dom";
import { AuthLayout } from "./components/AuthLayout";
import { LoginForm } from "./components/LoginForm";
import { useAuth } from "./useAuth";

export function LoginPage() {
  const user = useAuth((s) => s.user);
  const [searchParams] = useSearchParams();
  const from = searchParams.get("from") ?? "/home";
  if (user) {
    return <Navigate to={from} replace />;
  }
  return (
    <AuthLayout brandTitle="우리집 전기, 데이터로 똑똑하게 절약하세요.">
      <LoginForm />
    </AuthLayout>
  );
}
