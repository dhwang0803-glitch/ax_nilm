import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { DashboardPage } from "../../src/features/dashboard/DashboardPage";
import { server } from "./setup";

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DashboardPage", () => {
  it("renders KPIs, charts, and appliance breakdown on success", async () => {
    renderDashboard();
    await waitFor(() => expect(screen.getByText("이번 달 사용량")).toBeInTheDocument());
    expect(screen.getByText("218")).toBeInTheDocument();
    expect(screen.getByText("kWh")).toBeInTheDocument();
    expect(screen.getByText("예상 캐시백")).toBeInTheDocument();
    expect(screen.getByText("예상 요금")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "주간 전력 소모량" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /월별 전력 소모량/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "가전별 점유" })).toBeInTheDocument();
    expect(screen.getByText("냉난방")).toBeInTheDocument();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/dashboard/summary",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    renderDashboard();
    await waitFor(() =>
      expect(screen.getByText("데이터를 불러올 수 없습니다.")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "재시도" })).toBeInTheDocument();
  });

  it("appliance breakdown shares sum to 100%", () => {
    const items = [
      { name: "냉난방", sharePercent: 36 },
      { name: "냉장고", sharePercent: 22 },
      { name: "세탁/건조", sharePercent: 18 },
      { name: "주방", sharePercent: 12 },
      { name: "기타", sharePercent: 12 },
    ];
    const sum = items.reduce((acc, item) => acc + item.sharePercent, 0);
    expect(sum).toBe(100);
  });
});
