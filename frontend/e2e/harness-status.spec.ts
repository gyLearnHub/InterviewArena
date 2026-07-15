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
  await page.route("**/api/harness/evolution/status", async (route) => {
    await route.fulfill({
      json: {
        enabled: true,
        trigger_interviews: 10,
        synthetic_samples: 5,
        observation_interviews: 3,
        families: [],
        runs: []
      }
    });
  });
  await page.route("**/api/interviews/*/rounds/*/questions/*/draft", async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204 });
      return;
    }
    await route.fulfill({ json: { question_id: 0, answer: "", updated_at: null } });
  });
});

test("workspace exposes independent harness status page with backend harness records", async ({
  page
}) => {
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 1,
        report_count: 0,
        personalized_feedback_used: false,
        latest_interview: {
          interview_id: 77,
          target_position: "后端工程师",
          status: "in_progress",
          score: null,
          started_at: "2026-06-22T10:00:00",
          ended_at: null
        },
        latest_report: null,
        score_trend: [],
        score_delta: null,
        abilities: [],
        weak_points: []
      }
    });
  });
  await page.route("**/api/interviews/history/page?*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            interview_id: 77,
            target_position: "后端工程师",
            status: "in_progress",
            score: null,
            created_at: "2026-06-22T09:55:00",
            updated_at: "2026-06-22T10:06:00",
            started_at: "2026-06-22T10:00:00",
            ended_at: null
          },
          {
            interview_id: 78,
            target_position: "前端工程师",
            status: "finished",
            score: null,
            created_at: "2026-06-21T09:55:00",
            updated_at: "2026-06-21T11:05:00",
            started_at: "2026-06-21T10:00:00",
            ended_at: "2026-06-21T11:00:00"
          }
        ],
        next_offset: null
      }
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
        evaluations: [
          {
            id: 11,
            interview_id: 77,
            trace_id: 1,
            rule_name: "context_isolation",
            status: "passed",
            severity: "high",
            evidence: {},
            failure_reason: null,
            overall_grade: "PASS",
            created_at: "2026-06-22T10:05:01"
          }
        ],
        checkpoints: [
          {
            id: 21,
            interview_id: 77,
            round_id: 701,
            trace_id: 1,
            node_id: "technical-question-1",
            checkpoint_type: "question_generated",
            status: "available",
            snapshot: {},
            resume_version: null,
            created_at: "2026-06-22T10:05:02"
          }
        ]
      }
    });
  });
  await page.route("**/api/interviews/78/harness", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 78,
        harness_status: "completed",
        recovery_count: 0,
        had_degradation: false,
        traces: [
          {
            id: 2,
            interview_id: 78,
            round_id: 702,
            node_id: "frontend-final-review",
            node_type: "final_evaluation",
            agent_type: "manager",
            purpose: "final review",
            status: "completed",
            validation_status: "passed",
            retry_records: [],
            degradation_records: [],
            elapsed_ms: 980,
            execution_mode: "normal",
            created_at: "2026-06-21T11:01:00",
            updated_at: "2026-06-21T11:05:00"
          }
        ],
        evaluations: [
          {
            id: 12,
            interview_id: 78,
            trace_id: 2,
            rule_name: "score_evidence",
            status: "passed",
            severity: "high",
            evidence: {},
            failure_reason: null,
            overall_grade: "PASS",
            created_at: "2026-06-21T11:05:01"
          }
        ],
        checkpoints: []
      }
    });
  });

  await page.goto("/dashboard");
  await page.locator(".account-card").click();
  await page.getByRole("menuitem", { name: "高级诊断" }).click();

  await expect(page).toHaveURL(/\/harness$/);
  await expect(page.getByRole("main").getByRole("heading", { name: "高级诊断" })).toBeVisible();
  await expect(page.getByText("备用流程").first()).toBeVisible();
  await expect(page.getByText("1 / 1")).toBeVisible();
  await expect(page.getByText("technical-question-1").first()).toBeVisible();
  await expect(page.getByText("问题生成")).toBeVisible();
  await expect(page.locator("time[datetime='2026-06-22T10:06:00']")).toBeVisible();
  await expect(page.getByText("2 场面试记录")).toBeVisible();
  await page.getByRole("button", { name: "查看健康详情" }).click();
  await expect(page).toHaveURL(/\/harness$/);
  await expect(page.getByLabel("健康详情").getByText("Trace 总数")).toBeVisible();
  await expect(page.getByRole("button", { name: "收起健康详情" })).toBeVisible();
  await page.getByLabel("切换记录").selectOption("78");
  await expect(page.getByText("frontend-final-review").first()).toBeVisible();
  await expect(page.locator("time[datetime='2026-06-21T11:05:00']")).toBeVisible();
  await expect(page.getByText(/raw internal error/)).toHaveCount(0);
});

