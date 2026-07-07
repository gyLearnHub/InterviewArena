import { clearAuth, saveAuth } from "./auth";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 15000;
const RESUME_UPLOAD_TIMEOUT_MS = 220000;
const RESUME_PARSE_POLL_INTERVAL_MS = 1500;
const INTERVIEW_OPERATION_TIMEOUT_MS = 260000;
const INTERVIEW_OPERATION_POLL_INTERVAL_MS = 1200;
const CSRF_COOKIE_NAME = "interview_arena_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";
export const AUTH_EXPIRED_EVENT = "interview-arena:auth-expired";

export type LoginResponse = {
  id: number;
  username: string;
  display_name: string;
  avatar_url?: string | null;
};

export type UserProfile = {
  id: number;
  username: string;
  display_name: string;
  avatar_url?: string | null;
};

export type ResumeUploadResponse = {
  id: number;
  structured_data: Record<string, unknown>;
};

export type ResumeParseTaskResponse = {
  task_id: number;
  status: "pending" | "processing" | "completed" | "failed" | string;
  resume_id?: number | null;
  structured_data?: Record<string, unknown> | null;
  error_message?: string | null;
};

export type InterviewOperationTaskResponse<T = unknown> = {
  task_id: number;
  operation: string;
  status: "pending" | "processing" | "completed" | "failed" | string;
  interview_id: number;
  round_id?: number | null;
  result?: T | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type ResumeListItem = {
  id: number;
  name: string;
  uploaded_at: string;
  last_used_at: string | null;
  parse_status: string;
  is_default: boolean;
};

export type ResumeDetail = ResumeListItem & {
  structured_data: Record<string, unknown>;
};

export type InterviewCreateResponse = {
  id: number;
  status: string;
  mode?: "multi_round";
  rounds?: InterviewRound[];
  harness_status?: HarnessStatus | null;
  recovery_count?: number;
  had_degradation?: boolean;
  last_harness_error?: string | null;
};

export type FeedbackReport = {
  interview_id: number;
  score: number;
  weaknesses: string[];
  suggestions: string[];
  recommendation?: string;
  round_scores?: RoundScore[];
  strengths?: string[];
  reference_note?: string | null;
  ability_analysis?: string[];
  job_match?: string | null;
  final_conclusion?: string | null;
  confidence?: "high" | "medium" | "low";
  used_candidate_memory?: boolean;
  report_reliability_status?: ReportReliabilityStatus;
  detailed_feedback?: DetailedFeedback | null;
};

export type ProblemDiagnosis = {
  title: string;
  severity: "high" | "medium" | "low" | string;
  evidence: string[];
  impact: string;
  suggestion: string;
};

export type RoundReview = {
  round_type: RoundType | string;
  status?: string | null;
  score?: number | null;
  result?: string | null;
  strengths: string[];
  issues: string[];
  evidence: string[];
  suggestions: string[];
  answered_question_count?: number;
  evaluated_question_count?: number;
  is_reference_only?: boolean;
};

export type ActionPlan = {
  title: string;
  priority: "high" | "medium" | "low" | string;
  steps: string[];
  expected_outcome?: string | null;
};

export type DetailedFeedback = {
  problem_diagnosis: ProblemDiagnosis[];
  round_reviews: RoundReview[];
  action_plan: ActionPlan[];
  follow_up_questions: string[];
};

export type UserPreferences = {
  memory_enabled: boolean;
  memory_updated_at?: string | null;
};

export type MemoryClearStatus = {
  task_id?: number | null;
  status: "idle" | "pending" | "processing" | "completed" | "failed" | "retry_wait" | string;
  deleted_count?: number;
  error_message?: string | null;
};

export type NotificationFilter = "all" | "unread";

export type NotificationTarget = {
  exists: boolean | null;
  path: string | null;
  message: string | null;
};

export type NotificationItem = {
  id: number;
  title: string;
  summary: string;
  notification_type: string;
  is_read: boolean;
  related_type?: string | null;
  related_id?: number | null;
  interview_id?: number | null;
  round_id?: number | null;
  question_id?: number | null;
  created_at: string;
};

export type NotificationDetail = NotificationItem & {
  content: string;
  target: NotificationTarget;
};

export type NotificationListResponse = {
  items: NotificationItem[];
  next_cursor: string | null;
  unread_count: number;
};

export type NotificationUnreadCountResponse = {
  count: number;
};

export type HistoryItem = {
  interview_id: number;
  target_position: string;
  status: string;
  overall_status?: string | null;
  report_reliability_status?: ReportReliabilityStatus;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  ended_at: string | null;
};

export type ReportListItem = {
  interview_id: number;
  target_position: string;
  score: number;
  report_reliability_status: ReportReliabilityStatus;
  created_at: string | null;
  used_candidate_memory: boolean;
};

export type HistoryListResponse = {
  items: HistoryItem[];
  next_offset: number | null;
};

export type ReportListResponse = {
  items: ReportListItem[];
  next_offset: number | null;
};

export type ReportRoundScoreSource = {
  round_type: RoundType;
  status: string;
  score: number | null;
  source: "final_report" | "round_summary" | "none" | string;
  answered_question_count: number;
  evaluated_question_count: number;
  is_reference_only: boolean;
};

export type ReportQualitySummary = {
  completed_round_count: number;
  selected_round_count: number;
  answered_question_count: number;
  evaluated_question_count: number;
  score_coverage_percent: number;
  reliability_reasons: string[];
  score_sources: ReportRoundScoreSource[];
};

export type HistoryDetail = {
  interview_id: number;
  target_position: string;
  status: string;
  mode?: "multi_round";
  job_description?: string | null;
  overall_status?: string;
  rounds?: InterviewRound[];
  qa_history?: MultiRoundQaEntry[];
  report_quality?: ReportQualitySummary;
  resume: {
    id: number;
    created_at: string;
    structured_data: Record<string, unknown>;
  };
  feedback_report: Omit<FeedbackReport, "interview_id"> | null;
  started_at: string | null;
  ended_at: string | null;
  harness_status?: HarnessStatus | null;
  recovery_count?: number;
  had_degradation?: boolean;
  last_harness_error?: string | null;
};

export type DashboardInterviewSummary = {
  interview_id: number;
  target_position: string;
  status: string;
  score: number | null;
  started_at: string | null;
  ended_at: string | null;
};

export type DashboardReportSummary = {
  interview_id: number;
  target_position: string;
  score: number;
  created_at: string | null;
  used_candidate_memory: boolean;
  report_reliability_status: ReportReliabilityStatus;
};

export type DashboardScoreTrendPoint = {
  interview_id: number;
  score: number;
  created_at: string | null;
};

export type DashboardAbilitySummary = {
  round_type: string;
  score: number | null;
  result: string | null;
  status: string | null;
  is_reference_only: boolean;
};

export type DashboardWeakPointSummary = {
  title: string;
  summary?: string;
  suggestion: string | null;
  severity?: "high" | "medium" | "low" | string;
  occurrence_count?: number;
  evidence?: string[];
  sources?: DashboardWeakPointSource[];
  updated_at?: string | null;
};

export type DashboardWeakPointSource = {
  interview_id: number;
  target_position: string;
  round_type: string | null;
  score: number | null;
  occurred_at: string | null;
  evidence: string[];
};

export type DashboardSummary = {
  interview_count: number;
  report_count: number;
  personalized_feedback_used: boolean;
  memory_status?:
    | "disabled"
    | "accumulating"
    | "summarizing"
    | "ready"
    | "enabled"
    | "failed"
    | "unavailable"
    | string;
  candidate_memory_count?: number;
  latest_interview: DashboardInterviewSummary | null;
  latest_report: DashboardReportSummary | null;
  score_trend: DashboardScoreTrendPoint[];
  score_delta: number | null;
  abilities: DashboardAbilitySummary[];
  weak_points: DashboardWeakPointSummary[];
};

export type HarnessStatus =
  "pending" | "running" | "retrying" | "degraded" | "paused" | "failed" | "completed";

export type ReportReliabilityStatus = "normal" | "reference_only" | "unavailable";

export type RoundType = "resume" | "technical" | "manager" | "hr";
export type RoundStatus =
  "pending" | "in_progress" | "completed" | "finished_early" | "skipped" | "cancelled";
export type QuestionKind = "main" | "follow_up";
export type QuestionStatus = "active" | "regenerated" | "skipped";
export type RoundAnswerAction = "follow_up" | "next_question" | "finish_round";

export type RoundScore = {
  round_type: RoundType;
  score: number | null;
  result: string | null;
  is_reference_only?: boolean;
};

export type InterviewRound = {
  id: number;
  round_type: RoundType;
  status: RoundStatus;
  score?: number | null;
  result?: string | null;
  summary?: RoundSummary | null;
  is_reference_only?: boolean;
  started_at?: string | null;
  ended_at?: string | null;
  elapsed_seconds?: number;
};

export type RoundSummary = {
  score?: number;
  result?: string;
  dimension_reviews?: unknown[];
  strengths?: string[];
  main_issues?: string[];
  suggestions?: string[];
  evidence?: string[];
  is_reference_only?: boolean;
  reference_note?: string | null;
  question_evaluations?: QuestionEvaluation[];
};

export type QuestionEvaluation = {
  question_id?: number | null;
  round_id?: number | null;
  total_score?: number;
  dimension_scores?: unknown[];
  strengths?: string[];
  issues?: string[];
  evidence?: string[];
  should_follow_up?: boolean;
  follow_up_direction?: string | null;
  prompt_version?: string;
  model_name?: string;
};

export type MultiRoundQuestion = {
  id: number;
  round_id: number;
  sequence: number;
  question_kind: QuestionKind;
  question_status?: QuestionStatus;
  parent_question_id: number | null;
  regenerated_from_question_id?: number | null;
  question_type?: string;
  question: string;
};

export type MultiRoundQaEntry = {
  id?: number;
  round_id?: number | null;
  round_type?: RoundType;
  sequence?: number;
  question_kind?: QuestionKind;
  question_status?: QuestionStatus;
  parent_question_id?: number | null;
  regenerated_from_question_id?: number | null;
  question?: string;
  question_text?: string;
  prompt?: string;
  answer?: string;
  answer_text?: string;
  user_answer?: string;
  question_evaluation?: QuestionEvaluation | null;
};

export type MultiRoundState = {
  interview_id: number;
  mode: "multi_round";
  overall_status: string;
  target_position: string;
  job_description: string | null;
  current_round: RoundType | null;
  elapsed_seconds: number;
  rounds: InterviewRound[];
  current_question: MultiRoundQuestion | null;
  qa_history: MultiRoundQaEntry[];
  harness_status?: HarnessStatus | null;
  recovery_count?: number;
  had_degradation?: boolean;
  last_harness_error?: string | null;
};

export type HarnessTraceItem = {
  id: number;
  interview_id: number;
  round_id?: number | null;
  node_id: string;
  node_type: string;
  agent_type: string;
  purpose: string;
  status: string;
  validation_status: string;
  retry_records?: Record<string, unknown>[];
  degradation_records?: Record<string, unknown>[];
  error_code?: string | null;
  elapsed_ms?: number | null;
  execution_mode?: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type HarnessRuleEvaluationItem = {
  id: number;
  interview_id: number;
  trace_id?: number | null;
  rule_name: string;
  status: string;
  severity: string;
  evidence?: Record<string, unknown>;
  failure_reason?: string | null;
  overall_grade?: string | null;
  created_at?: string | null;
};

export type HarnessCheckpointItem = {
  id: number;
  interview_id: number;
  round_id?: number | null;
  trace_id?: number | null;
  node_id: string;
  checkpoint_type: string;
  status: string;
  snapshot?: Record<string, unknown>;
  resume_version?: string | null;
  created_at?: string | null;
};

export type HarnessListResponse<T> = {
  items: T[];
};

export type InterviewHarnessStatus = {
  interview_id: number;
  harness_status?: HarnessStatus | null;
  recovery_count: number;
  had_degradation: boolean;
  traces: HarnessTraceItem[];
  evaluations: HarnessRuleEvaluationItem[];
  checkpoints: HarnessCheckpointItem[];
};

export type RoundAnswerResponse = {
  action: RoundAnswerAction;
  question: MultiRoundQuestion | null;
  round_summary: RoundSummary | null;
  round?: InterviewRound;
};

type RequestOptions = {
  method?: string;
  body?: BodyInit | Record<string, unknown>;
  headers?: HeadersInit;
  timeoutMs?: number;
};

const ERROR_MESSAGES: Record<string, string> = {
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

export async function register(username: string, password: string): Promise<void> {
  await request("/auth/register", {
    method: "POST",
    body: { username, password }
  });
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const data = await request<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password }
  });
  saveAuth("", {
    id: data.id,
    username: data.username,
    display_name: data.display_name,
    avatar_url: data.avatar_url
  });
  return data;
}

