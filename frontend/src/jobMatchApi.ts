import { ApiError, request } from "./httpClient";

const ENQUEUE_TIMEOUT_MS = 15000;
const POLL_TIMEOUT_MS = 20 * 60 * 1000;
const JOB_MATCH_STATUS_MESSAGES: Record<number, string> = {
  400: "请求参数不正确。",
  401: "登录已失效，请重新登录。",
  403: "没有权限访问该资源。",
  404: "所选简历不存在，请重新选择。",
  409: "所选简历尚未解析成功，暂时无法生成匹配分析。",
  422: "岗位或 JD 内容不符合要求。",
  429: "请求过于频繁，请稍后再试。",
  500: "服务器开小差了，请稍后重试。",
  502: "后端服务暂时不可用，请稍后重试。",
  503: "后端服务暂时不可用，请稍后重试。",
  504: "匹配分析请求超时，请稍后重试。"
};

export type MatchedRequirement = {
  requirement: string;
  evidence: string;
};

export type MissingRequirement = {
  requirement: string;
  evidence_gap: string;
};

export type RiskQuestion = {
  question: string;
  related_requirement: string;
};

export type PreparationSuggestion = {
  suggestion: string;
  related_requirement: string;
};

export type JobMatchAnalysis = {
  resume_id: number;
  target_position: string;
  summary: string;
  matched_requirements: MatchedRequirement[];
  missing_requirements: MissingRequirement[];
  risk_questions: RiskQuestion[];
  preparation_suggestions: PreparationSuggestion[];
  analysis_basis: string;
};

export type JobMatchAnalysisRequest = {
  target_position: string;
  job_description: string;
};

export type JobMatchAnalysisTask = {
  task_id: number;
  status: "pending" | "processing" | "completed" | "failed";
  result: JobMatchAnalysis | null;
  error_code: string | null;
  error_message: string | null;
};

export async function analyzeResumeJobMatch(
  resumeId: number,
  payload: JobMatchAnalysisRequest
): Promise<JobMatchAnalysis> {
  let task = await request<JobMatchAnalysisTask>(`/resumes/${resumeId}/job-match-analysis`, {
    method: "POST",
    body: payload,
    timeoutMs: ENQUEUE_TIMEOUT_MS,
    statusMessages: JOB_MATCH_STATUS_MESSAGES
  });
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let delayMs = 1200;
  while (task.status === "pending" || task.status === "processing") {
    if (Date.now() >= deadline) {
      throw new ApiError("匹配分析等待超时，请稍后重试。", "NETWORK_TIMEOUT");
    }
    await delay(delayMs);
    task = await request<JobMatchAnalysisTask>(`/resumes/job-match-tasks/${task.task_id}`, {
      timeoutMs: ENQUEUE_TIMEOUT_MS,
      statusMessages: JOB_MATCH_STATUS_MESSAGES
    });
    delayMs = Math.min(5000, Math.round(delayMs * 1.5));
  }
  if (task.status === "completed" && task.result) {
    return task.result;
  }
  throw new ApiError(
    task.error_message || "匹配分析失败，请稍后重试。",
    task.error_code || "BUSINESS_ERROR"
  );
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
