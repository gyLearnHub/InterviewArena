import { expect, test } from "./fixtures";

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
  await page.route("**/api/review-bookmarks**", async (route) => {
    await route.fulfill({ json: [] });
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
  await expect(page.getByText("查找使用说明与常见问题。")).toBeVisible();
  await expect(page.getByRole("heading", { name: "如何开始一次多轮模拟面试？" })).toBeVisible();

  await page.getByLabel("问题检索").fill("Harness");

  await expect(page.getByText("找到 1 条相关文档")).toBeVisible();
  await expect(page.getByRole("heading", { name: "高级诊断有什么用？" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "如何开始一次多轮模拟面试？" })).toHaveCount(0);
});

test("feedback entry is available in help navigation and submits the form", async ({ page }) => {
  let feedbackPayload: Record<string, unknown> | null = null;
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
  await page.route("**/api/feedback", async (route) => {
    feedbackPayload = JSON.parse(route.request().postData() || "{}");
    await route.fulfill({
      status: 201,
      json: {
        id: 42,
        feedback_type: "general",
        content: "希望评分证据更具体。",
        rating: 5,
        interview_id: null,
        round_id: null,
        question_id: null,
        status: "new",
        created_at: "2026-07-10T13:30:00",
        updated_at: "2026-07-10T13:30:00"
      }
    });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(page.locator(".side-nav").getByRole("link", { name: "反馈提交" })).toHaveCount(0);
  await page.getByRole("button", { name: "打开主导航" }).click();
  await page.getByRole("link", { name: /帮助中心/ }).click();

  const helpNavButtons = page.locator(".category-panel").getByRole("button");
  await expect(helpNavButtons.nth(0)).toHaveText("全部文档");
  await expect(helpNavButtons.nth(4)).toHaveText("高级功能");
  await expect(helpNavButtons.nth(5)).toHaveText("反馈提交");
  await helpNavButtons.nth(5).click();

  await expect(page).toHaveURL(/\/help$/);
  await expect(page.locator(".result-summary strong")).toHaveText("反馈提交");
  await expect(page.getByRole("heading", { name: "告诉我们哪里需要改进" })).toBeVisible();
  await page.getByRole("button", { name: "5" }).click();
  await page.getByLabel("反馈内容").fill("希望评分证据更具体。");
  await page.getByRole("button", { name: "提交反馈" }).click();

  await expect(page.getByText("反馈已提交，编号 #42。")).toBeVisible();
  expect(feedbackPayload).toEqual({
    feedback_type: "general",
    content: "希望评分证据更具体。",
    rating: 5
  });
});
