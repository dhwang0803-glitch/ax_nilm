import { expect, test } from "@playwright/test";

test("로그인 → 사이드바 AI 진단 → 4 섹션 visible", async ({ page }) => {
  await page.goto("/auth/login");
  await page.getByLabel("이메일").fill("test@example.com");
  await page.getByLabel("비밀번호").fill("nilm-mock-2026!");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/home$/);

  await page.getByRole("link", { name: "AI 진단" }).click();
  await expect(page).toHaveURL(/\/insights$/);

  await expect(
    page.getByRole("heading", { name: "AI 진단", level: 2 })
  ).toBeVisible();

  // KPI 3
  await expect(page.getByText("이번 주 진단")).toBeVisible();
  await expect(page.getByText("이번 달 예상 절약")).toBeVisible();
  await expect(page.getByText("모델 신뢰도")).toBeVisible();

  // Highlight + 표 + 추이
  await expect(
    page.getByRole("heading", { name: "최근 이상 사용" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /추천 조치 \(\d+건\)/ })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "주간 진단 추이" })
  ).toBeVisible();

  // mock 데이터 검증
  await expect(page.getByText("정상 대비 25% 과소비")).toBeVisible();
  await expect(page.getByText("필터 청소 · 설정 온도 +1℃")).toBeVisible();
});
