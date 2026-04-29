import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthGuard } from "../../src/features/auth/AuthGuard";
import { useAuth } from "../../src/features/auth/useAuth";

describe("AuthGuard", () => {
  it("redirects to /auth/login when no user", () => {
    useAuth.setState({ user: null });
    render(
      <MemoryRouter initialEntries={["/home"]}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/home" element={<div>HOME PROTECTED</div>} />
          </Route>
          <Route path="/auth/login" element={<div>LOGIN PAGE</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("LOGIN PAGE")).toBeInTheDocument();
  });

  it("renders protected route when user is set", () => {
    useAuth.setState({ user: { id: "u1", email: "a@b.c", name: "tester" } });
    render(
      <MemoryRouter initialEntries={["/home"]}>
        <Routes>
          <Route element={<AuthGuard />}>
            <Route path="/home" element={<div>HOME PROTECTED</div>} />
          </Route>
          <Route path="/auth/login" element={<div>LOGIN PAGE</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("HOME PROTECTED")).toBeInTheDocument();
    useAuth.setState({ user: null });
  });
});
