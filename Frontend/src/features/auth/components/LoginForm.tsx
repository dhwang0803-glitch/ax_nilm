import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { login, oauthLogin } from "../api";
import { loginSchema, type LoginFormData } from "../schemas";
import { useAuth } from "../useAuth";
import { Field } from "./Field";
import { OAuthButtons, type OAuthProvider } from "./OAuthButtons";

export function LoginForm() {
  const setUser = useAuth((s) => s.setUser);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [oauthLoading, setOauthLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  async function onSubmit(data: LoginFormData) {
    setSubmitError(null);
    try {
      const { user } = await login({ email: data.email, password: data.password });
      setUser(user);
      // LoginPage 가 user 변경을 감지해서 ?from 또는 /home 으로 redirect
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 401) {
        setSubmitError("이메일 또는 비밀번호가 일치하지 않습니다");
      } else {
        setSubmitError("로그인 중 오류가 발생했습니다");
      }
    }
  }

  async function handleOAuth(provider: OAuthProvider) {
    setOauthLoading(true);
    setSubmitError(null);
    try {
      const { user } = await oauthLogin(provider);
      setUser(user);
    } catch {
      setSubmitError("소셜 로그인 중 오류가 발생했습니다");
    } finally {
      setOauthLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold text-ink-1">로그인</h1>
        <p className="mt-1 text-sm text-ink-3">계정 정보로 로그인하세요</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3" noValidate>
        <Field
          label="이메일"
          type="email"
          autoComplete="email"
          placeholder="name@example.com"
          {...register("email")}
          error={errors.email?.message}
        />
        <Field
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          placeholder="••••••••"
          {...register("password")}
          error={errors.password?.message}
        />

        <div className="flex items-center justify-between text-xs">
          <label className="flex items-center gap-1.5 text-ink-2">
            <input type="checkbox" {...register("rememberMe")} className="accent-ink-1" />
            자동 로그인
          </label>
          <button
            type="button"
            onClick={() => alert("준비 중입니다")}
            className="text-ink-3 hover:text-ink-1"
          >
            비밀번호 찾기
          </button>
        </div>

        {submitError && <div className="text-xs text-red-600">{submitError}</div>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center border border-ink-1 bg-ink-1 px-4 py-2.5 text-sm font-medium text-canvas disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "로그인 중…" : "로그인"}
        </button>
      </form>

      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-line-3" />
        <span className="text-[11px] text-ink-3">또는</span>
        <div className="h-px flex-1 bg-line-3" />
      </div>

      <OAuthButtons onSelect={handleOAuth} disabled={oauthLoading} />

      <div className="text-center text-xs text-ink-3">
        처음이신가요?{" "}
        <Link to="/auth/signup" className="font-semibold text-ink-1">
          회원가입 →
        </Link>
      </div>
    </div>
  );
}
