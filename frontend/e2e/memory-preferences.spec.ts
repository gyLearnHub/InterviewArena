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
  await page.route("**/api/review-bookmarks**", async (route) => {
    await route.fulfill({ json: [] });
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

test("memory page shows accumulated memories", async ({ page }) => {
  await page.route("**/api/memories?**", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            id: 1,
            memory_type: "weakness",
            title: "索引原理需要加强",
            content: "需要补充覆盖索引和回表分析。",
            confidence: 0.9,
            status: "active",
            index_status: "indexed",
            source_interview_id: 10,
            source_round_id: 20,
            target_position: "后端工程师",
            evidence: ["回答缺少执行计划证据"],
            created_at: "2026-07-10T10:00:00",
            updated_at: "2026-07-10T10:00:00"
          },
          {
            id: 2,
            memory_type: "preference",
            title: "偏好结构化回答",
            content: "回答时优先使用背景、行动和结果结构。",
            confidence: 0.8,
            status: "active",
            index_status: "indexed",
            source_interview_id: null,
            source_round_id: null,
            target_position: null,
            evidence: [],
            created_at: "2026-07-10T11:00:00",
            updated_at: "2026-07-10T11:00:00"
          }
        ],
        total: 2,
        active_count: 2,
        pending_review_count: 0,
        limit: 100,
        offset: 0,
        next_offset: null
      }
    });
  });

  await page.goto("/memories");

  await expect(page.getByRole("region", { name: "记忆概览" }).getByText("2").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "索引原理需要加强" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "偏好结构化回答" })).toBeVisible();
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
