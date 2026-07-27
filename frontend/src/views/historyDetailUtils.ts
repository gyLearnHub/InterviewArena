import type {
  InterviewRound,
  MultiRoundQaEntry,
  ProblemDiagnosis,
  QuestionEvaluation,
  RoundReview,
  RoundType
} from "../api";
import { parseApiDate } from "../formatters";

export type WeaknessPracticeItem = {
  key: string;
  title: string;
  weakness: string;
  suggestion?: string;
  roundType?: RoundType;
  sourceLabel: string;
};

export const orderedRoundTypes: RoundType[] = ["resume", "technical", "manager", "hr"];

export function problemDiagnosisPracticeItem(item: ProblemDiagnosis): WeaknessPracticeItem {
  return {
    key: `diagnosis-${item.title}`,
    title: item.title,
    weakness: item.title,
    suggestion: item.suggestion,
    sourceLabel: severityText(item.severity)
  };
}

export function roundReviewPracticeItems(review: RoundReview): WeaknessPracticeItem[] {
  const roundType = asRoundType(review.round_type);
  return (review.issues || []).slice(0, 2).map((issue, index) => ({
    key: `round-${review.round_type}-${index}-${issue}`,
    title: `${roundLabel(review.round_type)}：${issue}`,
    weakness: issue,
    suggestion: review.suggestions?.[index] || review.suggestions?.[0],
    roundType: roundType || undefined,
    sourceLabel: roundLabel(review.round_type)
  }));
}

export function dedupePracticeItems(items: WeaknessPracticeItem[]): WeaknessPracticeItem[] {
  const seen = new Set<string>();
  const result: WeaknessPracticeItem[] = [];
  for (const item of items) {
    const key = `${item.roundType || "all"}:${item.weakness.trim()}`;
    if (!item.weakness.trim() || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }
  return result;
}

export function asRoundType(value: string): RoundType | null {
  return orderedRoundTypes.includes(value as RoundType) ? (value as RoundType) : null;
}

export function statusText(status: string): string {
  const labels: Record<string, string> = {
    created: "已创建",
    in_progress: "进行中",
    finished: "已结束",
    completed: "已结束"
  };
  return labels[status] || status;
}

export function roundLabel(type: string): string {
  const labels: Record<string, string> = {
    resume: "简历面",
    technical: "技术面",
    manager: "主管面",
    hr: "HR 面"
  };
  return labels[type] || "未分组";
}

export function roundOrdinal(index: number): string {
  return ["第一轮", "第二轮", "第三轮", "第四轮"][index] || `第 ${index + 1} 轮`;
}

export function scoreFromRoundSummary(round: InterviewRound | null): number | null {
  return typeof round?.summary?.score === "number" ? round.summary.score : null;
}

export function firstNumber(values: Array<number | null | undefined>): number | null {
  const value = values.find((item) => typeof item === "number");
  return typeof value === "number" ? value : null;
}

export function normalizeScore(score: number | null): number | null {
  if (typeof score !== "number") return null;
  return Math.max(0, Math.min(100, score));
}

export function formatScore(score: number): string {
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

export function ratingText(score: number | null): string {
  if (score === null) return "待评";
  if (score >= 85) return "优秀";
  if (score >= 70) return "良好";
  if (score >= 60) return "合格";
  return "待提升";
}

export function confidenceText(value: string): string {
  const labels: Record<string, string> = {
    high: "高置信度",
    medium: "中等置信度",
    low: "低置信度"
  };
  return labels[value] || value;
}

export function severityText(value: string): string {
  const labels: Record<string, string> = {
    high: "高风险",
    medium: "中风险",
    low: "低风险"
  };
  return labels[value] || value;
}

export function priorityText(value: string): string {
  const labels: Record<string, string> = {
    high: "高优先级",
    medium: "中优先级",
    low: "低优先级"
  };
  return labels[value] || value;
}

export function scoreSourceText(value: string): string {
  const labels: Record<string, string> = {
    final_report: "总评报告",
    round_summary: "轮次评分",
    none: "暂无评分"
  };
  return labels[value] || value;
}

export function radarPoints(values: number[]) {
  return values.map((value, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / values.length;
    const radius = (82 * Math.max(0, Math.min(100, value))) / 100;
    return {
      x: Number((180 + Math.cos(angle) * radius).toFixed(1)),
      y: Number((126 + Math.sin(angle) * radius).toFixed(1))
    };
  });
}

export function radarGuide(level: number): string {
  return pointString(
    radarPoints([100 * level, 100 * level, 100 * level, 100 * level, 100 * level])
  );
}

export function pointString(points: Array<{ x: number; y: number }>): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

export function questionScoreText(entry: MultiRoundQaEntry): string {
  const score =
    typeof entry.question_evaluation?.total_score === "number"
      ? entry.question_evaluation.total_score
      : null;
  return score === null ? "本题暂未评分" : `本题评分：${formatScore(score)} / 100`;
}

export function questionEvaluationText(entry: MultiRoundQaEntry): string {
  const evaluation = entry.question_evaluation;
  return evaluation ? evaluationText(evaluation) : "";
}

export function evaluationText(evaluation: QuestionEvaluation): string {
  return (
    evaluation.strengths?.find(Boolean) ||
    evaluation.issues?.find(Boolean) ||
    evaluation.follow_up_direction ||
    ""
  );
}

export function questionText(entry: MultiRoundQaEntry): string {
  return entry.question || entry.question_text || entry.prompt || "暂无问题内容";
}

export function answerText(entry: MultiRoundQaEntry): string {
  return answeredText(entry) || "暂无回答";
}

export function answeredText(entry: MultiRoundQaEntry): string {
  return entry.answer || entry.answer_text || entry.user_answer || "";
}

export function formatDateTime(value: string | null): string {
  return value ? parseApiDate(value).toLocaleString("zh-CN", { hour12: false }) : "暂无";
}

export function formatDuration(seconds: number): string {
  if (!seconds) return "-";
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `${minutes} 分钟`;
}
