import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { InsightsPage } from "../../src/features/insights/InsightsPage";
import { server } from "./setup";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <InsightsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("InsightsPage", () => {
  it("renders header with last analysis time and model version", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "AI 진단", level: 2 })
      ).toBeInTheDocument()
    );
    expect(screen.getByText(/마지막 분석: 2026-04-30 09:12/)).toBeInTheDocument();
    expect(screen.getByText(/모델 v2\.4/)).toBeInTheDocument();
  });

  it("renders 3 KPI cards (week count, monthly saving, confidence)", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("이번 주 진단")).toBeInTheDocument()
    );
    expect(screen.getByText("이번 달 예상 절약")).toBeInTheDocument();
    expect(screen.getByText("모델 신뢰도")).toBeInTheDocument();

    // 12건, 9,840원, 92% 표기
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("9,840")).toBeInTheDocument();
    expect(screen.getByText("92")).toBeInTheDocument();
    expect(screen.getByText(/표본 79세대/)).toBeInTheDocument();
  });

  it("renders anomaly highlights with severity pills", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "최근 이상 사용" })
      ).toBeInTheDocument()
    );
    expect(screen.getByText("정상 대비 25% 과소비")).toBeInTheDocument();
    expect(screen.getByText("평소 대비 12% 추가 소비")).toBeInTheDocument();
    // severity 라벨 (highlight 카드 + 표는 분리 — getAllByText 안전)
    expect(screen.getAllByText("높음").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("중간").length).toBeGreaterThanOrEqual(1);
  });

  it("renders recommendations table with 6 rows + confidence progressbars", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "추천 조치 (6건)" })
      ).toBeInTheDocument()
    );
    expect(
      screen.getByText("필터 청소 · 설정 온도 +1℃")
    ).toBeInTheDocument();
    const bars = screen.getAllByRole("progressbar");
    expect(bars).toHaveLength(6);
    expect(bars[0]).toHaveAttribute("aria-valuenow", "91");
  });

  it("renders weekly trend chart heading + svg", async () => {
    const { container } = renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "주간 진단 추이" })
      ).toBeInTheDocument()
    );
    // Recharts ResponsiveContainer 가 svg 를 그렸는지만 확인
    expect(container.querySelector(".recharts-responsive-container")).not.toBeNull();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/insights/summary",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText("데이터를 불러올 수 없습니다.")
      ).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "재시도" })).toBeInTheDocument();
  });

  it("shows empty state when highlights / recommendations are empty", async () => {
    server.use(
      http.get("/api/insights/summary", () =>
        HttpResponse.json({
          generatedAt: "2026-04-30 09:12",
          modelVersion: "v2.4",
          sampleHouseholds: 79,
          kpi: {
            weeklyDiagnosisCount: 0,
            weeklyDiagnosisDelta: 0,
            monthlyEstimatedSavingKrw: 0,
            monthlySavingDelta: 0,
            modelConfidence: 0.5,
          },
          anomalyHighlights: [],
          recommendations: [],
          weeklyTrend: [],
        })
      )
    );
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/최근 7일 내 이상 사용이 감지되지 않았습니다/)
      ).toBeInTheDocument()
    );
    expect(
      screen.getByText(/현재 권고할 조치가 없습니다/)
    ).toBeInTheDocument();
    expect(screen.getByText("표시할 데이터가 없습니다.")).toBeInTheDocument();
  });
});
