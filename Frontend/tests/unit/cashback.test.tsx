import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CashbackPage } from "../../src/features/cashback/CashbackPage";
import { server } from "./setup";

function renderCashback() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CashbackPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CashbackPage", () => {
  it("renders goal + charts + missions on success", async () => {
    renderCashback();
    await waitFor(() =>
      expect(screen.getByText(/저녁 19–21시 건조기 미사용/)).toBeInTheDocument()
    );
    expect(screen.getByRole("heading", { name: /11월 목표/ })).toBeInTheDocument();
    expect(screen.getByText("D-15")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "주간 전력 소모량" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "월별 전력 소모량" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "오늘의 미션" })).toBeInTheDocument();
  });

  it("progressbar has correct aria attributes", async () => {
    renderCashback();
    await waitFor(() => expect(screen.getByRole("progressbar")).toBeInTheDocument());
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "8.4");
    expect(bar).toHaveAttribute("aria-valuemax", "10");
  });

  it("missions table has 3 rows (1 done + 2 pending)", async () => {
    renderCashback();
    await waitFor(() =>
      expect(screen.getByText(/저녁 19–21시 건조기 미사용/)).toBeInTheDocument()
    );
    expect(screen.getByText(/대기전력 멀티탭 OFF/)).toBeInTheDocument();
    expect(screen.getByText(/에어컨 26→27℃/)).toBeInTheDocument();
    expect(screen.getByText("완료")).toBeInTheDocument();
    // "대기" 는 2개
    expect(screen.getAllByText("대기")).toHaveLength(2);
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/cashback/tracker",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    renderCashback();
    await waitFor(() =>
      expect(screen.getByText("데이터를 불러올 수 없습니다.")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "재시도" })).toBeInTheDocument();
  });
});
