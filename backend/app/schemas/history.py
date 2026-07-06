from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeedbackReportSummary(BaseModel):
    score: int
    weaknesses: list[str]
    suggestions: list[str]
    recommendation: str | None = None
    round_scores: list[dict[str, Any]] | None = None
    strengths: list[str] | None = None
    ability_analysis: list[str] | None = Field(default=None, exclude_if=lambda value: value is None)
    job_match: str | None = Field(default=None, exclude_if=lambda value: value is None)
    final_conclusion: str | None = Field(default=None, exclude_if=lambda value: value is None)
    confidence: str | None = Field(default=None, exclude_if=lambda value: value is None)
    reference_note: str | None = None
    report_reliability_status: str = "normal"
    detailed_feedback: dict[str, Any] | None = None


class HistoryListItem(BaseModel):
    interview_id: int
    target_position: str
    status: str
    overall_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ReportListItem(BaseModel):
    interview_id: int
    target_position: str
    score: int
    report_reliability_status: str = "normal"
    created_at: datetime | None = None
    used_candidate_memory: bool = False


class HistoryListResponse(BaseModel):
    items: list[HistoryListItem]
    next_offset: int | None = None


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    next_offset: int | None = None


class ResumeSummary(BaseModel):
    id: int
    created_at: datetime
    structured_data: dict[str, Any]


class HistoryRound(BaseModel):
    id: int
    round_type: str
    status: str
    score: int | None = None
    result: str | None = None
    summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    elapsed_seconds: int = 0


class HistoryQAItem(BaseModel):
    id: int
    round_id: int | None = None
    round_type: str | None = None
    sequence: int
    question_type: str
    question: str
    answer: str | None = None
    question_kind: str = "main"
    parent_question_id: int | None = None
    created_at: datetime | None = None
    question_evaluation: dict[str, Any] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class ReportRoundScoreSource(BaseModel):
    round_type: str
    status: str
    score: int | None = None
    source: str
    answered_question_count: int = 0
    evaluated_question_count: int = 0
    is_reference_only: bool = False


class ReportQualitySummary(BaseModel):
    completed_round_count: int = 0
    selected_round_count: int = 0
    answered_question_count: int = 0
    evaluated_question_count: int = 0
    score_coverage_percent: int = 0
    reliability_reasons: list[str] = Field(default_factory=list)
    score_sources: list[ReportRoundScoreSource] = Field(default_factory=list)


class HistoryDetail(BaseModel):
    interview_id: int
    target_position: str
    status: str
    mode: str = "multi_round"
    job_description: str | None = None
    overall_status: str | None = None
    rounds: list[HistoryRound] = Field(default_factory=list)
    qa_history: list[HistoryQAItem] = Field(default_factory=list)
    report_quality: ReportQualitySummary = Field(default_factory=ReportQualitySummary)
    resume: ResumeSummary
    feedback_report: FeedbackReportSummary | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    harness_status: str | None = None
    recovery_count: int = 0
    had_degradation: bool = False
    last_harness_error: str | None = None