test("multi-round interview shows recoverable flow status without internal details", async ({
  page
}) => {
  await page.route("**/api/interviews/77/state", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 77,
        mode: "multi_round",
        overall_status: "in_progress",
        target_position: "后端工程师",
        job_description: null,
        current_round: "technical",
        elapsed_seconds: 60,
        harness_status: "paused",
        recovery_count: 1,
        had_degradation: true,
        last_harness_error: "raw internal error should stay hidden",
        rounds: [
          {
            id: 701,
            round_type: "technical",
            status: "in_progress",
            score: null,
            result: null
          }
        ],
        current_question: {
          id: 9001,
          round_id: 701,
          sequence: 1,
          question_kind: "main",
          parent_question_id: null,
          question_type: "technical",
          question: "请介绍一次你优化接口性能的经历。"
        },
        qa_history: []
      }
    });
  });

  await page.goto("/interviews/multi/77");

  await expect(page.getByText("面试已暂停")).toBeVisible();
  await expect(page.getByText("正在保存恢复点，请稍后重新检查后继续。")).toBeVisible();
  await expect(page.getByText(/raw internal error/)).toHaveCount(0);
});

test("harness status does not render fallback rows when backend has no records", async ({
  page
}) => {
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
  await page.route("**/api/interviews/history/page?*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            interview_id: 91,
            target_position: "后端工程师",
            status: "in_progress",
            overall_status: "in_progress",
            created_at: "2026-06-24T09:00:00",
            updated_at: "2026-06-24T09:20:00",
            started_at: "2026-06-24T09:10:00",
            ended_at: null
          }
        ],
        next_offset: null
      }
    });
  });
  await page.route("**/api/interviews/91/harness", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 91,
        harness_status: "running",
        recovery_count: 0,
        had_degradation: false,
        traces: [],
        evaluations: [],
        checkpoints: []
      }
    });
  });

  await page.goto("/harness");

  await expect(page.getByText("系统暂无这场面试的运行明细。")).toBeVisible();
  await expect(page.getByText("状态同步")).toHaveCount(0);
  await expect(page.getByText("轮次记录")).toHaveCount(0);
  await expect(page.getByText("问答记录")).toHaveCount(0);
  await expect(page.locator(".donut strong")).toHaveText("0");
});

