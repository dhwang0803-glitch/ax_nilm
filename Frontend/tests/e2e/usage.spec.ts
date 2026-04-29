import { expect, test } from "@playwright/test";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);
}

test("로그인 → /usage 사이드바 진입 → 모든 영역 표시", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "사용량 분석" }).click();
  await expect(page).toHaveURL(/\/usage$/);

  await expect(page.getByRole("heading", { name: "사용량 분석", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: /주간 전력 소모량/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /시간대별 평균/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /가전별 분해/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /월별 전력 소모량/ })).toBeVisible();
  await expect(page.getByText("에어컨/난방")).toBeVisible();
});

test("CSV 내보내기 placeholder alert", async ({ page }) => {
  await login(page);
  // SPA navigate (sidebar 클릭) — page.goto 는 브라우저 reload 라 zustand 세션 손실
  await page.getByRole("link", { name: "사용량 분석" }).click();
  await expect(page).toHaveURL(/\/usage$/);
  await expect(page.getByRole("heading", { name: "사용량 분석", level: 1 })).toBeVisible();

  page.on("dialog", async (dialog) => {
    expect(dialog.message()).toContain("준비 중");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "CSV 내보내기" }).click();
});
