import { expect, test } from "@playwright/test";

test("랜딩 페이지 + 보호 라우트 redirect", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /매달 받는 캐시백/ })).toBeVisible();

  await page.goto("/usage");
  await expect(page).toHaveURL(/\/auth\/login$/);
  await expect(page.getByRole("heading", { name: "로그인" })).toBeVisible();
});