export async function logoutCurrentUser(): Promise<void> {
  try {
    await request<void>("/auth/logout", {
      method: "POST"
    });
  } catch {
    // Local auth state must be cleared even if the server session is already gone.
  } finally {
    clearAuth();
  }
}

export function getCurrentUser(): Promise<UserProfile> {
  return request("/auth/me");
}

export function updateCurrentUser(displayName: string): Promise<UserProfile> {
  return request("/auth/me", {
    method: "PATCH",
    body: { display_name: displayName }
  });
}

export function uploadCurrentUserAvatar(file: File): Promise<UserProfile> {
  const data = new FormData();
  data.append("file", file);
  return request("/auth/me/avatar", {
    method: "POST",
    body: data
  });
}

export function uploadResume(file: File): Promise<ResumeUploadResponse> {
  const data = new FormData();
  data.append("file", file);
  return request<ResumeParseTaskResponse>("/resumes/upload-async", {
    method: "POST",
    body: data
  }).then((task) => waitForResumeParse(task));
}

export function listResumes(): Promise<ResumeListItem[]> {
  return request("/resumes");
}

export function getResumeDetail(resumeId: number): Promise<ResumeDetail> {
  return request(`/resumes/${resumeId}`);
}

export function getResumeParseTask(taskId: number): Promise<ResumeParseTaskResponse> {
  return request(`/resumes/upload-tasks/${taskId}`);
}

