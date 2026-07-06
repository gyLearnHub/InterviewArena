from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

JOB_DESCRIPTION_MAX_LENGTH = 8_000
ROUND_ANSWER_MAX_LENGTH = 8_000


class InterviewCreateRequest(BaseModel):
    resume_id: int
    target_position: str = Field(min_length=1, max_length=128)
    job_description: str | None = Field(default=None, max_length=JOB_DESCRIPTION_MAX_LENGTH)
    selected_rounds: list[str] | None = None


class InterviewRoundResponse(BaseModel):
    id: int
    round_type: str
    status: str
    score: int | None = None
    result: str | None = None
    summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    elapsed_seconds: int = 0
    execution_status: str | None = None
    retry_count: int = 0


class InterviewCreateResponse(BaseModel):
    id: int
    status: str
    mode: str = "multi_round"
    rounds: list[InterviewRoundResponse] = Field(default_factory=list)


class RoundAnswerRequest(BaseModel):
    question_id: int
    answer: str = Field(min_length=1, max_length=ROUND_ANSWER_MAX_LENGTH)
    finish_after_answer: bool = False


class RoundFinishRequest(BaseModel):
    finish_type: str = Field(default="normal", pattern="^(normal|early)$")


class InterviewFinishRequest(BaseModel):
    finish_type: str = Field(default="normal", pattern="^(normal|early)$")


class InterviewOperationTaskResponse(BaseModel):
    task_id: int
    operation: str
    status: str
    interview_id: int
    round_id: int | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


class FeedbackReportResponse(BaseModel):
    interview_id: int
    score: int = Field(ge=0, le=100)
    weaknesses: list[str]
    suggestions: list[str]
    recommendation: str | None = None
    round_scores: list[dict[str, Any]] | None = None
    strengths: list[str] | None = None
    ability_analysis: list[str] | None = None
    job_match: str | None = None
    final_conclusion: str | None = None
    confidence: str | None = None
    reference_note: str | None = None
    used_candidate_memory: bool = False
    report_reliability_status: str = "normal"
    detailed_feedback: dict[str, Any] | None = None


class InterviewStatusResponse(BaseModel):
    id: int
    status: str
    question_count: int
    started_at: datetime | None = None
    ended_at: datetime | None = None


class RoundQuestionResponse(BaseModel):
    id: int
    round_id: int
    sequence: int
    question_kind: str
    question_status: str = "active"
    parent_question_id: int | None = None
    regenerated_from_question_id: int | None = None
    question_type: str
    question: str


class RoundAnswerResponse(BaseModel):
    action: str
    question: RoundQuestionResponse | None = None
    round_summary: dict[str, Any] | None = None


class InterviewStateResponse(BaseModel):
    interview_id: int
    mode: str
    overall_status: str
    target_position: str
    job_description: str | None = None
    current_round: str | None = None
    elapsed_seconds: int = 0
    harness_status: str | None = None
    recovery_count: int = 0
    had_degradation: bool = False
    last_harness_error: str | None = None
    rounds: list[InterviewRoundResponse]
    current_question: RoundQuestionResponse | None = None
    qa_history: list[dict[str, Any]] = Field(default_factory=list)
