import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AccountPage } from "../../src/features/settings/AccountPage";
import { server } from "./setup";

function renderAccount() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AccountPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AccountPage", () => {
  it("renders profile + kepco cards on success", async () => {
    renderAccount();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "프로필" })).toBeInTheDocument()
    );
    expect(screen.getByRole("heading", { name: "한전 연동" })).toBeInTheDocument();
    expect(screen.getByText("테스터")).toBeInTheDocument();
    expect(screen.getByText("test@example.com")).toBeInTheDocument();
    expect(screen.getByText("010-****-1234")).toBeInTheDocument();
    expect(screen.getByText("3명")).toBeInTheDocument();
    expect(screen.getByText("12-3456-7890-12")).toBeInTheDocument();
    expect(screen.getByText("서울특별시 ○○구 ○○로 ***")).toBeInTheDocument();
    expect(screen.getByText("주택용 저압")).toBeInTheDocument();
    expect(screen.getByText("2026-04-15")).toBeInTheDocument();
  });

  it("shows visual-only pill buttons (수정 / 재연동)", async () => {
    renderAccount();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "프로필" })).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "수정" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "재연동" })).toBeInTheDocument();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/settings/account",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    renderAccount();
    await waitFor(() =>
      expect(screen.getByText("데이터를 불러올 수 없습니다.")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: "재시도" })).toBeInTheDocument();
  });
});
