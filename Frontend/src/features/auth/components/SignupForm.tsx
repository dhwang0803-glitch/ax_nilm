import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { oauthLogin, signup } from "../api";
import { signupSchema, type SignupFormData } from "../schemas";
import { useAuth } from "../useAuth";
import { Field } from "./Field";
import { OAuthButtons, type OAuthProvider } from "./OAuthButtons";

export function SignupForm() {
  const setUser = useAuth((s) => s.setUser);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [oauthLoading, setOauthLoading] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormData>({
    resolver: zodResolver(signupSchema),
  });

  const skipKepco = watch("skipKepco");

  async function onSubmit(data: SignupFormData) {
    setSubmitError(null);
    try {
      const { user } = await signup({
        email: data.email,
        password: data.password,
        name: data.name,
        agreeTerms: data.agreeTerms,
        kepcoCustomerNumber: data.skipKepco ? null : (data.kepcoCustomerNumber ?? null),
      });
      setUser(user);
      // SignupPage 가 user 변경 감지해서 /home 으로 redirect
    } catch (err) {
      if (isAxiosError(err) && err.response?.status === 422) {
        setSubmitError("이미 가입된 이메일입니다");
      } else {
        setSubmitError("회원가입 중 오류가 발생했습니다");
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
        <h1 className="text-2xl font-semibold text-ink-1">회원가입</h1>
        <p className="mt-1 text-sm text-ink-3">3분이면 시작할 수 있어요</p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-3" noValidate>
        <Field
          label="이메일"
          type="email"
          autoComplete="email"
          {...register("email")}
          error={errors.email?.message}
        />
        <Field
          label="비밀번호"
          type="password"
          autoComplete="new-password"
          {...register("password")}
          error={errors.password?.message}
        />
        <Field
          label="비밀번호 확인"
          type="password"
          autoComplete="new-password"
          {...register("passwordConfirm")}
          error={errors.passwordConfirm?.message}
        />
        <Field
          label="이름"
          type="text"
          autoComplete="name"
          {...register("name")}
          error={errors.name?.message}
        />

        <div className="flex flex-col gap-2 border-t border-line-3 pt-3">
          <Field
            label="한전 고객번호 (선택)"
            type="text"
            inputMode="numeric"
            placeholder="10자리 숫자"
            disabled={skipKepco}
            {...register("kepcoCustomerNumber")}
            error={errors.kepcoCustomerNumber?.message}
          />
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            <input type="checkbox" {...register("skipKepco")} className="accent-ink-1" />
            나중에 하기
          </label>
          {skipKepco && (
            <p className="text-xs text-ink-3">
              설정 &gt; 계정 &gt; 한전 연동에서 추후 입력 가능합니다
            </p>
          )}
        </div>

        <label className="flex items-start gap-2 text-xs text-ink-2">
          <input
            type="checkbox"
            {...register("agreeTerms")}
            className="mt-0.5 accent-ink-1"
          />
          <span>
            서비스 이용약관 및 개인정보 수집·이용에 동의합니다
            {errors.agreeTerms && (
              <span className="ml-1 text-red-600">{errors.agreeTerms.message}</span>
            )}
          </span>
        </label>

        {submitError && <div className="text-xs text-red-600">{submitError}</div>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center border border-ink-1 bg-ink-1 px-4 py-2.5 text-sm font-medium text-canvas disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "회원가입 중…" : "회원가입"}
        </button>
      </form>

      <div className="flex items-center gap-2">
        <div className="h-px flex-1 bg-line-3" />
        <span className="text-[11px] text-ink-3">또는</span>
        <div className="h-px flex-1 bg-line-3" />
      </div>

      <OAuthButtons onSelect={handleOAuth} disabled={oauthLoading} />

      <div className="text-center text-xs text-ink-3">
        이미 계정이 있으신가요?{" "}
        <Link to="/auth/login" className="font-semibold text-ink-1">
          로그인 →
        </Link>
      </div>
    </div>
  );
}
