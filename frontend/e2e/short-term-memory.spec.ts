import { expect, test } from "./fixtures";

const interviewId = 77;

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
  await page.route("**/api/interviews/*/rounds/*/questions/*/draft", async (route) => {
    await route.fulfill({ json: { question_id: 9001, answer: "", updated_at: null } });
  });
});

test("shows all short-term memory runtime states beside the interviewer", async ({ page }) => {
  let memoryStatus: "healthy" | "compressed" | "recovered" | "degraded" = "healthy";
  await page.route(`**/api/interviews/${interviewId}/state`, async (route) => {
    await route.fulfill({
      json: {
        interview_id: interviewId,
        mode: "multi_round",
        overall_status: "in_progress",
        target_position: "后端工程师",
        job_description: null,
        interview_goal: "campus",
        difficulty: "normal",
        time_limit_minutes: 45,
        current_round: "technical",
        elapsed_seconds: 60,
        rounds: [
          {
            id: 701,
            round_type: "technical",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 60,
            difficulty: "normal",
            time_limit_minutes: 45
          }
        ],
        current_question: {
          id: 9001,
          round_id: 701,
          sequence: 1,
          question_kind: "main",
          question_status: "active",
          parent_question_id: null,
          question_type: "database",
          question: "请说明 Redis 持久化策略。"
        },
        qa_history: [],
        short_term_memory: {
          status: memoryStatus,
          source: memoryStatus === "degraded" ? "mysql" : "redis",
          compressed: memoryStatus === "compressed",
          fallback_used: memoryStatus === "recovered" || memoryStatus === "degraded",
          updated_at: "2026-07-16T10:00:00"
        }
      }
    });
  });

  const badge = page.getByTestId("short-term-memory-status");
  await page.goto(`/interviews/multi/${interviewId}`);
  await expect(badge).toHaveText("短期记忆正常");

  memoryStatus = "compressed";
  await page.reload();
  await expect(badge).toHaveText("短期记忆已压缩");

  memoryStatus = "recovered";
  await page.reload();
  await expect(badge).toHaveText("短期记忆已恢复");

  memoryStatus = "degraded";
  await page.reload();
  await expect(badge).toHaveText("短期记忆降级");
  await expect(badge).toHaveAttribute("title", /MySQL/);
});
