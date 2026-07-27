import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";

const initialJobDescription = "负责 Agent 产品开发，要求熟悉 Vue、TypeScript 与 RAG。";

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

test("requires a parsed resume and invalidates results when inputs change", async ({ page }) => {
  await seedDraft(page, "parsed");
  const requestPayloads: Array<Record<string, unknown>> = [];
  let analysisCallCount = 0;
  const taskResults = new Map<number, ReturnType<typeof completeAnalysis>>();

  await page.route("**/api/resumes/301/job-match-analysis", async (route) => {
    analysisCallCount += 1;
    const taskId = 8000 + analysisCallCount;
    requestPayloads.push(JSON.parse(route.request().postData() || "{}"));
    if (analysisCallCount === 2) {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    const result =
      analysisCallCount === 3
        ? emptyAnalysis("新 JD 暂未发现明确的匹配或缺口。")
        : completeAnalysis(analysisCallCount === 2 ? "这是一条已过期的分析。" : "岗位匹配度较高。");
    taskResults.set(taskId, result);
    await route.fulfill({
      status: 202,
      json: {
        task_id: taskId,
        status: "pending",
        result: null,
        error_code: null,
        error_message: null
      }
    });
  });
  await page.route("**/api/resumes/job-match-tasks/*", async (route) => {
    const taskId = Number(new URL(route.request().url()).pathname.split("/").pop());
    await route.fulfill({
      json: {
        task_id: taskId,
        status: "completed",
        result: taskResults.get(taskId),
        error_code: null,
        error_message: null
      }
    });
  });
  await page.route("**/api/resumes", async (route) => {
    await route.fulfill({
      json: [resumeListItem(301, "candidate.docx"), resumeListItem(302, "candidate-v2.docx")]
    });
  });

  await page.goto("/interviews/new");
  await goToJobDescriptionStep(page);

  const panel = page.getByRole("region", { name: "简历与 JD 匹配分析" });
  await expect(panel.getByRole("button", { name: "生成分析" })).toBeEnabled();
  await panel.getByRole("button", { name: "生成分析" }).click();

  expect(requestPayloads[0]).toEqual({
    target_position: "Agent 应用开发",
    job_description: initialJobDescription
  });
  await expect(panel.getByText("岗位匹配度较高。")).toBeVisible();
  await expect(panel.getByRole("heading", { name: "已匹配要求" })).toBeVisible();
  await expect(panel.getByText("Vue 3 前端开发")).toBeVisible();
  await expect(panel.getByRole("heading", { name: "待补足要求" })).toBeVisible();
  await expect(panel.getByText("大规模系统经验")).toBeVisible();
  await expect(panel.getByRole("heading", { name: "高风险追问" })).toBeVisible();
  await expect(panel.getByText("如何保证 RAG 质量？")).toBeVisible();
  await expect(panel.getByRole("heading", { name: "准备建议" })).toBeVisible();
  await expect(panel.getByText("准备一个量化效果案例")).toBeVisible();
  await expect(panel.getByText(/分析依据：基于当前简历与用户提供的 JD/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "刷新分析" })).toBeVisible();

  const secondJobDescription = `${initialJobDescription} 需要高并发经验。`;
  await page.getByLabel("岗位 JD").fill(secondJobDescription);
  await expect(panel.getByText("岗位匹配度较高。")).toHaveCount(0);
  await panel.getByRole("button", { name: "生成分析" }).click();
  await expect(panel.getByText(/正在结合简历和岗位要求/)).toBeVisible();

  const thirdJobDescription = `${initialJobDescription} 需要数据治理经验。`;
  await page.getByLabel("岗位 JD").fill(thirdJobDescription);
  await expect(panel.getByRole("button", { name: "生成分析" })).toBeEnabled();
  await expect(panel.getByText("这是一条已过期的分析。")).toHaveCount(0);
  await page.waitForTimeout(300);
  await expect(panel.getByText("这是一条已过期的分析。")).toHaveCount(0);

  await panel.getByRole("button", { name: "生成分析" }).click();
  await expect(panel.getByText("新 JD 暂未发现明确的匹配或缺口。")).toBeVisible();
  await expect(panel.getByText("暂未识别到明确匹配项。")).toBeVisible();
  await expect(panel.getByText("暂未识别到明显能力缺口。")).toBeVisible();
  await expect(panel.getByText("暂未识别到高风险追问。")).toBeVisible();
  await expect(panel.getByText("暂无额外准备建议。")).toBeVisible();

  await page
    .locator(".stepper")
    .getByRole("button", { name: /基础信息/ })
    .click();
  await page.getByRole("button", { name: /Agent 应用开发/ }).click();
  await page.getByRole("option", { name: /后端开发/ }).click();
  await goForwardToJobDescriptionStep(page);
  await expect(panel.getByText("新 JD 暂未发现明确的匹配或缺口。")).toHaveCount(0);

  await panel.getByRole("button", { name: "生成分析" }).click();
  await expect(panel.getByRole("button", { name: "刷新分析" })).toBeVisible();
  await page
    .locator(".stepper")
    .getByRole("button", { name: /简历与岗位/ })
    .click();
  await page.getByRole("button", { name: "重新选择" }).click();
  await page.getByRole("menuitem", { name: /复用已有简历/ }).click();
  const secondResume = page.locator(".resume-history-row").filter({ hasText: "candidate-v2.docx" });
  await secondResume.getByRole("button", { name: "选择", exact: true }).click();
  await goForwardToJobDescriptionStep(page);
  await expect(panel.getByText("新 JD 暂未发现明确的匹配或缺口。")).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "生成分析" })).toBeEnabled();
});