export function renameResume(resumeId: number, name: string): Promise<ResumeDetail> {
  return request(`/resumes/${resumeId}`, {
    method: "PATCH",
    body: { name }
  });
}

export function setDefaultResume(resumeId: number): Promise<ResumeDetail> {
  return request(`/resumes/${resumeId}/default`, {
    method: "POST"
  });
}

export function deleteResume(resumeId: number): Promise<void> {
  return request(`/resumes/${resumeId}`, {
    method: "DELETE"
  });
}

export function createInterview(
  resumeId: number,
  targetPosition: string,
  options: {
    jobDescription?: string;
    selectedRounds?: RoundType[];
  } = {}
): Promise<InterviewCreateResponse> {
  return request("/interviews", {
    method: "POST",
    body: {
      resume_id: resumeId,
      target_position: targetPosition,
      ...(options.jobDescription ? { job_description: options.jobDescription } : {}),
      ...(options.selectedRounds ? { selected_rounds: options.selectedRounds } : {})
    }
  });
}

export function listHistory(): Promise<HistoryItem[]> {
  return request("/interviews/history");
}

export function listHistoryPage(
  options: { limit?: number; offset?: number } = {}
): Promise<HistoryListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit || 20));
  params.set("offset", String(options.offset || 0));
  return request(`/interviews/history/page?${params.toString()}`);
}

