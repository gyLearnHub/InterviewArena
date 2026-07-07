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
  await page.route("**/api/interviews/history", async (route) => {
    await route.fulfill({
      json: [
        {
          interview_id: 77,
          target_position: "后端工程师",
          status: "in_progress",
          overall_status: "in_progress",
          created_at: "2026-06-22T09:55:00",
          updated_at: "2026-06-22T10:06:00",
          started_at: "2026-06-22T10:00:00",
          ended_at: null
        }
      ]
    });
  });
  await page.route("**/api/interviews/77/harness", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 77,
        harness_status: "degraded",
        recovery_count: 2,
        had_degradation: true,
        traces: [
          {
            id: 1,
            interview_id: 77,
            round_id: 701,
            node_id: "technical-question-1",
            node_type: "question_generation",
            agent_type: "technical",
            purpose: "generate question",
            status: "completed",
            validation_status: "passed",
            retry_records: [{ reason: "timeout" }],
            degradation_records: [{ reason: "fallback" }],
            elapsed_ms: 1200,
            execution_mode: "normal",
            created_at: "2026-06-22T10:05:00",
            updated_at: "2026-06-22T10:06:00"
          }
        ],
        evaluations: [],
        checkpoints: []
      }
    });
  });
});

test("harness status keeps self-evolution out of the frontend page", async ({ page }) => {
  const evolutionRequests: string[] = [];
  await page.route("**/api/internal/evolution/**", async (route) => {
    evolutionRequests.push(route.request().url());
    await route.fulfill({
      status: 404,
      json: { error: { code: "NOT_FOUND", message: "资源不存在。" } }
    });
  });

  await page.goto("/harness");

  await expect(page.getByText("technical-question-1").first()).toBeVisible();
  await expect(page.getByText("1 / 2")).toBeVisible();
  await expect(page.getByRole("heading", { name: "自动进化概览" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "进化运行记录" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "候选队列" })).toHaveCount(0);
  await expect(page.getByText("资源不存在。")).toHaveCount(0);
  expect(evolutionRequests).toEqual([]);
});

test("harness status does not expose candidate action controls", async ({ page }) => {
  const actions: string[] = [];
  await page.route("**/api/internal/evolution/**", async (route) => {
    actions.push(route.request().method());
    await route.fulfill({
      status: 404,
      json: { error: { code: "NOT_FOUND", message: "资源不存在。" } }
    });
  });

  await page.goto("/harness");

  await expect(page.getByRole("button", { name: "通过并应用" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重跑验证" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "回滚" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "标记已处理" })).toHaveCount(0);
  expect(actions).toEqual([]);
});

test("harness status no longer shows evolution empty states", async ({ page }) => {
  await page.goto("/harness");

  await expect(page.getByText("暂无自动进化概览数据")).toHaveCount(0);
  await expect(page.getByText("暂无进化运行记录")).toHaveCount(0);
  await expect(page.getByText("暂无候选队列数据")).toHaveCount(0);
  await expect(page.getByText("暂无版本包与验证记录")).toHaveCount(0);
  await expect(page.getByText("暂无低风险自动应用记录")).toHaveCount(0);
});
