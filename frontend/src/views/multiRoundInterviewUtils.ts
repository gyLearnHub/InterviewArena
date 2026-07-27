import type {
  MultiRoundState,
  QuestionEvaluation,
  RoundAnswerResponse,
  RoundSummary
} from "../api";

export function roundSummaryText(summary: RoundSummary): string {
  const issues = summary.main_issues?.filter(Boolean) || [];
  if (issues.length > 0) {
    return issues.join("；");
  }
  const suggestions = summary.suggestions?.filter(Boolean) || [];
  if (suggestions.length > 0) {
    return suggestions[0];
  }
  return summary.reference_note || "";
}

export function questionEvaluationText(evaluation: QuestionEvaluation): string {
  const strengths = evaluation.strengths?.filter(Boolean) || [];
  if (strengths.length > 0) {
    return strengths[0];
  }
  const issues = evaluation.issues?.filter(Boolean) || [];
  if (issues.length > 0) {
    return issues[0];
  }
  return evaluation.follow_up_direction || "已完成本题评分。";
}

export function answerQualityTone(evaluation: QuestionEvaluation): string {
  if (evaluation.status === "fallback" || evaluation.total_score === null) {
    return "quality-hint";
  }
  const score = evaluation.total_score ?? 0;
  if (score >= 80) return "quality-strong";
  if (score >= 60) return "quality-steady";
  return "quality-needs-work";
}

export function answerQualityLabel(evaluation: QuestionEvaluation): string {
  if (evaluation.status === "fallback" || evaluation.total_score === null) {
    return "结构建议";
  }
  const score = evaluation.total_score ?? 0;
  if (score >= 80) return "表现较好";
  if (score >= 60) return "可以打磨";
  return "需要补强";
}

export function answerQualityLead(evaluation: QuestionEvaluation): string {
  if (evaluation.status === "fallback" || evaluation.total_score === null) {
    return "本次未生成可靠分数，以下建议仅用于检查回答结构。";
  }
  const score = evaluation.total_score ?? 0;
  if (score >= 80) {
    return "回答整体扎实，可以继续强化证据和岗位相关性。";
  }
  if (score >= 60) {
    return "回答方向基本成立，建议优先补足下面的关键信息。";
  }
  return "回答仍有明显缺口，建议按下面的提示补充后再复盘。";
}

export function answerQualityStrengths(evaluation: QuestionEvaluation): string[] {
  return uniqueEvaluationText(evaluation.strengths).slice(0, 3);
}

export function answerQualityIssues(evaluation: QuestionEvaluation): string[] {
  return uniqueEvaluationText(evaluation.issues).slice(0, 4);
}

export function answerQualityEvidence(evaluation: QuestionEvaluation): string[] {
  return uniqueEvaluationText(evaluation.evidence).slice(0, 3);
}

export function answerQualityDimensions(evaluation: QuestionEvaluation) {
  return (evaluation.dimension_scores || []).filter(
    (item) =>
      item &&
      typeof item.dimension === "string" &&
      item.dimension.trim() &&
      typeof item.score === "number"
  );
}

export function uniqueEvaluationText(values?: string[]): string[] {
  return [...new Set((values || []).map((value) => value.trim()).filter(Boolean))];
}

export function hasAnswerQualityDetails(evaluation: QuestionEvaluation): boolean {
  return Boolean(
    answerQualityDimensions(evaluation).length ||
    answerQualityStrengths(evaluation).length ||
    answerQualityIssues(evaluation).length ||
    evaluation.follow_up_direction ||
    answerQualityEvidence(evaluation).length
  );
}

export function canBookmarkAnswer(evaluation: QuestionEvaluation): boolean {
  return typeof evaluation.question_id === "number";
}

export function clipBookmarkText(
  value: string | null | undefined,
  maxLength: number
): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized.slice(0, maxLength) : undefined;
}

export function reviewBookmarkEvaluation(evaluation: QuestionEvaluation): QuestionEvaluation {
  return {
    question_id: evaluation.question_id,
    round_id: evaluation.round_id,
    round_type: evaluation.round_type,
    status: clipBookmarkText(evaluation.status, 32),
    total_score:
      typeof evaluation.total_score === "number"
        ? normalizeBookmarkScore(evaluation.total_score)
        : evaluation.total_score,
    dimension_scores: normalizeBookmarkDimensionScores(evaluation.dimension_scores),
    strengths: evaluation.strengths?.slice(0, 8).map((item) => item.slice(0, 1000)),
    issues: evaluation.issues?.slice(0, 8).map((item) => item.slice(0, 1000)),
    evidence: evaluation.evidence?.slice(0, 8).map((item) => item.slice(0, 1000)),
    should_follow_up: evaluation.should_follow_up,
    follow_up_direction: clipBookmarkText(evaluation.follow_up_direction, 1000),
    prompt_version: clipBookmarkText(evaluation.prompt_version, 128),
    model_name: clipBookmarkText(evaluation.model_name, 128)
  };
}

export function normalizeBookmarkDimensionScores(value: unknown[] | undefined) {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.slice(0, 8).flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const record = item as Record<string, unknown>;
    const dimension =
      typeof record.dimension === "string" ? record.dimension.trim().slice(0, 120) : "";
    if (!dimension || typeof record.score !== "number") {
      return [];
    }
    return [
      {
        dimension,
        score: normalizeBookmarkScore(record.score),
        reason:
          typeof record.reason === "string"
            ? record.reason.trim().slice(0, 1000) || undefined
            : undefined
      }
    ];
  });
}

export function normalizeBookmarkScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function formatDuration(totalSeconds: number): string {
  const normalized = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(normalized / 60);
  const seconds = normalized % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

export function isStatePayload(
  payload: RoundAnswerResponse | MultiRoundState
): payload is MultiRoundState {
  return Boolean((payload as MultiRoundState).rounds && (payload as MultiRoundState).interview_id);
}