export function listReports(): Promise<ReportListItem[]> {
  return request("/interviews/reports");
}

export function listReportsPage(
  options: { limit?: number; offset?: number } = {}
): Promise<ReportListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit || 20));
  params.set("offset", String(options.offset || 0));
  return request(`/interviews/reports/page?${params.toString()}`);
}

export function deleteHistoryItem(interviewId: number): Promise<void> {
  return request(`/interviews/history/${interviewId}`, { method: "DELETE" });
}

export function clearHistory(): Promise<void> {
  return request("/interviews/history", { method: "DELETE" });
}

export function getHistoryDetail(interviewId: number): Promise<HistoryDetail> {
  return request(`/interviews/${interviewId}`);
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request("/dashboard/summary");
}

export function getMultiRoundState(interviewId: number): Promise<MultiRoundState> {
  return request(`/interviews/${interviewId}/state`);
}

export function pauseMultiRoundInterview(interviewId: number): Promise<MultiRoundState> {
  return request(`/interviews/${interviewId}/pause`, {
    method: "POST"
  });
}

export function resumeMultiRoundInterview(interviewId: number): Promise<MultiRoundState> {
  return request(`/interviews/${interviewId}/resume`, {
    method: "POST"
  });
}

export function startInterviewRound(
  interviewId: number,
  roundId: number
): Promise<RoundAnswerResponse | MultiRoundState> {
  return request<InterviewOperationTaskResponse<RoundAnswerResponse>>(
    `/interviews/${interviewId}/rounds/${roundId}/start-task`,
    { method: "POST" }
  ).then((task) => waitForInterviewOperation(task));
}

