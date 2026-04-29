import { Navigate } from "react-router-dom";
import { AuthLayout } from "./components/AuthLayout";
import { SignupForm } from "./components/SignupForm";
import { useAuth } from "./useAuth";

export function SignupPage() {
  const user = useAuth((s) => s.user);
  if (user) {
    return <Navigate to="/home" replace />;
  }
  return (
    <AuthLayout brandTitle="지금 시작하면, 다음 달부터 캐시백.">
      <SignupForm />
    </AuthLayout>
  );
}