test("shows parse and API errors without blocking interview creation", async ({ page }) => {
  await seedDraft(page, "failed");
  await page.route("**/api/resumes", async (route) => {
    await route.fulfill({ json: [resumeListItem(302, "parsed-resume.docx")] });
  });
  await page.route("**/api/resumes/302/job-match-analysis", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "BUSINESS_ERROR", message: "匹配分析服务暂时不可用。", details: null }
      })
    });
  });
  await page.goto("/interviews/new");
  await goToJobDescriptionStep(page);

  const panel = page.getByRole("region", { name: "简历与 JD 匹配分析" });
  await expect(panel.getByRole("button", { name: "生成分析" })).toBeDisabled();
  await expect(panel.getByText("所选简历解析失败，请重新上传或选择其他简历。")).toBeVisible();

  await page
    .locator(".stepper")
    .getByRole("button", { name: /简历与岗位/ })
    .click();
  await page.getByRole("button", { name: "重新选择" }).click();
  await page.getByRole("menuitem", { name: /复用已有简历/ }).click();
  await page
    .locator(".resume-history-row")
    .filter({ hasText: "parsed-resume.docx" })
    .getByRole("button", { name: "选择", exact: true })
    .click();
  await goForwardToJobDescriptionStep(page);

  const readyPanel = page.getByRole("region", { name: "简历与 JD 匹配分析" });
  await readyPanel.getByRole("button", { name: "生成分析" }).click();
  await expect(readyPanel.getByRole("alert")).toContainText("匹配分析服务暂时不可用。");
  await page.getByRole("button", { name: "下一步" }).click();
  await expect(page.getByRole("button", { name: "开始面试" })).toBeEnabled();
});

async function seedDraft(page: Page, parseStatus: string) {
  await page.addInitScript(
    ({ jobDescription, resumeParseStatus }) => {
      window.localStorage.setItem(
        "interview_arena_create_draft:1",
        JSON.stringify({
          targetPosition: "Agent 应用开发",
          customPosition: "",
          isCustomInputMode: false,
          selectedRounds: ["resume", "technical", "manager", "hr"],
          interviewGoal: "campus",
          jobDescription,
          resumeId: 301,
          resumeName: "candidate.docx",
          resumeParseStatus
        })
      );
    },
    { jobDescription: initialJobDescription, resumeParseStatus: parseStatus }
  );
}

async function goToJobDescriptionStep(page: Page) {
  await page.getByRole("button", { name: "下一步" }).click();
  await page.getByRole("button", { name: "下一步" }).click();
  await page.getByRole("button", { name: "下一步" }).click();
}

async function goForwardToJobDescriptionStep(page: Page) {
  while (await page.getByLabel("岗位 JD").isHidden()) {
    await page.getByRole("button", { name: "下一步" }).click();
  }
}

function completeAnalysis(summary: string) {
  return {
    resume_id: 301,
    target_position: "Agent 应用开发",
    summary,
    matched_requirements: [{ requirement: "Vue 3 前端开发", evidence: "简历包含 Vue 项目经历。" }],
    missing_requirements: [{ requirement: "大规模系统经验", evidence_gap: "简历未提供相关证据。" }],
    risk_questions: [{ question: "如何保证 RAG 质量？", related_requirement: "RAG 工程能力" }],
    preparation_suggestions: [
      { suggestion: "准备一个量化效果案例", related_requirement: "结果量化能力" }
    ],
    analysis_basis: "基于当前简历与用户提供的 JD，仅供面试准备参考。"
  };
}

function emptyAnalysis(summary: string) {
  return {
    resume_id: 301,
    target_position: "Agent 应用开发",
    summary,
    matched_requirements: [],
    missing_requirements: [],
    risk_questions: [],
    preparation_suggestions: [],
    analysis_basis: "基于当前简历与用户提供的 JD，仅供面试准备参考。"
  };
}

function resumeListItem(id: number, name: string) {
  return {
    id,
    name,
    uploaded_at: "2026-07-20T08:00:00Z",
    last_used_at: null,
    parse_status: "parsed",
    is_default: id === 301
  };
}