export function submitRoundAnswer(
  interviewId: number,
  roundId: number,
  questionId: number,
  answer: string
): Promise<RoundAnswerResponse> {
  return request<InterviewOperationTaskResponse<RoundAnswerResponse>>(
    `/interviews/${interviewId}/rounds/${roundId}/answers-task`,
    {
      method: "POST",
      body: { question_id: questionId, answer }
    }
  ).then((task) => waitForInterviewOperation(task));
}

export function regenerateRoundQuestion(
  interviewId: number,
  roundId: number,
  questionId: number
): Promise<RoundAnswerResponse> {
  return request<InterviewOperationTaskResponse<RoundAnswerResponse>>(
    `/interviews/${interviewId}/rounds/${roundId}/questions/${questionId}/regenerate-task`,
    { method: "POST" }
  ).then((task) => waitForInterviewOperation(task));
}

export function skipRoundQuestion(
  interviewId: number,
  roundId: number,
  questionId: number
): Promise<RoundAnswerResponse> {
  return request<InterviewOperationTaskResponse<RoundAnswerResponse>>(
    `/interviews/${interviewId}/rounds/${roundId}/questions/${questionId}/skip-task`,
    { method: "POST" }
  ).then((task) => waitForInterviewOperation(task));
}

export function finishInterviewRound(
  interviewId: number,
  roundId: number,
  finishType: "normal" | "early" = "early"
): Promise<RoundAnswerResponse | MultiRoundState> {
  return request<InterviewOperationTaskResponse<RoundAnswerResponse>>(
    `/interviews/${interviewId}/rounds/${roundId}/finish-task`,
    {
      method: "POST",
      body: { finish_type: finishType }
    }
  ).then((task) => waitForInterviewOperation(task));
}

export function finishMultiRoundInterview(
  interviewId: number,
  finishType: "normal" | "early" = "normal"
): Promise<FeedbackReport> {
  return request<InterviewOperationTaskResponse<FeedbackReport>>(
    `/interviews/${interviewId}/finish-task`,
    {
      method: "POST",
      body: { finish_type: finishType }
    }
  ).then((task) => waitForInterviewOperation(task));
}

export function getUserPreferences(): Promise<UserPreferences> {
  return request("/user/preferences");
}

export function updateUserPreferences(memoryEnabled: boolean): Promise<UserPreferences> {
  return request("/user/preferences", {
    method: "PATCH",
    body: { memory_enabled: memoryEnabled }
  });
}

export function clearMemories(): Promise<MemoryClearStatus> {
  return request("/memories", { method: "DELETE" });
}

export function getMemoryClearStatus(): Promise<MemoryClearStatus> {
  return request("/memories/clear-status");
}

export function listNotifications(
  options: {
    filter?: NotificationFilter;
    cursor?: string | null;
    limit?: number;
  } = {}
): Promise<NotificationListResponse> {
  const params = new URLSearchParams();
  params.set("filter", options.filter || "all");
  params.set("limit", String(options.limit || 10));
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  return request(`/notifications?${params.toString()}`);
}

