import { expect, test } from "@playwright/test";

const interviewId = 77;
const roundId = 701;
const questionId = 9001;
const answer = "我会先复现问题，再结合日志和指标定位根因。";

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

test("restores the current answer when async submission fails", async ({ page }) => {
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
        current_round: "resume",
        elapsed_seconds: 60,
        rounds: [
          {
            id: roundId,
            round_type: "resume",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 60
          }
        ],
        current_question: {
          id: questionId,
          round_id: roundId,
          sequence: 1,
          question_kind: "main",
          question_status: "active",
          parent_question_id: null,
          question_type: "resume",
          question: "请介绍一次线上问题排查经历。"
        },
        qa_history: []
      }
    });
  });
  await page.route(
    `**/api/interviews/${interviewId}/rounds/${roundId}/questions/${questionId}/draft`,
    async (route) => {
      await route.fulfill({ json: { question_id: questionId, answer: "", updated_at: null } });
    }
  );
  await page.route(
    `**/api/interviews/${interviewId}/rounds/${roundId}/answers-task`,
    async (route) => {
      await route.fulfill({
        status: 503,
        json: { error: { code: "NETWORK_TIMEOUT", message: "提交暂时失败，请重试。" } }
      });
    }
  );

  await page.goto(`/interviews/multi/${interviewId}`);
  const composer = page.getByPlaceholder("输入你的回答...");
  await expect(composer).toBeEnabled();
  await composer.fill(answer);
  await composer.press("Enter");

  await expect(page.locator(".toast.error")).toHaveText("提交暂时失败，请重试。");
  await expect(composer).toHaveValue(answer);
  const storedDraft = await page.evaluate(
    ([currentInterviewId, currentQuestionId]) =>
      window.localStorage.getItem(`multi_round_draft:${currentInterviewId}:${currentQuestionId}`),
    [interviewId, questionId]
  );
  expect(storedDraft).toBe(answer);
});

test("renders each answer tip after its answer and submits a valid review bookmark", async ({
  page
}) => {
  const nextQuestionId = 9002;
  const longIssue = `缺少量化依据${"。".repeat(1100)}`;
  let bookmarkPayload: Record<string, unknown> | null = null;

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
        current_round: "resume",
        elapsed_seconds: 60,
        rounds: [
          {
            id: roundId,
            round_type: "resume",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 60
          }
        ],
        current_question: {
          id: nextQuestionId,
          round_id: roundId,
          sequence: 2,
          question_kind: "main",
          question_status: "active",
          parent_question_id: null,
          question_type: "resume",
          question: "下一题：你如何衡量优化结果？"
        },
        qa_history: [
          {
            id: questionId,
            round_id: roundId,
            round_type: "resume",
            sequence: 1,
            question_kind: "main",
            question_status: "active",
            question: "请介绍一次线上问题排查经历。",
            answer,
            question_evaluation: {
              question_id: questionId,
              round_id: roundId,
              round_type: "resume",
              status: "succeeded",
              total_score: 72,
              dimension_scores: [
                {
                  dimension: "表达质量",
                  score: 72,
                  reason: "过程完整。",
                  internal_note: "must not be submitted"
                }
              ],
              strengths: ["排查过程清楚。"],
              issues: [longIssue],
              evidence: ["先复现问题，再结合日志和指标定位根因。"],
              should_follow_up: true,
              follow_up_direction: "补充量化结果。",
              raw_prompt: "must not be submitted"
            }
          }
        ]
      }
    });
  });
  await page.route(
    `**/api/interviews/${interviewId}/rounds/${roundId}/questions/${nextQuestionId}/draft`,
    async (route) => {
      await route.fulfill({ json: { question_id: nextQuestionId, answer: "", updated_at: null } });
    }
  );
  await page.route("**/api/review-bookmarks", async (route) => {
    bookmarkPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 201,
      json: {
        id: 1,
        title: "缺少量化依据",
        issue: "缺少量化依据",
        suggestion: "补充量化结果。",
        status: "active",
        source_score: 72,
        source_interview_id: interviewId,
        target_position: "后端工程师",
        round_id: roundId,
        round_type: "resume",
        question_id: questionId,
        question: "请介绍一次线上问题排查经历。",
        answer,
        practice_interview_id: null,
        created_at: "2026-07-12T10:00:00Z",
        updated_at: "2026-07-12T10:00:00Z"
      }
    });
  });

  await page.goto(`/interviews/multi/${interviewId}`);

  const answerBubble = page.getByText(answer, { exact: true });
  const tipPanel = page.locator(`.answer-quality-panel[data-question-id="${questionId}"]`);
  const nextQuestion = page.getByText("下一题：你如何衡量优化结果？", { exact: true });
  await expect(tipPanel).toBeVisible();
  expect(
    await page.evaluate(
      ([answerSelector, tipSelector, nextQuestionText]) => {
        const answerElement = document.querySelector(answerSelector);
        const tipElement = document.querySelector(tipSelector);
        const nextElement = Array.from(document.querySelectorAll(".bubble p")).find(
          (element) => element.textContent === nextQuestionText
        );
        return Boolean(
          answerElement &&
          tipElement &&
          nextElement &&
          answerElement.compareDocumentPosition(tipElement) & Node.DOCUMENT_POSITION_FOLLOWING &&
          tipElement.compareDocumentPosition(nextElement) & Node.DOCUMENT_POSITION_FOLLOWING
        );
      },
      [
        `.message-row.user .bubble p`,
        `.answer-quality-panel[data-question-id="${questionId}"]`,
        "下一题：你如何衡量优化结果？"
      ]
    )
  ).toBe(true);
  await expect(answerBubble).toBeVisible();
  await expect(nextQuestion).toBeVisible();
  await expect(tipPanel.getByText("维度表现")).toBeVisible();
  await expect(tipPanel.getByText("做得好的")).toBeVisible();
  await expect(tipPanel.getByText("优先改进")).toBeVisible();
  await expect(tipPanel.getByText("下一步怎么答")).toBeVisible();
  await expect(tipPanel.getByText("表达质量")).toBeVisible();
  await expect(tipPanel.getByText("过程完整。")).toBeVisible();
  await expect(tipPanel.getByText(longIssue)).toHaveCount(1);

  await tipPanel.getByRole("button", { name: "加入复盘" }).click();
  await expect(tipPanel.getByText("已加入首页复盘清单")).toBeVisible();

  expect(bookmarkPayload).not.toBeNull();
  expect(String(bookmarkPayload?.title).length).toBeLessThanOrEqual(500);
  expect(String(bookmarkPayload?.issue).length).toBeLessThanOrEqual(1000);
  const submittedEvaluation = bookmarkPayload?.evaluation as Record<string, unknown>;
  expect(submittedEvaluation.raw_prompt).toBeUndefined();
  expect(
    (submittedEvaluation.dimension_scores as Record<string, unknown>[])[0].internal_note
  ).toBeUndefined();
});
