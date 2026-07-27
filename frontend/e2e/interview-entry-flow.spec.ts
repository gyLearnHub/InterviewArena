import { expect, test } from "./fixtures";

const interviewId = 501;
const resumeId = 301;
const resumeRoundId = 601;
const firstQuestionId = 701;
const uploadedResumeName = "candidate-main-flow.docx";
const jobDescription = "负责 AI 面试系统的前端流程、接口联调和体验优化。";
const firstQuestion = "请用一分钟介绍你最近负责的面试系统项目。";

type CreateInterviewPayload = {
  resume_id?: number;
  target_position?: string;
  job_description?: string;
  selected_rounds?: string[];
  interview_goal?: string;
  experience_mode?: string;
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "interview_arena_user",
      JSON.stringify({ id: 1, username: "alice", display_name: "Alice" })
    );
    window.localStorage.removeItem("interview_arena_create_draft:1");
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

test("does not restore another account's create-interview draft", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "interview_arena_create_draft:99",
      JSON.stringify({
        targetPosition: "上一账号岗位",
        jobDescription: "private-draft-from-another-account",
        resumeId: 909,
        resumeName: "private-resume.docx"
      })
    );
  });

  await page.goto("/interviews/new");

  await expect(page.getByText("上一账号岗位")).toHaveCount(0);
  await expect(page.getByText("private-resume.docx")).toHaveCount(0);
  await expect(page.getByLabel("岗位 JD")).not.toHaveValue("private-draft-from-another-account");
});

