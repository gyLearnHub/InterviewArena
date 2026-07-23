import { expect, test } from "@playwright/test";

const simulationInterviewId = 93;
const historyInterviewId = 94;

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

test("simulation mode hides in-round feedback but reveals completed-round evaluations", async ({
  page
}) => {
  const technicalRoundId = 9302;
  const currentQuestionId = 9322;
  const answer = "我先用监控定位慢查询，再补索引并用压测验证优化结果。";

  await page.route(`**/api/interviews/${simulationInterviewId}/state`, async (route) => {
    await route.fulfill({
      json: {
        interview_id: simulationInterviewId,
        mode: "multi_round",
        experience_mode: "simulation",
        overall_status: "in_progress",
        target_position: "后端工程师",
        job_description: null,
        interview_goal: "campus",
        difficulty: "normal",
        time_limit_minutes: 45,
        current_round: "technical",
        elapsed_seconds: 120,
        rounds: [
          {
            id: 9301,
            round_type: "resume",
            status: "completed",
            score: 82,
            result: "passed",
            elapsed_seconds: 60,
            difficulty: "normal",
            time_limit_minutes: 45
          },
          {
            id: technicalRoundId,
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
          id: currentQuestionId,
          round_id: technicalRoundId,
          sequence: 2,
          question_kind: "main",
          question_status: "active",
          parent_question_id: null,
          question_type: "technical",
          question: "你如何验证这次性能优化确实有效？"
        },
        qa_history: [
          {
            id: 9311,
            round_id: 9301,
            round_type: "resume",
            sequence: 1,
            question_kind: "main",
            question_status: "active",
            question: "请介绍你负责的核心项目。",
            answer: "我负责面试平台的服务编排。",
            question_evaluation: evaluation(9311, 9301, "resume", 82, "继续强调业务结果。")
          },
          {
            id: 9321,
            round_id: technicalRoundId,
            round_type: "technical",
            sequence: 1,
            question_kind: "main",
            question_status: "active",
            question: "请介绍一次接口性能优化。",
            answer: "我通过索引优化降低了查询耗时。",
            question_evaluation: evaluation(
              9321,
              technicalRoundId,
              "technical",
              76,
              "下一步补充压测数据。"
            )
          }
        ]
      }
    });
  });
  await page.route("**/api/interviews/*/rounds/*/questions/*/draft", async (route) => {
    const match = route
      .request()
      .url()
      .match(/questions\/(\d+)\/draft/);
    await route.fulfill({
      json: { question_id: Number(match?.[1] || 0), answer: "", updated_at: null }
    });
  });
  await page.route(
    `**/api/interviews/${simulationInterviewId}/rounds/${technicalRoundId}/answers-task`,
    async (route) => {
      await route.fulfill({
        json: {
          task_id: 9399,
          operation: "answer_round_question",
          status: "completed",
          interview_id: simulationInterviewId,
          round_id: technicalRoundId,
          result: {
            action: "next_question",
            question: {
              id: 9323,
              round_id: technicalRoundId,
              sequence: 3,
              question_kind: "follow_up",
              question_status: "active",
              parent_question_id: currentQuestionId,
              question_type: "technical",
              question: "压测中你重点观察哪些指标？"
            },
            round_summary: {
              score: 79,
              strengths: ["定位过程清楚。"],
              suggestions: ["补充指标。"]
            },
            answer_evaluation: evaluation(
              currentQuestionId,
              technicalRoundId,
              "technical",
              79,
              "补充 P95 和错误率。"
            )
          }
        }
      });
    }
  );

  await page.goto(`/interviews/multi/${simulationInterviewId}`);

  await expect(page.getByTestId("experience-mode")).toHaveText("真实模拟 · 轮后反馈");
  await expect(page.locator(".answer-quality-panel")).toHaveCount(0);
  await expect(page.getByText("下一步补充压测数据。")).toHaveCount(0);

  await page.locator(".round-card").filter({ hasText: "简历面" }).click();
  await expect(page.locator(".answer-quality-panel")).toBeVisible();
  await expect(page.getByText("继续强调业务结果。")).toBeVisible();

  await page.locator(".round-card").filter({ hasText: "技术面" }).click();
  await expect(page.locator(".answer-quality-panel")).toHaveCount(0);
  const composer = page.getByPlaceholder("输入你的回答...");
  await composer.fill(answer);
  await composer.press("Enter");

  await expect(page.getByText("压测中你重点观察哪些指标？")).toBeVisible();
  await expect(page.locator(".answer-quality-panel")).toHaveCount(0);
  await expect(page.locator(".summary-panel")).toHaveCount(0);
  await expect(page.getByText("补充 P95 和错误率。")).toHaveCount(0);
});

test("history review submits immutable reanswers and compares scored attempts", async ({
  page
}) => {
  const questionId = 9401;
  const originalAnswer = "我优化了接口性能，但没有记录具体指标。";
  const firstReanswer = "我通过索引优化把接口耗时降低了一些。";
  const secondReanswer =
    "我定位到慢查询后补充联合索引，将 P95 从 420ms 降到 160ms，并验证错误率无回升。";
  let submittedAnswer = "";

  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 1,
        report_count: 1,
        personalized_feedback_used: false,
        latest_interview: null,
        latest_report: null,
        score_trend: [{ interview_id: historyInterviewId, score: 70, created_at: "2026-07-20" }],
        score_delta: null,
        abilities: [],
        weak_points: []
      }
    });
  });
  await page.route(`**/api/interviews/${historyInterviewId}`, async (route) => {
    await route.fulfill({
      json: {
        interview_id: historyInterviewId,
        target_position: "后端工程师",
        status: "finished",
        mode: "multi_round",
        experience_mode: "simulation",
        overall_status: "finished",
        rounds: [
          {
            id: 9400,
            round_type: "resume",
            status: "completed",
            score: 70,
            result: "passed",
            elapsed_seconds: 600,
            difficulty: "normal",
            time_limit_minutes: 45
          }
        ],
        qa_history: [
          {
            id: questionId,
            round_id: 9400,
            round_type: "resume",
            sequence: 1,
            question_kind: "main",
            question_status: "active",
            question: "请介绍一次接口性能优化经历。",
            answer: originalAnswer,
            question_evaluation: evaluation(questionId, 9400, "resume", 70, "补充量化指标。")
          }
        ],
        resume: { id: 7, created_at: "2026-07-20T09:00:00Z", structured_data: {} },
        feedback_report: {
          score: 70,
          weaknesses: ["缺少量化证据"],
          suggestions: ["补充优化前后的指标"],
          report_reliability_status: "normal"
        },
        started_at: "2026-07-20T09:30:00Z",
        ended_at: "2026-07-20T10:00:00Z"
      }
    });
  });
  await page.route(
    `**/api/interviews/${historyInterviewId}/questions/${questionId}/reanswers`,
    async (route) => {
      if (route.request().method() === "POST") {
        submittedAnswer = (route.request().postDataJSON() as { answer: string }).answer;
        await route.fulfill({
          status: 201,
          json: {
            interview_id: historyInterviewId,
            question_id: questionId,
            question: "请介绍一次接口性能优化经历。",
            original_answer: originalAnswer,
            original_evaluation: evaluation(questionId, 9400, "resume", 70, "补充量化指标。"),
            attempt: reanswerAttempt(2, secondReanswer, 88, 18, "继续补充容量上限。")
          }
        });
        return;
      }
      await route.fulfill({
        json: {
          interview_id: historyInterviewId,
          question_id: questionId,
          question: "请介绍一次接口性能优化经历。",
          original_answer: originalAnswer,
          original_evaluation: evaluation(questionId, 9400, "resume", 70, "补充量化指标。"),
          attempts: [reanswerAttempt(1, firstReanswer, 78, 8, "补充准确耗时。")]
        }
      });
    }
  );

  await page.goto(`/reports/${historyInterviewId}`);
  await page.locator(".round-toggle").first().click();
  await page.getByRole("button", { name: /重新作答与对比/ }).click();

  await expect(page.getByText("第 1 次尝试")).toBeVisible();
  await expect(page.locator(".attempt-score").getByText("+8 分")).toBeVisible();
  await expect(page.getByText(firstReanswer, { exact: true })).toBeVisible();

  await page.getByLabel("这一次，你会怎么回答？").fill(secondReanswer);
  await page.getByRole("button", { name: "提交新回答" }).click();

  expect(submittedAnswer).toBe(secondReanswer);
  await expect(page.getByText("第 2 次尝试")).toBeVisible();
  await expect(page.locator(".attempt-score").getByText("+18 分")).toBeVisible();
  const newestAttempt = page.locator(".attempt-card").first();
  await expect(newestAttempt.getByText(originalAnswer, { exact: true })).toBeVisible();
  await expect(newestAttempt.getByText(secondReanswer, { exact: true })).toBeVisible();
  await expect(newestAttempt.getByText("结构完整度", { exact: true })).toBeVisible();
  await expect(newestAttempt.getByRole("heading", { name: "本次亮点" })).toBeVisible();
  await expect(newestAttempt.getByRole("heading", { name: "本次仍需改进" })).toBeVisible();
  await expect(newestAttempt.getByRole("heading", { name: "本次改进建议" })).toBeVisible();
  await expect(newestAttempt.getByText("继续补充容量上限。")).toBeVisible();
});

