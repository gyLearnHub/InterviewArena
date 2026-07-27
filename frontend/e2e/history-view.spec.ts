import { expect, test } from "./fixtures";

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
    const query = new URL(route.request().url()).searchParams.get("query");
    await route.fulfill({
      json: {
        items: query
          ? [
              {
                interview_id: 21,
                target_position: "后端平台工程师",
                status: "finished",
                overall_status: "finished",
                created_at: "2026-07-01T09:00:00",
                updated_at: "2026-07-01T10:00:00",
                report_reliability_status: "normal"
              }
            ]
          : [
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
  await page.route("**/api/interviews/reports/page?*", async (route) => {
    const sort = new URL(route.request().url()).searchParams.get("sort");
    const reports = [
      {
        interview_id: 31,
        target_position: "后端工程师",
        score: 72,
        report_reliability_status: "normal",
        created_at: "2026-07-12T10:00:00",
        used_candidate_memory: false
      },
      {
        interview_id: 22,
        target_position: "平台架构师",
        score: 96,
        report_reliability_status: "normal",
        created_at: "2026-07-01T10:00:00",
        used_candidate_memory: false
      }
    ];
    await route.fulfill({
      json: {
        items: sort === "score-desc" ? [...reports].reverse() : reports,
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
  await expect(panel.getByText("已加载 2 场面试")).toBeVisible();
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

test("history search loads server-side matches beyond the initial page", async ({ page }) => {
  await page.goto("/history");

  await page.getByPlaceholder("搜索岗位或面试记录").fill("后端平台");

  await expect(page.getByText("后端平台工程师")).toBeVisible();
  await expect(page.getByText("#21")).toBeVisible();
  await expect(page.getByText("没有符合条件的记录")).toHaveCount(0);
});

test("report score sorting uses server-side global order", async ({ page }) => {
  await page.goto("/reports");

  await page.getByLabel("排序").selectOption("score-desc");

  const firstRow = page.locator(".history-table tbody tr").first();
  await expect(firstRow.getByText("平台架构师")).toBeVisible();
  await expect(firstRow.getByText("96 分")).toBeVisible();
});
