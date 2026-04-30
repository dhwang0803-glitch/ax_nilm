import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { NotificationsPage } from "../../src/features/settings/NotificationsPage";
import { server } from "./setup";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("NotificationsPage", () => {
  it("renders matrix (4 kinds × 3 channels) + dnd card on success", async () => {
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("이상 탐지")).toBeInTheDocument()
    );

    // 매트릭스 12 (role=checkbox) + 방해 금지 토글 1 (role=switch)
    expect(screen.getAllByRole("checkbox")).toHaveLength(12);
    expect(screen.getAllByRole("switch")).toHaveLength(1);

    expect(screen.getByLabelText("이상 탐지 이메일")).toBeChecked();
    expect(screen.getByLabelText("캐시백 정산 SMS")).not.toBeChecked();
    expect(screen.getByLabelText("시스템 공지 이메일")).not.toBeChecked();

    expect(
      screen.getByRole("heading", { name: "방해 금지 시간" })
    ).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeChecked();
  });

  it("toggles a matrix cell on click", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("이상 탐지")).toBeInTheDocument()
    );

    const cell = screen.getByLabelText("주간 리포트 푸시");
    expect(cell).not.toBeChecked();
    await user.click(cell);
    expect(cell).toBeChecked();
  });

  it("disables DnD selects when switch is turned off", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("이상 탐지")).toBeInTheDocument()
    );

    const startSelect = screen.getByLabelText("시작") as HTMLSelectElement;
    expect(startSelect).not.toBeDisabled();

    await user.click(screen.getByRole("switch"));
    expect(startSelect).toBeDisabled();
  });

  it("shows error UI with retry button when API fails", async () => {
    server.use(
      http.get(
        "/api/settings/notifications",
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
