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
  await page.route("**/api/memories/clear-status", async (route) => {
    await route.fulfill({
      json: { task_id: null, status: "idle", deleted_count: 0, error_message: null }
    });
  });
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 0,
        report_count: 0,
        personalized_feedback_used: false,
        memory_status: "accumulating",
        candidate_memory_count: 0,
        latest_interview: null,
        latest_report: null
      }
    });
  });
});

test("dashboard shows accumulated memory when memories exist before report reuse", async ({
  page
}) => {
  await page.unroute("**/api/dashboard/summary");
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 2,
        report_count: 2,
        personalized_feedback_used: false,
        memory_status: "ready",
        candidate_memory_count: 2,
        latest_interview: null,
        latest_report: null,
        score_trend: [],
        abilities: [],
        weak_points: []
      }
    });
  });
  await page.route("**/api/user/preferences", async (route) => {
    await route.fulfill({ json: { memory_enabled: true } });
  });

  await page.goto("/dashboard");

  await expect(page.getByText("记忆系统")).toBeVisible();
  await expect(page.getByText("已积累 2 条")).toBeVisible();
  await expect(page.getByText("待积累")).toHaveCount(0);
});

test("memory toggle keeps previous UI state when preference API fails", async ({ page }) => {
  let patchCalled = false;

  await page.route("**/api/user/preferences", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { memory_enabled: true }
      });
      return;
    }

    patchCalled = true;
    await route.fulfill({
      status: 500,
      json: { error: { code: "INTERNAL_ERROR", message: "save failed" } }
    });
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: /Alice/ }).click();
  await page.getByRole("menuitem", { name: "设置" }).click();
  await page.getByRole("button", { name: "个性化" }).click();

  const toggle = page.getByRole("button", { name: "已开启" });
  await expect(toggle).toHaveAttribute("aria-pressed", "true");

  await toggle.click();

  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("save failed")).toBeVisible();
  expect(patchCalled).toBe(true);
});

test("memory toggle updates UI only after preference API succeeds", async ({ page }) => {
  await page.route("**/api/user/preferences", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: { memory_enabled: true }
      });
      return;
    }

    await route.fulfill({
      json: { memory_enabled: false }
    });
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: /Alice/ }).click();
  await page.getByRole("menuitem", { name: "设置" }).click();
  await page.getByRole("button", { name: "个性化" }).click();
  await page.getByRole("button", { name: "已开启" }).click();

  const disabledToggle = page.getByRole("button", { name: "已关闭" });
  await expect(disabledToggle).toHaveAttribute("aria-pressed", "false");
});

test("memory clear task status is shown and refreshed in settings dialog", async ({ page }) => {
  await page.unroute("**/api/memories/clear-status");
  await page.route("**/api/user/preferences", async (route) => {
    await route.fulfill({
      json: { memory_enabled: true }
    });
  });

  let clearStatusCalls = 0;
  await page.route("**/api/memories/clear-status", async (route) => {
    clearStatusCalls += 1;
    await route.fulfill({
      json:
        clearStatusCalls < 2
          ? { task_id: null, status: "idle", deleted_count: 0, error_message: null }
          : { task_id: 7, status: "completed", deleted_count: 3, error_message: null }
    });
  });
  await page.route("**/api/memories", async (route) => {
    await route.fulfill({
      json: { task_id: 7, status: "pending", deleted_count: 0, error_message: null }
    });
  });
  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });

  await page.goto("/dashboard");
  await page.getByRole("button", { name: /Alice/ }).click();
  await page.getByRole("menuitem", { name: "设置" }).click();
  await page.getByRole("button", { name: "清除" }).click();

  await expect(page.getByText("清除任务等待中")).toBeVisible();
  await expect(page.getByText("个人长期记忆已清除")).toBeVisible();
  await expect(page.getByText("已清除记忆：3")).toBeVisible();
});
