import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { LoginPage } from "../../src/features/auth/LoginPage";
import { useAuth } from "../../src/features/auth/useAuth";

function renderForm(initialPath = "/auth/login") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/auth/login" element={<LoginPage />} />
        <Route path="/home" element={<div>HOME</div>} />
        <Route path="/usage" element={<div>USAGE</div>} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => useAuth.setState({ user: null }));

describe("LoginForm", () => {
  it("invalid email shows zod error", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "not-an-email");
    await userEvent.type(screen.getByLabelText("비밀번호"), "nilm-mock-2026!");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByText("올바른 이메일 형식이 아닙니다")).toBeInTheDocument();
  });

  it("password < 8 chars shows zod error", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "test@example.com");
    await userEvent.type(screen.getByLabelText("비밀번호"), "short");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByText("비밀번호는 8자 이상이어야 합니다")).toBeInTheDocument();
  });

  it("successful login sets user and redirects to /home (no from)", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "test@example.com");
    await userEvent.type(screen.getByLabelText("비밀번호"), "nilm-mock-2026!");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(screen.getByText("HOME")).toBeInTheDocument());
    expect(useAuth.getState().user).toMatchObject({ email: "test@example.com" });
  });

  it("successful login redirects to ?from when present", async () => {
    renderForm("/auth/login?from=/usage");
    await userEvent.type(screen.getByLabelText("이메일"), "test@example.com");
    await userEvent.type(screen.getByLabelText("비밀번호"), "nilm-mock-2026!");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(screen.getByText("USAGE")).toBeInTheDocument());
  });

  it("401 response shows server error", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "wrong@test.com");
    await userEvent.type(screen.getByLabelText("비밀번호"), "wrongpass1");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(
      await screen.findByText("이메일 또는 비밀번호가 일치하지 않습니다")
    ).toBeInTheDocument();
  });
});
