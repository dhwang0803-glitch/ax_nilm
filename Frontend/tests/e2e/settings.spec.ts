import { expect, test } from "@playwright/test";

test("로그인 → 사이드바 설정 → 프로필 + 한전 연동 카드", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByRole("link", { name: "설정" }).click();
  await expect(page).toHaveURL(/\/settings\/account$/);

  await expect(page.getByRole("heading", { name: "프로필" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "한전 연동" })).toBeVisible();
  await expect(page.getByText("test@example.com")).toBeVisible();
  await expect(page.getByText("주택용 저압")).toBeVisible();

  await expect(page.getByRole("link", { name: "프로필 / 한전 연동" })).toBeVisible();
  await expect(page.getByRole("link", { name: "알림" })).toBeVisible();
  await expect(page.getByRole("link", { name: "보안" })).toBeVisible();
  await expect(page.getByRole("link", { name: "이상 탐지 내역" })).toBeVisible();
  await expect(page.getByRole("link", { name: "이메일 연동" })).toBeVisible();
});

test("설정 → 알림 탭 → 매트릭스 + 방해 금지 카드", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByRole("link", { name: "설정" }).click();
  await expect(page).toHaveURL(/\/settings\/account$/);

  await page.getByRole("link", { name: "알림", exact: true }).click();
  await expect(page).toHaveURL(/\/settings\/notifications$/);

  await expect(
    page.getByRole("heading", { name: "알림 종류 / 채널" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "방해 금지 시간" })
  ).toBeVisible();
  await expect(page.getByText("이상 탐지", { exact: true })).toBeVisible();
  await expect(page.getByLabel("이상 탐지 이메일")).toBeChecked();
});

test("설정 → 보안 탭 → 4 카드 표시", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByRole("link", { name: "설정" }).click();
  await page.getByRole("link", { name: "보안", exact: true }).click();
  await expect(page).toHaveURL(/\/settings\/security$/);

  await expect(
    page.getByRole("heading", { name: "비밀번호 변경" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "2단계 인증" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "활성 세션" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "위험 영역" })
  ).toBeVisible();
  await expect(page.getByText("Chrome · macOS")).toBeVisible();
});
