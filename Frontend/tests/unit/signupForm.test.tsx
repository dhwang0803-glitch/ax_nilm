import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { SignupPage } from "../../src/features/auth/SignupPage";
import { useAuth } from "../../src/features/auth/useAuth";

function renderForm() {
  return render(
    <MemoryRouter initialEntries={["/auth/signup"]}>
      <Routes>
        <Route path="/auth/signup" element={<SignupPage />} />
        <Route path="/home" element={<div>HOME</div>} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => useAuth.setState({ user: null }));

describe("SignupForm", () => {
  it("password mismatch shows error", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "new@example.com");
    await userEvent.type(screen.getByLabelText("비밀번호", { exact: true }), "password123");
    await userEvent.type(screen.getByLabelText("비밀번호 확인"), "different1");
    await userEvent.type(screen.getByLabelText("이름"), "새 사용자");
    await userEvent.click(screen.getByLabelText("나중에 하기"));
    await userEvent.click(screen.getByLabelText(/이용약관/));
    await userEvent.click(screen.getByRole("button", { name: "회원가입" }));
    expect(await screen.findByText("비밀번호가 일치하지 않습니다")).toBeInTheDocument();
  });

  it("agreeTerms unchecked blocks submit", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "new@example.com");
    await userEvent.type(screen.getByLabelText("비밀번호", { exact: true }), "password123");
    await userEvent.type(screen.getByLabelText("비밀번호 확인"), "password123");
    await userEvent.type(screen.getByLabelText("이름"), "새 사용자");
    await userEvent.click(screen.getByLabelText("나중에 하기"));
    await userEvent.click(screen.getByRole("button", { name: "회원가입" }));
    expect(await screen.findByText("약관에 동의해주세요")).toBeInTheDocument();
  });

  it("skipKepco=true skips KEPCO validation and signs up", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "fresh@example.com");
    await userEvent.type(screen.getByLabelText("비밀번호", { exact: true }), "password123");
    await userEvent.type(screen.getByLabelText("비밀번호 확인"), "password123");
    await userEvent.type(screen.getByLabelText("이름"), "테스터");
    await userEvent.click(screen.getByLabelText("나중에 하기"));
    await userEvent.click(screen.getByLabelText(/이용약관/));
    await userEvent.click(screen.getByRole("button", { name: "회원가입" }));
    await waitFor(() => expect(screen.getByText("HOME")).toBeInTheDocument());
    expect(useAuth.getState().user).toMatchObject({ email: "fresh@example.com" });
  });

  it("422 email taken shows server error", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText("이메일"), "taken@test.com");
    await userEvent.type(screen.getByLabelText("비밀번호", { exact: true }), "password123");
    await userEvent.type(screen.getByLabelText("비밀번호 확인"), "password123");
    await userEvent.type(screen.getByLabelText("이름"), "테스터");
    await userEvent.click(screen.getByLabelText("나중에 하기"));
    await userEvent.click(screen.getByLabelText(/이용약관/));
    await userEvent.click(screen.getByRole("button", { name: "회원가입" }));
    expect(await screen.findByText("이미 가입된 이메일입니다")).toBeInTheDocument();
  });
});
