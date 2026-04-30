import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SecurityPage } from "../../src/features/settings/SecurityPage";
import { server } from "./setup";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SecurityPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SecurityPage", () => {
  it("renders 4 cards on success", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "비밀번호 변경" })
      ).toBeInTheDocument()
    );
    expect(
      screen.getByRole("heading", { name: "2단계 인증" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "활성 세션" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "위험 영역" })
    ).toBeInTheDocument();
  });

  it("password form: empty submit shows error", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "비밀번호 변경" })
      ).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: "변경" }));
    expect(
      await screen.findByText("모든 항목을 입력해주세요.")
    ).toBeInTheDocument();
  });

  it("password form: mismatch between next and confirm shows error", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "비밀번호 변경" })
      ).toBeInTheDocument()
    );

    await user.type(screen.getByLabelText("현재 비밀번호"), "old-pw");
    await user.type(screen.getByLabelText("신규 비밀번호"), "new-pw-1");
    await user.type(screen.getByLabelText("신규 비밀번호 확인"), "new-pw-2");
    await user.click(screen.getByRole("button", { name: "변경" }));

    expect(
      await screen.findByText(
        "신규 비밀번호와 확인이 일치하지 않습니다."
      )
    ).toBeInTheDocument();
  });

  it("password form: valid submit shows success message", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "비밀번호 변경" })
      ).toBeInTheDocument()
    );

    await user.type(screen.getByLabelText("현재 비밀번호"), "old-pw");
    await user.type(screen.getByLabelText("신규 비밀번호"), "new-pw-9");
    await user.type(screen.getByLabelText("신규 비밀번호 확인"), "new-pw-9");
    await user.click(screen.getByRole("button", { name: "변경" }));

    expect(
      await screen.findByText(/비밀번호가 변경되었습니다/)
    ).toBeInTheDocument();
  });

  it("2FA toggle changes status pill", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "2단계 인증" })
      ).toBeInTheDocument()
    );

    expect(screen.getByText("미설정")).toBeInTheDocument();
    await user.click(screen.getByRole("switch", { name: "2단계 인증 사용" }));
    expect(screen.getByText("활성")).toBeInTheDocument();
  });

  it("sessions table: 3 rows, current row marked + logout disabled", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "활성 세션" })
      ).toBeInTheDocument()
    );

    expect(screen.getByText("Chrome · macOS")).toBeInTheDocument();
    expect(screen.getByText("Safari · iPhone 15")).toBeInTheDocument();
    expect(screen.getByText("Edge · Windows 11")).toBeInTheDocument();

    expect(screen.getByText("현재")).toBeInTheDocument();

    const currentRow = screen.getByText("Chrome · macOS").closest("tr")!;
    expect(
      within(currentRow).getByRole("button", { name: "로그아웃" })
    ).toBeDisabled();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/settings/security",
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