test("multi-round review keeps future rounds locked and current round actionable", async ({
  page
}) => {
  await page.route("**/api/interviews/88/state", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 88,
        mode: "multi_round",
        overall_status: "in_progress",
        target_position: "后端工程师",
        job_description: null,
        current_round: "technical",
        elapsed_seconds: 180,
        harness_status: "running",
        recovery_count: 0,
        had_degradation: false,
        rounds: [
          {
            id: 801,
            round_type: "resume",
            status: "completed",
            score: 82,
            result: "passed",
            elapsed_seconds: 120
          },
          {
            id: 802,
            round_type: "technical",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 60
          },
          {
            id: 803,
            round_type: "manager",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          },
          {
            id: 804,
            round_type: "hr",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          }
        ],
        current_question: {
          id: 9901,
          round_id: 802,
          sequence: 1,
          question_kind: "main",
          parent_question_id: null,
          question_type: "technical",
          question: "请介绍一次你优化接口性能的经历。"
        },
        qa_history: [
          {
            id: 9801,
            round_id: 801,
            round_type: "resume",
            sequence: 1,
            question_kind: "main",
            parent_question_id: null,
            question_type: "resume",
            question: "请介绍你的项目经历。",
            answer: "我负责过多轮面试系统的后端编排。"
          }
        ]
      }
    });
  });

  await page.goto("/interviews/multi/88");

  const resumeCard = page.locator(".round-card").filter({ hasText: "简历面" });
  const technicalCard = page.locator(".round-card").filter({ hasText: "技术面" });
  const managerCard = page.locator(".round-card").filter({ hasText: "主管面" });

  await expect(technicalCard).toHaveClass(/is-active-view/);
  await expect(managerCard).toHaveAttribute("aria-disabled", "true");

  await managerCard.dispatchEvent("click");
  await expect(technicalCard).toHaveClass(/is-active-view/);

  await expect(resumeCard).toHaveAttribute("aria-disabled", "false");
  await resumeCard.click();

  await expect(resumeCard).toHaveClass(/is-active-view/);
  await expect(page.getByText("技术面进行中")).toBeVisible();
  await expect(page.getByRole("button", { name: "结束当前轮" })).toBeEnabled();
});

test("multi-round review can return to the next startable round", async ({ page }) => {
  await page.route("**/api/interviews/89/state", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 89,
        mode: "multi_round",
        overall_status: "in_progress",
        target_position: "后端工程师",
        job_description: null,
        current_round: null,
        elapsed_seconds: 120,
        harness_status: "running",
        recovery_count: 0,
        had_degradation: false,
        rounds: [
          {
            id: 891,
            round_type: "resume",
            status: "completed",
            score: 82,
            result: "passed",
            elapsed_seconds: 120
          },
          {
            id: 892,
            round_type: "technical",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          },
          {
            id: 893,
            round_type: "manager",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          },
          {
            id: 894,
            round_type: "hr",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          }
        ],
        current_question: null,
        qa_history: [
          {
            id: 8801,
            round_id: 891,
            round_type: "resume",
            sequence: 1,
            question_kind: "main",
            parent_question_id: null,
            question_type: "resume",
            question: "请介绍你的项目经历。",
            answer: "我负责过多轮面试系统的后端编排。"
          }
        ]
      }
    });
  });

  await page.goto("/interviews/multi/89");

  const resumeCard = page.locator(".round-card").filter({ hasText: "简历面" });
  const technicalCard = page.locator(".round-card").filter({ hasText: "技术面" });

  await expect(technicalCard).toHaveClass(/is-active-view/);
  await resumeCard.click();
  await expect(resumeCard).toHaveClass(/is-active-view/);

  await expect(technicalCard).toHaveAttribute("aria-disabled", "false");
  await technicalCard.click();
  await expect(technicalCard).toHaveClass(/is-active-view/);
  await page.getByLabel("打开面试操作菜单").click();
  await expect(page.getByRole("button", { name: "开始本轮" })).toBeEnabled();
});

