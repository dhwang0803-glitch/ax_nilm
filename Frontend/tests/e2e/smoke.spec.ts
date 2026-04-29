import { expect, test } from "@playwright/test";

test("랜딩 페이지 + 보호 라우트 redirect", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "전기요금, 줄인 만큼 돌려받으세요" })
  ).toBeVisible();

  await page.goto("/usage");
  await expect(page).toHaveURL(/\/auth\/login$/);
  await expect(page.getByRole("heading", { name: "로그인" })).toBeVisible();
});
