import { HttpResponse, delay, http } from "msw";
import { mockCashbackTracker } from "./cashbackData";
import { mockDashboardSummary } from "./dashboardData";
import {
  mockAccount,
  mockAnomalyEvents,
  mockNotifications,
  mockSecurity,
} from "./settingsData";
import { mockUsageAnalysis } from "./usageData";

const VALID_EMAIL = "test@example.com";
const VALID_PASSWORD = "nilm-mock-2026!";
const TAKEN_EMAIL = "taken@test.com";

type LoginBody = { email: string; password: string };
type SignupBody = {
  email: string;
  password: string;
  name: string;
  agreeTerms: boolean;
  kepcoCustomerNumber: string | null;
};

export const handlers = [
  http.post("/auth/login", async ({ request }) => {
    const body = (await request.json()) as LoginBody;
    if (body.email === VALID_EMAIL && body.password === VALID_PASSWORD) {
      return HttpResponse.json({
        user: { id: "u1", email: VALID_EMAIL, name: "테스터" },
      });
    }
    return HttpResponse.json(
      { code: "INVALID_CREDENTIALS", message: "이메일 또는 비밀번호가 일치하지 않습니다" },
      { status: 401 }
    );
  }),

  http.post("/auth/signup", async ({ request }) => {
    const body = (await request.json()) as SignupBody;
    if (body.email === TAKEN_EMAIL) {
      return HttpResponse.json(
        { code: "EMAIL_TAKEN", message: "이미 가입된 이메일입니다" },
        { status: 422 }
      );
    }
    return HttpResponse.json({
      user: { id: "u-new", email: body.email, name: body.name },
    });
  }),

  http.get("/auth/me", () => {
    // dev 단계는 zustand store 가 세션 권위 — /auth/me 는 prod 전환 시 활용. 기본 401.
    return new HttpResponse(null, { status: 401 });
  }),

  http.post("/auth/logout", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("/auth/oauth/:provider", ({ params }) => {
    const provider = params.provider as string;
    if (!["kakao", "naver", "google"].includes(provider)) {
      return HttpResponse.json({ code: "UNKNOWN_PROVIDER" }, { status: 400 });
    }
    return HttpResponse.json({
      user: {
        id: `u-${provider}`,
        email: `${provider}@example.com`,
        name: `${provider} 사용자`,
      },
    });
  }),

  http.get("/api/dashboard/summary", async () => {
    // 300ms delay — dev 시연 시 skeleton UI 자연스럽게 노출. 실 백엔드 응답 시간 시뮬.
    await delay(300);
    return HttpResponse.json(mockDashboardSummary);
  }),

  http.get("/api/usage/analysis", async () => {
    await delay(300);
    return HttpResponse.json(mockUsageAnalysis);
  }),

  http.get("/api/cashback/tracker", async () => {
    await delay(300);
    return HttpResponse.json(mockCashbackTracker);
  }),

  http.get("/api/settings/account", async () => {
    await delay(300);
    return HttpResponse.json(mockAccount);
  }),

  http.get("/api/settings/notifications", async () => {
    await delay(300);
    return HttpResponse.json(mockNotifications);
  }),

  http.get("/api/settings/security", async () => {
    await delay(300);
    return HttpResponse.json(mockSecurity);
  }),

  http.get("/api/settings/anomaly-events", async () => {
    await delay(300);
    return HttpResponse.json(mockAnomalyEvents);
  }),
];
