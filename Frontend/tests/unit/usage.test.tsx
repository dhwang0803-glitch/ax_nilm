import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { UsagePage } from "../../src/features/usage/UsagePage";
import { server } from "./setup";

function renderUsage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <UsagePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("UsagePage", () => {
  it("renders all four sections on success", async () => {
    renderUsage();
    // 가전명 텍스트는 skeleton 에 없으므로 success 분기 진입의 정확한 신호
    await waitFor(() => expect(screen.getByText("에어컨/난방")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "사용량 분석", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /주간 전력 소모량/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /시간대별 평균/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /가전별 분해/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /월별 전력 소모량/ })).toBeInTheDocument();
  });

  it("appliance breakdown table has 5 rows", async () => {
    renderUsage();
    await waitFor(() => expect(screen.getByText("에어컨/난방")).toBeInTheDocument());
    expect(screen.getByText("냉장고")).toBeInTheDocument();
    expect(screen.getByText("세탁/건조")).toBeInTheDocument();
    expect(screen.getByText("주방")).toBeInTheDocument();
    expect(screen.getByText("조명/기타")).toBeInTheDocument();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/usage/analysis",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    renderUsage();
    await waitFor(() =>
      expect(screen.getByText("데이터를 불러올 수 없습니다.")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "재시도" })).toBeInTheDocument();
  });
});
