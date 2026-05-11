import { expect, test } from "@playwright/test";

test("로그인 후 /home → KPI + 차트 + 가전별 점유율 표시", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  // KPI 3개
  await expect(page.getByText("이번 달 사용량")).toBeVisible();
  await expect(page.getByText("예상 캐시백")).toBeVisible();
  await expect(page.getByText("예상 요금")).toBeVisible();

  // 차트 섹션 헤더
  await expect(page.getByRole("heading", { name: "주간 전력 소모량" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /월별 전력 소모량/ })).toBeVisible();

  // 가전별 점유율
  await expect(page.getByRole("heading", { name: "가전별 점유" })).toBeVisible();
  await expect(page.getByText("냉난방")).toBeVisible();
  await expect(page.getByText("냉장고")).toBeVisible();
});
