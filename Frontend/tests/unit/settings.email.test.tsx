import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { EmailPage } from "../../src/features/settings/EmailPage";
import { server } from "./setup";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EmailPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("EmailPage", () => {
  it("renders 4 sections (recipient + toggles + test + disclosure) on success", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "수신 이메일" })
      ).toBeInTheDocument()
    );

    expect(screen.getByText("test@example.com")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "이메일 수신 항목" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "테스트 메일 발송" })
    ).toBeInTheDocument();
    expect(screen.getByText(/마지막 발송: 2026-04-25/)).toBeInTheDocument();
    expect(
      screen.getByText(/SMTP \/ POP 직접 설정/)
    ).toBeInTheDocument();
  });

  it("checking '다른 주소 사용' reveals alternate input", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "수신 이메일" })
      ).toBeInTheDocument()
    );

    expect(screen.queryByLabelText("대체 주소")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("다른 주소 사용"));
    expect(screen.getByLabelText("대체 주소")).toBeInTheDocument();
  });

  it("4 toggle switches, initial state matches mock (anomaly + cashback on)", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "이메일 수신 항목" })
      ).toBeInTheDocument()
    );

    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(4);

    expect(screen.getByLabelText("이상 탐지 이메일 수신")).toBeChecked();
    expect(screen.getByLabelText("캐시백 정산 이메일 수신")).toBeChecked();
    expect(screen.getByLabelText("주간 리포트 이메일 수신")).not.toBeChecked();
    expect(screen.getByLabelText("정책 안내 이메일 수신")).not.toBeChecked();
  });

  it("test email button shows mock success message after click", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "테스트 메일 발송" })
      ).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: "테스트 메일 발송" }));
    expect(
      await screen.findByText(/테스트 메일을 발송했습니다/)
    ).toBeInTheDocument();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/settings/email",
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
