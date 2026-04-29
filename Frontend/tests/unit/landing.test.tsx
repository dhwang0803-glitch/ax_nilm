import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { useAuth } from "../../src/features/auth/useAuth";
import { LandingPage } from "../../src/features/landing/LandingPage";

afterEach(() => {
  useAuth.setState({ user: null });
});

describe("LandingPage", () => {
  it("renders all three sections when unauthenticated", () => {
    useAuth.setState({ user: null });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/매달 받는 캐시백/);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("왜 에너지캐시백인가");
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(3);
  });

  it("redirects to /home when authenticated", () => {
    useAuth.setState({ user: { id: "u1", email: "a@b.c", name: "tester" } });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/home" element={<div>HOME</div>} />
        </Routes>
      </MemoryRouter>
    );
    expect(screen.getByText("HOME")).toBeInTheDocument();
  });
});
