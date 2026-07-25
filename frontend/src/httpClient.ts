import { clearAuth } from "./auth";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 15000;
const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || "interview_arena_csrf";
const CSRF_HEADER_NAME = import.meta.env.VITE_CSRF_HEADER_NAME || "X-CSRF-Token";

export const AUTH_EXPIRED_EVENT = "interview-arena:auth-expired";

export type RequestOptions = {
  method?: string;
  body?: BodyInit | Record<string, unknown>;
  headers?: HeadersInit;
  timeoutMs?: number;
  statusMessages?: Record<number, string>;
};

export const ERROR_MESSAGES: Record<string, string> = {
  VALIDATION_ERROR: "请求参数不正确。",
  UNAUTHORIZED: "请先登录。",
  FORBIDDEN: "没有权限访问该资源。",
  NOT_FOUND: "资源不存在。",
  CONFLICT: "资源已存在。",
  INVALID_UPLOAD_TYPE: "上传格式不支持，需要重新上传哦。",
  RESUME_PARSE_FAILED: "简历解析失败，请重新上传。",
  LLM_API_KEY_MISSING: "需要配置好API Key噢。",
  NETWORK_TIMEOUT: "当前网络环境不好，请稍后重试。",
  TOO_MANY_REQUESTS: "请求过于频繁，请稍后再试。",
  BUSINESS_ERROR: "业务处理失败。",
  INTERNAL_ERROR: "服务器开小差了，请稍后重试。",
  MISSING_RESUME: "需要先上传简历哦"
};

export class ApiError extends Error {
  code?: string;
  status?: number;
  details?: unknown;

  constructor(message: string, code?: string, status?: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  let body = options.body;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    options.timeoutMs || REQUEST_TIMEOUT_MS
  );

  if (body && !(body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }
  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && !headers.has(CSRF_HEADER_NAME)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body as BodyInit | undefined,
      credentials: "include",
      signal: controller.signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(ERROR_MESSAGES.NETWORK_TIMEOUT, "NETWORK_TIMEOUT");
    }
    throw new ApiError("无法连接后端服务，请确认服务已启动后再重试。", "NETWORK_ERROR");
  } finally {
    window.clearTimeout(timeoutId);
  }

  const data = await readJson(response, options.statusMessages);
  if (!response.ok) {
    const errorBody = normalizeErrorBody(data);
    const code = errorBody.code;
    const message =
      errorBody.message ||
      (code ? ERROR_MESSAGES[code] : undefined) ||
      statusMessage(response.status, options.statusMessages);

    if (response.status === 401) {
      clearAuth();
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }

    throw new ApiError(message, code, response.status, errorBody.details);
  }

  return data as T;
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

async function readJson(
  response: Response,
  customStatusMessages?: Record<number, string>
): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  const contentType = response.headers.get("Content-Type") || "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) {
      return { error: { message: statusMessage(response.status, customStatusMessages) } };
    }
    throw new ApiError("响应格式异常，请稍后重试。", "INVALID_RESPONSE", response.status);
  }

  try {
    return JSON.parse(text);
  } catch {
    if (!response.ok) {
      return { error: { message: statusMessage(response.status, customStatusMessages) } };
    }
    throw new ApiError("响应解析失败，请稍后重试。", "INVALID_RESPONSE", response.status);
  }
}

function normalizeErrorBody(data: unknown): { code?: string; message: string; details?: unknown } {
  if (!data || typeof data !== "object") {
    return { message: "" };
  }

  if ("error" in data && data.error && typeof data.error === "object") {
    const error = data.error as { code?: unknown; message?: unknown; details?: unknown };
    return {
      code: typeof error.code === "string" ? error.code : undefined,
      message: typeof error.message === "string" ? error.message : "",
      details: error.details
    };
  }

  if ("detail" in data && typeof data.detail === "string") {
    return { message: data.detail };
  }

  if ("detail" in data && Array.isArray(data.detail)) {
    return {
      code: "VALIDATION_ERROR",
      message: ERROR_MESSAGES.VALIDATION_ERROR,
      details: data.detail
    };
  }

  return { message: "" };
}

function statusMessage(status: number, customMessages?: Record<number, string>): string {
  if (customMessages?.[status]) {
    return customMessages[status];
  }
  const messages: Record<number, string> = {
    400: "请求参数不正确。",
    401: "登录已失效，请重新登录。",
    403: "没有权限访问该资源。",
    404: "资源不存在。",
    409: "资源已存在。",
    422: "请求参数不正确。",
    429: "请求过于频繁，请稍后再试。",
    500: "服务器开小差了，请稍后重试。",
    502: "后端服务暂时不可用，请稍后重试。",
    503: "后端服务暂时不可用，请稍后重试。",
    504: "请求超时，请稍后重试。"
  };
  return messages[status] || "请求失败，请稍后重试。";
}
