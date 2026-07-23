import { clearAuth } from "./auth";
import { ApiError, AUTH_EXPIRED_EVENT } from "./api";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 120000;
const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || "interview_arena_csrf";
const CSRF_HEADER_NAME = import.meta.env.VITE_CSRF_HEADER_NAME || "X-CSRF-Token";

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
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers = new Headers({ "Content-Type": "application/json" });
  const csrfToken = readCookie(CSRF_COOKIE_NAME);
  if (csrfToken) {
    headers.set(CSRF_HEADER_NAME, csrfToken);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/resumes/${resumeId}/job-match-analysis`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      credentials: "include",
      signal: controller.signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("匹配分析请求超时，请稍后重试。", "NETWORK_TIMEOUT");
    }
    throw new ApiError("无法连接后端服务，请确认服务已启动后再重试。", "NETWORK_ERROR");
  } finally {
    window.clearTimeout(timeoutId);
  }

  const data = await readJson(response);
  if (!response.ok) {
    const errorBody = normalizeErrorBody(data);
    if (response.status === 401) {
      clearAuth();
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(
      errorBody.message || statusMessage(response.status),
      errorBody.code,
      response.status,
      errorBody.details
    );
  }

  return data as JobMatchAnalysis;
}

function readCookie(name: string): string {
  const encodedName = `${encodeURIComponent(name)}=`;
  return (
    document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith(encodedName))
      ?.slice(encodedName.length) || ""
  );
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) {
      return null;
    }
    throw new ApiError("响应格式异常，请稍后重试。", "INVALID_RESPONSE", response.status);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("响应解析失败，请稍后重试。", "INVALID_RESPONSE", response.status);
  }
}

function normalizeErrorBody(data: unknown): { code?: string; message?: string; details?: unknown } {
  if (!data || typeof data !== "object") {
    return {};
  }
  if ("error" in data && data.error && typeof data.error === "object") {
    const error = data.error as { code?: unknown; message?: unknown; details?: unknown };
    return {
      code: typeof error.code === "string" ? error.code : undefined,
      message: typeof error.message === "string" ? error.message : undefined,
      details: error.details
    };
  }
  if ("detail" in data && typeof data.detail === "string") {
    return { message: data.detail };
  }
  return {};
}

function statusMessage(status: number): string {
  const messages: Record<number, string> = {
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
  return messages[status] || "匹配分析失败，请稍后重试。";
}
