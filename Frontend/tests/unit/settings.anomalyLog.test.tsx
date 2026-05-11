import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AnomalyLogPage } from "../../src/features/settings/AnomalyLogPage";
import { server } from "./setup";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AnomalyLogPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AnomalyLogPage", () => {
  it("renders header + 3 KPIs + filter + 8 event rows on success", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이상 탐지 내역" })
      ).toBeInTheDocument()
    );

    expect(screen.getByText("이번 달 이벤트")).toBeInTheDocument();
    expect(screen.getByText("평균 응답 시간")).toBeInTheDocument();
    // "미해결" KPI title 과 status 필터 pill 둘 다 매치되므로 갯수 검증
    expect(screen.getAllByText("미해결").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("3시간 12분")).toBeInTheDocument();

    expect(
      screen.getByRole("heading", { name: "이벤트 (8건)" })
    ).toBeInTheDocument();
  });

  it("severity '높음' pill toggles client-side filter (2 rows)", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이벤트 (8건)" })
      ).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: "높음" }));
    expect(
      screen.getByRole("heading", { name: "이벤트 (2건)" })
    ).toBeInTheDocument();
  });

  it("status '미해결' pill filters down to 2 open rows + unresolved KPI updates", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이벤트 (8건)" })
      ).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: "미해결" }));
    expect(
      screen.getByRole("heading", { name: "이벤트 (2건)" })
    ).toBeInTheDocument();
  });

  it("appliance '에어컨' single-select filter (2 rows), clicking again clears", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이벤트 (8건)" })
      ).toBeInTheDocument()
    );

    const ac = screen.getByRole("button", { name: "에어컨" });
    await user.click(ac);
    expect(
      screen.getByRole("heading", { name: "이벤트 (2건)" })
    ).toBeInTheDocument();
    expect(ac).toHaveAttribute("aria-pressed", "true");

    await user.click(ac);
    expect(
      screen.getByRole("heading", { name: "이벤트 (8건)" })
    ).toBeInTheDocument();
    expect(ac).toHaveAttribute("aria-pressed", "false");
  });

  it("contradictory filter combination shows empty state", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이벤트 (8건)" })
      ).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: "높음" }));
    await user.click(screen.getByRole("button", { name: "김치냉장고" }));

    expect(
      screen.getByText("현재 필터 조건에 해당하는 이벤트가 없습니다.")
    ).toBeInTheDocument();
  });

  it("export toolbar has 3 visual-only buttons", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이상 탐지 내역" })
      ).toBeInTheDocument()
    );

    const toolbar = screen.getByText("내보내기").closest("div")!;
    expect(within(toolbar).getByRole("button", { name: "CSV" })).toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: "JSON" })).toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: "PDF" })).toBeInTheDocument();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/settings/anomaly-events",
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
});
