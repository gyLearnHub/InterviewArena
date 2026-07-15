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
  await page.route("**/api/review-bookmarks**", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/api/interviews/history/page?*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            interview_id: 18,
            target_position: "前端工程师",
            status: "in_progress",
            overall_status: "in_progress",
            created_at: "2026-07-10T09:00:00",
            updated_at: "2026-07-11T10:30:00",
            report_reliability_status: null
          },
          {
            interview_id: 17,
            target_position: "产品经理",
            status: "finished",
            overall_status: "finished",
            created_at: "2026-07-08T09:00:00",
            updated_at: "2026-07-08T10:00:00",
            report_reliability_status: "normal"
          }
        ],
        next_offset: null
      }
    });
  });
});

test("history uses one compact surface and a structured record table", async ({ page }) => {
  await page.goto("/history");

  const panel = page.getByRole("region", { name: "历史记录" });
  await expect(panel.getByLabel("历史筛选")).toBeVisible();
  await expect(panel.getByRole("table")).toBeVisible();
  await expect(panel.getByText("共 2 场面试")).toBeVisible();
  await expect(page.getByRole("group", { name: "视图切换" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "继续" })).toBeVisible();
});

test("history records become readable blocks on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/history");

  const firstRow = page.locator(".history-table tbody tr").first();
  await expect(firstRow).toHaveCSS("display", "block");
  await expect(firstRow.getByText("前端工程师")).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
  expect(hasHorizontalOverflow).toBe(false);
});
