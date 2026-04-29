import { expect, test } from "@playwright/test";

test("로그인 성공 → from(/usage) origin 으로 redirect", async ({ page }) => {
  await page.goto("/usage");
  await expect(page).toHaveURL(/\/auth\/login(\?|$)/);
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("password123");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/usage$/);
  await expect(page.getByRole("heading", { name: "사용량 분석" })).toBeVisible();
});

test("잘못된 자격증명 → 401 inline 에러", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("wrong@test.com");
  await page.getByLabel("비밀번호").fill("wrongpass1");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page.getByText("이메일 또는 비밀번호가 일치하지 않습니다")).toBeVisible();
});

test("회원가입 + KEPCO 나중에 하기 → /home", async ({ page }) => {
  await page.goto("/auth/signup");
  await page.getByLabel("이메일").fill("new@example.com");
  await page.getByLabel("비밀번호", { exact: true }).fill("password123");
  await page.getByLabel("비밀번호 확인").fill("password123");
  await page.getByLabel("이름").fill("새 사용자");
  await page.getByLabel("나중에 하기").check();
  await expect(page.getByText(/추후 입력 가능합니다/)).toBeVisible();
  await page.getByLabel(/이용약관/).check();
  await page.getByRole("button", { name: "회원가입" }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test("로그인 → 로그아웃 dropdown → /auth/login", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("password123");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByLabel("계정 메뉴").click();
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page).toHaveURL(/\/auth\/login(\?|$)/);
});