test("in-progress history does not offer reanswer actions", async ({ page }) => {
  const interviewId = 95;
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 1,
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
  await page.route(`**/api/interviews/${interviewId}`, async (route) => {
    await route.fulfill({
      json: {
        interview_id: interviewId,
        target_position: "后端工程师",
        status: "in_progress",
        mode: "multi_round",
        experience_mode: "training",
        overall_status: "in_progress",
        rounds: [
          {
            id: 9500,
            round_type: "resume",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 60,
            difficulty: "normal",
            time_limit_minutes: 45
          }
        ],
        qa_history: [
          {
            id: 9501,
            round_id: 9500,
            round_type: "resume",
            sequence: 1,
            question_kind: "main",
            question_status: "active",
            question: "请介绍最近的项目。",
            answer: "我负责后端服务开发。"
          }
        ],
        resume: { id: 8, created_at: "2026-07-20T09:00:00Z", structured_data: {} },
        feedback_report: null,
        started_at: "2026-07-20T09:30:00Z",
        ended_at: null
      }
    });
  });

  await page.goto(`/reports/${interviewId}`);
  await page.locator(".round-toggle").first().click();
  await expect(page.getByRole("button", { name: /重新作答与对比/ })).toHaveCount(0);
});

function evaluation(
  questionId: number,
  roundId: number,
  roundType: string,
  score: number,
  suggestion: string
) {
  return {
    question_id: questionId,
    round_id: roundId,
    round_type: roundType,
    status: "succeeded",
    total_score: score,
    dimension_scores: [
      { dimension: "结构完整度", score, reason: "表达结构可追踪。" },
      { dimension: "证据充分度", score: score - 5, reason: "仍可补充更多数据。" }
    ],
    strengths: ["回答过程清晰。"],
    issues: ["证据仍可更具体。"],
    evidence: ["包含定位与优化动作。"],
    should_follow_up: true,
    follow_up_direction: suggestion
  };
}

function reanswerAttempt(
  attemptNumber: number,
  answer: string,
  score: number,
  scoreDelta: number,
  suggestion: string
) {
  return {
    id: 9500 + attemptNumber,
    attempt_number: attemptNumber,
    answer,
    evaluation: evaluation(9401, 9400, "resume", score, suggestion),
    score_delta: scoreDelta,
    created_at: `2026-07-20T10:0${attemptNumber}:00Z`
  };
}
