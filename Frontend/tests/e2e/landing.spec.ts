import { expect, test } from "@playwright/test";

test("PubNav 시작하기 → /auth/login", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "시작하기", exact: true }).click();
  await expect(page).toHaveURL(/\/auth\/login$/);
});

test("Hero 시작하기 · 무료 → /auth/login", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "시작하기 · 무료" }).click();
  await expect(page).toHaveURL(/\/auth\/login$/);
});

test("3 feature 카드 모두 표시", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "가전별 분해" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "주간/월간 추적" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "AI 진단" })).toBeVisible();
});