export function getUnreadNotificationCount(): Promise<NotificationUnreadCountResponse> {
  return request("/notifications/unread-count");
}

export function getNotificationDetail(notificationId: number): Promise<NotificationDetail> {
  return request(`/notifications/${notificationId}`);
}

export function markNotificationRead(notificationId: number): Promise<void> {
  return request(`/notifications/${notificationId}/read`, { method: "POST" });
}

export function markAllNotificationsRead(): Promise<void> {
  return request("/notifications/read-all", { method: "POST" });
}

export function getInterviewHarnessStatus(interviewId: number): Promise<InterviewHarnessStatus> {
  return request(`/interviews/${interviewId}/harness`);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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

  const data = await readJson(response);
  if (!response.ok) {
    const errorBody = normalizeErrorBody(data);
    const code = errorBody.code;
    const message =
      errorBody.message ||
      (code ? ERROR_MESSAGES[code] : undefined) ||
      statusMessage(response.status);

    if (response.status === 401) {
      clearAuth();
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }

    throw new ApiError(message, code, response.status, errorBody.details);
  }

  return data as T;
}

async function waitForResumeParse(
  initialTask: ResumeParseTaskResponse
): Promise<ResumeUploadResponse> {
  const startedAt = Date.now();
  let task = initialTask;
  while (true) {
    if (task.status === "completed" && task.resume_id && task.structured_data) {
      return {
        id: task.resume_id,
        structured_data: task.structured_data
      };
    }
    if (task.status === "failed") {
      throw new ApiError(
        task.error_message || ERROR_MESSAGES.RESUME_PARSE_FAILED,
        "RESUME_PARSE_FAILED"
      );
    }
    if (Date.now() - startedAt > RESUME_UPLOAD_TIMEOUT_MS) {
      throw new ApiError(ERROR_MESSAGES.NETWORK_TIMEOUT, "NETWORK_TIMEOUT");
    }
    await delay(RESUME_PARSE_POLL_INTERVAL_MS);
    task = await getResumeParseTask(task.task_id);
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export function getInterviewOperationTask<T = unknown>(
  taskId: number
): Promise<InterviewOperationTaskResponse<T>> {
  return request(`/interviews/tasks/${taskId}`);
}

async function waitForInterviewOperation<T>(
  initialTask: InterviewOperationTaskResponse<T>
): Promise<T> {
  const startedAt = Date.now();
  let task = initialTask;
  while (true) {
    if (task.status === "completed" && task.result) {
      return task.result;
    }
    if (task.status === "failed") {
      throw new ApiError(
        task.error_message || ERROR_MESSAGES.INTERNAL_ERROR,
        task.error_code || "INTERNAL_ERROR"
      );
    }
    if (Date.now() - startedAt > INTERVIEW_OPERATION_TIMEOUT_MS) {
      throw new ApiError(ERROR_MESSAGES.NETWORK_TIMEOUT, "NETWORK_TIMEOUT");
    }
    await delay(INTERVIEW_OPERATION_POLL_INTERVAL_MS);
    task = await getInterviewOperationTask<T>(task.task_id);
  }
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
      return { error: { message: statusMessage(response.status) } };
    }
    throw new ApiError("响应格式异常，请稍后重试。", "INVALID_RESPONSE", response.status);
  }

  try {
    return JSON.parse(text);
  } catch {
    if (!response.ok) {
      return { error: { message: statusMessage(response.status) } };
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

function statusMessage(status: number): string {
  const messages: Record<number, string> = {
    400: "请求参数不正确。",
    401: "登录已失效，请重新登录。",
    403: "没有权限访问该资源。",
    404: "资源不存在。",
    409: "资源已存在。",
    422: "请求参数不正确。",
    500: "服务器开小差了，请稍后重试。",
    502: "后端服务暂时不可用，请稍后重试。",
    503: "后端服务暂时不可用，请稍后重试。",
    504: "请求超时，请稍后重试。"
  };
  return messages[status] || "请求失败，请稍后重试。";
}