test("exit interview does not show next-question thinking state", async ({ page }) => {
  await page.addInitScript(() => {
    window.confirm = () => true;
  });
  await page.route("**/api/interviews/90/state", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 90,
        mode: "multi_round",
        overall_status: "in_progress",
        target_position: "后端工程师",
        job_description: null,
        current_round: "technical",
        elapsed_seconds: 180,
        harness_status: "running",
        recovery_count: 0,
        had_degradation: false,
        rounds: [
          {
            id: 901,
            round_type: "resume",
            status: "completed",
            score: 82,
            result: "passed",
            elapsed_seconds: 120
          },
          {
            id: 902,
            round_type: "technical",
            status: "in_progress",
            score: null,
            result: null,
            elapsed_seconds: 60
          },
          {
            id: 903,
            round_type: "manager",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          },
          {
            id: 904,
            round_type: "hr",
            status: "pending",
            score: null,
            result: null,
            elapsed_seconds: 0
          }
        ],
        current_question: {
          id: 9902,
          round_id: 902,
          sequence: 1,
          question_kind: "main",
          parent_question_id: null,
          question_type: "technical",
          question: "请介绍一次你优化接口性能的经历。"
        },
        qa_history: []
      }
    });
  });
  await page.route("**/api/interviews/90/finish-task", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({
      json: {
        task_id: 900,
        status: "completed",
        result: {
          interview_id: 90,
          score: 0,
          weaknesses: ["面试提前结束。"],
          suggestions: ["后续补充完整面试。"],
          recommendation: "暂缓决定",
          round_scores: [],
          strengths: [],
          reference_note: "面试提前结束，评价仅供参考。",
          report_reliability_status: "reference_only"
        }
      }
    });
  });
  await page.route("**/api/interviews/90", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 90,
        target_position: "后端工程师",
        status: "finished",
        mode: "multi_round",
        overall_status: "finished",
        rounds: [],
        qa_history: [],
        resume: { id: 1, created_at: "2026-06-01T09:00:00", structured_data: {} },
        feedback_report: null,
        started_at: "2026-06-01T10:00:00",
        ended_at: "2026-06-01T11:00:00"
      }
    });
  });

  await page.goto("/interviews/multi/90");
  await page.getByLabel("打开面试操作菜单").click();
  await page.getByRole("button", { name: "退出面试" }).click();

  await expect(page.getByText("面试官正在思考")).toHaveCount(0);
  await expect(page.getByText("正在整理下一问题")).toHaveCount(0);
});

test("reports and history show reliability labels", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("interview_arena_history_view", "list");
  });
  await page.route("**/api/dashboard/summary", async (route) => {
    await route.fulfill({
      json: {
        interview_count: 2,
        report_count: 1,
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
  await page.route("**/api/interviews/history/page?*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            interview_id: 77,
            target_position: "后端工程师",
            status: "finished",
            score: 72,
            started_at: "2026-06-01T10:00:00",
            ended_at: "2026-06-01T11:00:00",
            report_reliability_status: "reference_only"
          },
          {
            interview_id: 78,
            target_position: "前端工程师",
            status: "finished",
            score: null,
            started_at: "2026-06-02T10:00:00",
            ended_at: "2026-06-02T11:00:00",
            report_reliability_status: "unavailable"
          }
        ],
        next_offset: null
      }
    });
  });
  await page.route("**/api/interviews/77", async (route) => {
    await route.fulfill({
      json: {
        interview_id: 77,
        target_position: "后端工程师",
        status: "finished",
        mode: "multi_round",
        overall_status: "finished",
        rounds: [],
        qa_history: [],
        resume: { id: 1, created_at: "2026-06-01T09:00:00", structured_data: {} },
        feedback_report: {
          score: 72,
          weaknesses: ["需要补充压测证据"],
          suggestions: ["复盘关键指标"],
          recommendation: "谨慎录用",
          report_reliability_status: "reference_only",
          reference_note: "部分结果受备用流程影响。"
        },
        started_at: "2026-06-01T10:00:00",
        ended_at: "2026-06-01T11:00:00"
      }
    });
  });

  await page.goto("/history");
  await expect(page.getByText("仅供参考")).toBeVisible();
  await expect(page.getByText("报告不可用")).toBeVisible();

  await page.goto("/reports/77");
  await expect(page.getByRole("heading", { name: "面试复盘" })).toBeVisible();
  await expect(page.getByText("代码筑基，系统赋能，创造无限可能")).toHaveCount(0);
  await expect(page.locator(".overview-art")).toHaveCount(0);
  await expect(page.locator(".score-summary")).toContainText("72");
  await expect(page.getByText("报告仅供参考")).toBeVisible();
  await expect(page.getByText("部分结果受备用流程影响。")).toBeVisible();
});
