import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      json: { id: 1, username: "alice", display_name: "Alice", avatar_url: null }
    });
  });
  await page.route("**/api/notifications/unread-count", async (route) => {
    await route.fulfill({ json: { count: 0 } });
  });
  await page.route("**/api/review-bookmarks?*", async (route) => {
    await route.fulfill({
      json: [
        {
          id: 9,
          title: "项目影响需要量化",
          issue: "回答中缺少可验证的结果数据。",
          suggestion: "补充性能、效率或业务指标的前后对比。",
          status: "active",
          source_score: 68,
          source_interview_id: 77,
          target_position: "前端工程师",
          round_id: 2,
          round_type: "technical",
          question_id: 12,
          question: "你如何证明这次性能优化有效？",
          answer: "我重构了列表渲染逻辑，页面体验有明显改善。",
          practice_interview_id: null,
          created_at: "2026-07-10T09:00:00",
          updated_at: "2026-07-11T10:00:00"
        }
      ]
    });
  });
});

test("review bookmarks read as focused practice tasks", async ({ page }) => {
  await page.goto("/review-bookmarks");

  await expect(page.getByText("当前显示 1 条")).toBeVisible();
  await expect(page.locator(".review-stats")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "项目影响需要量化" })).toBeVisible();
  await expect(page.getByText("你如何证明这次性能优化有效？")).toBeHidden();

  const evidenceButton = page.locator(".evidence-toggle");
  await expect(evidenceButton).toHaveAttribute("aria-expanded", "false");
  await evidenceButton.click();
  await expect(evidenceButton).toHaveAttribute("aria-expanded", "true");
  const evidenceContent = page.locator(".evidence-details dl");
  await expect(evidenceContent).toBeVisible();
  await expect(evidenceContent).toContainText("你如何证明这次性能优化有效？");
  await expect(page.locator(".review-actions")).toHaveCSS("display", "flex");
});

test("review tasks stay within the mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/review-bookmarks");

  await expect(page.getByRole("button", { name: "开始专项" })).toBeVisible();
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
  expect(hasHorizontalOverflow).toBe(false);
});

test("detached bookmarks remain readable without a broken practice action", async ({ page }) => {
  await page.route("**/api/review-bookmarks?*", async (route) => {
    await route.fulfill({
      json: [
        {
          id: 10,
          title: "保留的复盘收藏",
          issue: "原面试已被用户删除。",
          status: "active",
          source_score: 72,
          source_interview_id: null,
          target_position: "后端工程师",
          round_id: null,
          round_type: "technical",
          question_id: null,
          question: "如何做容量规划？",
          answer: "先估算 QPS。",
          practice_interview_id: null,
          created_at: "2026-07-10T09:00:00",
          updated_at: "2026-07-15T10:00:00"
        }
      ]
    });
  });

  await page.goto("/review-bookmarks");

  await expect(page.getByRole("heading", { name: "保留的复盘收藏" })).toBeVisible();
  await expect(page.getByText("原面试已删除")).toBeVisible();
  await expect(page.getByRole("link", { name: "查看原面试" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "仅保留收藏" })).toBeDisabled();
});
