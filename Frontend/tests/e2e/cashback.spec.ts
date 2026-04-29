import { expect, test } from "@playwright/test";

test("로그인 → 사이드바 캐시백 → 목표 트래커 + 차트 + 미션", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByRole("link", { name: "캐시백" }).click();
  await expect(page).toHaveURL(/\/cashback$/);

  await expect(page.getByRole("heading", { name: "목표 트래커" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /11월 목표/ })).toBeVisible();
  await expect(page.getByText("D-15")).toBeVisible();
  await expect(page.getByRole("heading", { name: "주간 전력 소모량" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "월별 전력 소모량" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "오늘의 미션" })).toBeVisible();
  await expect(page.getByText(/저녁 19–21시 건조기 미사용/)).toBeVisible();
});
