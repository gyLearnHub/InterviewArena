import { request } from "./httpClient";

const REQUEST_TIMEOUT_MS = 120000;
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

export async function analyzeResumeJobMatch(
  resumeId: number,
  payload: JobMatchAnalysisRequest
): Promise<JobMatchAnalysis> {
  return request<JobMatchAnalysis>(`/resumes/${resumeId}/job-match-analysis`, {
    method: "POST",
    body: payload,
    timeoutMs: REQUEST_TIMEOUT_MS,
    statusMessages: JOB_MATCH_STATUS_MESSAGES
  });
}