test("creates an interview from uploaded resume and enters the first round question", async ({
  page
}) => {
  let uploadMethod = "";
  let uploadContentType = "";
  let uploadBodyText = "";
  let createPayload: CreateInterviewPayload | null = null;
  let startRoundMethod = "";
  let startRoundPayload: { difficulty?: string; time_limit_minutes?: number } | null = null;

  await page.route("**/api/resumes/upload-async", async (route) => {
    uploadMethod = route.request().method();
    uploadContentType = route.request().headers()["content-type"] || "";
    uploadBodyText = (await route.request().postDataBuffer())?.toString("utf8") || "";

    await route.fulfill({
      json: {
        task_id: 801,
        status: "processing",
        resume_id: null,
        structured_data: null,
        error_message: null
      }
    });
  });
  await page.route("**/api/resumes/upload-tasks/801", async (route) => {
    await route.fulfill({
      json: {
        task_id: 801,
        status: "completed",
        resume_id: resumeId,
        structured_data: {
          basic_info: { name: "Alice", target_position: "Agent 应用开发" },
          skills: ["Vue", "TypeScript", "Playwright"]
        },
        error_message: null
      }
    });
  });
  await page.route("**/api/interviews", async (route) => {
    createPayload = JSON.parse(route.request().postData() || "{}") as CreateInterviewPayload;

    await route.fulfill({
      json: {
        id: interviewId,
        status: "created",
        mode: "multi_round",
        experience_mode: "simulation",
        interview_goal: "campus",
        difficulty: "normal",
        time_limit_minutes: 45,
        rounds: [],
        harness_status: "pending",
        recovery_count: 0,
        had_degradation: false,
        last_harness_error: null
      }
    });
  });
  await page.route(`**/api/interviews/${interviewId}/state`, async (route) => {
    await route.fulfill({
      json: {
        interview_id: interviewId,
        mode: "multi_round",
        experience_mode: "simulation",
        overall_status: "created",
        target_position: "Agent 应用开发",
        job_description: jobDescription,
        interview_goal: "campus",
        difficulty: "normal",
        time_limit_minutes: 45,
        current_round: null,
        elapsed_seconds: 0,
        harness_status: "running",
        recovery_count: 0,
        had_degradation: false,
        last_harness_error: null,
        rounds: [
          {
            id: resumeRoundId,
            round_type: "resume",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0,
            difficulty: "normal",
            time_limit_minutes: 45
          },
          {
            id: 602,
            round_type: "technical",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0,
            difficulty: "normal",
            time_limit_minutes: 45
          },
          {
            id: 603,
            round_type: "manager",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0,
            difficulty: "normal",
            time_limit_minutes: 45
          },
          {
            id: 604,
            round_type: "hr",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0,
            difficulty: "normal",
            time_limit_minutes: 45
          }
        ],
        current_question: null,
        qa_history: []
      }
    });
  });
  await page.route(
    `**/api/interviews/${interviewId}/rounds/${resumeRoundId}/start-task`,
    async (route) => {
      startRoundMethod = route.request().method();
      startRoundPayload = JSON.parse(route.request().postData() || "{}");

      await route.fulfill({
        json: {
          task_id: 901,
          operation: "start_round",
          status: "processing",
          interview_id: interviewId,
          round_id: resumeRoundId,
          result: null,
          error_code: null,
          error_message: null
        }
      });
    }
  );
  await page.route("**/api/interviews/tasks/901", async (route) => {
    await route.fulfill({
      json: {
        task_id: 901,
        operation: "start_round",
        status: "completed",
        interview_id: interviewId,
        round_id: resumeRoundId,
        result: {
          action: "next_question",
          question: {
            id: firstQuestionId,
            round_id: resumeRoundId,
            sequence: 1,
            question_kind: "main",
            question_status: "active",
            parent_question_id: null,
            question_type: "resume",
            question: firstQuestion
          },
          round_summary: null,
          round: {
            id: resumeRoundId,
            round_type: "resume",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 0
          }
        },
        error_code: null,
        error_message: null
      }
    });
  });
  await page.route(
    `**/api/interviews/${interviewId}/rounds/${resumeRoundId}/questions/${firstQuestionId}/draft`,
    async (route) => {
      await route.fulfill({
        json: { question_id: firstQuestionId, answer: "", updated_at: null }
      });
    }
  );

  await page.goto("/interviews/new");

  await expect(page.getByRole("heading", { name: "新建面试" })).toBeVisible();
  await expect(page.locator(".summary-card")).toHaveCount(1);
  await expect(page.locator(".selection-bar").getByText("当前选择")).toHaveCount(0);
  await expect(page.locator(".stepper").getByRole("button", { name: /简历与岗位/ })).toBeDisabled();
  await page.getByRole("button", { name: /请选择面试方向/ }).click();
  await page.getByRole("option", { name: /Agent 应用开发/ }).click();
  await page.getByRole("button", { name: "下一步" }).click();

  const fileChooserPromise = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: /选择简历/ }).click();
  await page.getByRole("menuitem", { name: /上传新简历/ }).click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.setFiles({
    name: uploadedResumeName,
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("mock docx payload")
  });

  await expect(page.getByRole("button", { name: /candidate-main-flow\.docx/ })).toBeVisible();
  await expect(page.locator(".summary-card").getByText(/candidate-main-flow\.docx/)).toBeVisible();

  await page.getByRole("button", { name: "下一步" }).click();
  const roundGrid = page.getByLabel("面试轮次");
  await expect(roundGrid.getByText("简历面")).toBeVisible();
  await expect(roundGrid.getByText("技术面")).toBeVisible();

  await page.getByRole("button", { name: "下一步" }).click();
  await expect(page.getByRole("radio", { name: /训练模式/ })).toHaveAttribute(
    "aria-checked",
    "true"
  );
  await page.getByRole("radio", { name: /真实模拟模式/ }).click();
  await page.getByLabel("岗位 JD").fill(jobDescription);

  await page.getByRole("button", { name: "下一步" }).click();
  await expect(page.getByRole("heading", { name: "Agent 应用开发" })).toBeVisible();
  await expect(page.locator(".summary-card")).toHaveCount(0);
  await expect(page.locator(".confirm-panel").getByText(/4 个轮次.*简历已就绪/)).toBeVisible();

  await page.getByRole("button", { name: "开始面试" }).click();

  expect(uploadMethod).toBe("POST");
  expect(uploadContentType).toContain("multipart/form-data");
  expect(uploadBodyText).toContain(uploadedResumeName);
  expect(createPayload).toEqual({
    resume_id: resumeId,
    target_position: "Agent 应用开发",
    job_description: jobDescription,
    selected_rounds: ["resume", "technical", "manager", "hr"],
    interview_goal: "campus",
    experience_mode: "simulation"
  });

  await expect(page).toHaveURL(new RegExp(`/interviews/multi/${interviewId}$`));
  await expect(page.getByRole("heading", { name: "Agent 应用开发 · 模拟面试" })).toBeVisible();
  await expect(page.getByTestId("experience-mode")).toHaveText("真实模拟 · 轮后反馈");
  await expect(page.locator(".round-card")).toHaveCount(4);
  expect(
    await page
      .locator(".round-board")
      .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length)
  ).toBe(4);
  await expect(page.locator("button.round-card")).toHaveCount(4);
  await expect(page.locator(".mini-rounds")).toHaveCount(0);
  await expect(page.getByLabel("提交回答")).toBeVisible();

  const resumeCard = page.locator(".round-card").filter({ hasText: "简历面" });
  await expect(resumeCard).toHaveAttribute("aria-disabled", "false");
  await expect(resumeCard).toHaveClass(/is-active-view/);

  await page.getByLabel("打开面试操作菜单").click();
  await page.getByRole("button", { name: "开始本轮" }).click();
  const roundConfigDialog = page.getByRole("dialog", { name: "简历面" });
  await expect(roundConfigDialog).toBeVisible();
  await expect(roundConfigDialog.getByRole("button", { name: /普通/ })).toHaveClass(/active/);
  await expect(roundConfigDialog.getByRole("button", { name: /45 分钟/ })).toHaveClass(/active/);
  await roundConfigDialog.getByRole("button", { name: "开始本轮" }).click();

  await expect(page.getByText(firstQuestion)).toBeVisible();
  await expect(resumeCard).toHaveClass(/in_progress/);
  await expect(page.getByPlaceholder("输入你的回答...")).toBeEnabled();
  expect(startRoundMethod).toBe("POST");
  expect(startRoundPayload).toEqual({ difficulty: "normal", time_limit_minutes: 45 });
});
