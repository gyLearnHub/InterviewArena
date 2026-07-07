import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "interview_arena_user",
      JSON.stringify({ id: 1, username: "alice", display_name: "Alice" })
    );
  });

  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      json: { id: 1, username: "alice", display_name: "Alice", avatar_url: null }
    });
  });

  await page.route("**/api/notifications/unread-count", async (route) => {
    await route.fulfill({ json: { count: 0 } });
  });
});

test("help center keeps documents and search reachable from sidebar", async ({ page }) => {
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 0,
        report_count: 0,
        personalized_feedback_used: false,
        latest_interview: null,
        latest_report: null,
        score_trend: [],
        score_delta: null,
        abilities: [],
        weak_points: []
      }
    });
  });

  await page.goto("/dashboard");
  await page.getByRole("link", { name: /帮助中心/ }).click();

  await expect(page).toHaveURL(/\/help$/);
  await expect(page.getByRole("heading", { name: "查找使用说明与常见问题" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "如何开始一次多轮模拟面试？" })).toBeVisible();

  await page.getByLabel("问题检索").fill("Harness");

  await expect(page.getByText("找到 1 条相关文档")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Harness 状态页面有什么用？" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "如何开始一次多轮模拟面试？" })).toHaveCount(0);
});

test("feedback submit is below system status in help navigation and shows update state", async ({
  page
}) => {
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 0,
        report_count: 0,
        personalized_feedback_used: false,
        latest_interview: null,
        latest_report: null,
        score_trend: [],
        score_delta: null,
        abilities: [],
        weak_points: []
      }
    });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(page.locator(".side-nav").getByRole("link", { name: "反馈提交" })).toHaveCount(0);
  await page.getByRole("link", { name: /帮助中心/ }).click();

  const helpNavButtons = page.locator(".category-panel").getByRole("button");
  await expect(helpNavButtons.nth(0)).toHaveText("全部文档");
  await expect(helpNavButtons.nth(4)).toHaveText("系统状态");
  await expect(helpNavButtons.nth(5)).toHaveText("反馈提交");
  await helpNavButtons.nth(5).click();

  await expect(page).toHaveURL(/\/help$/);
  await expect(page.locator(".result-summary strong")).toHaveText("反馈提交");
  await expect(page.getByRole("heading", { name: "该功能正在抓紧更新" })).toBeVisible();
});
