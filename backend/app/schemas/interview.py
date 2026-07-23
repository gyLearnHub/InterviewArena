from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.short_term_memory import ShortTermMemoryStatus

JOB_DESCRIPTION_MAX_LENGTH = 8_000
ROUND_ANSWER_MAX_LENGTH = 8_000
InterviewGoal = Literal["internship", "campus", "big_tech"]
InterviewDifficulty = Literal["easy", "normal", "pressure"]
InterviewExperienceMode = Literal["training", "simulation"]
TimeLimitMinutes = Literal[30, 45, 60]
DEFAULT_INTERVIEW_GOAL: InterviewGoal = "campus"
DEFAULT_INTERVIEW_DIFFICULTY: InterviewDifficulty = "normal"
DEFAULT_INTERVIEW_EXPERIENCE_MODE: InterviewExperienceMode = "training"
DEFAULT_TIME_LIMIT_MINUTES: TimeLimitMinutes = 45


class InterviewCreateRequest(BaseModel):
    resume_id: int
    target_position: str = Field(min_length=1, max_length=128)
    job_description: str | None = Field(default=None, max_length=JOB_DESCRIPTION_MAX_LENGTH)
    selected_rounds: list[str] | None = None
    interview_goal: InterviewGoal = DEFAULT_INTERVIEW_GOAL
    difficulty: InterviewDifficulty = DEFAULT_INTERVIEW_DIFFICULTY
    experience_mode: InterviewExperienceMode = DEFAULT_INTERVIEW_EXPERIENCE_MODE
    time_limit_minutes: TimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES


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
    difficulty: InterviewDifficulty = DEFAULT_INTERVIEW_DIFFICULTY
    time_limit_minutes: TimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES
    execution_status: str | None = None
    retry_count: int = 0


class InterviewCreateResponse(BaseModel):
    id: int
    status: str
    mode: str = "multi_round"
    interview_goal: InterviewGoal = DEFAULT_INTERVIEW_GOAL
    difficulty: InterviewDifficulty = DEFAULT_INTERVIEW_DIFFICULTY
    experience_mode: InterviewExperienceMode = DEFAULT_INTERVIEW_EXPERIENCE_MODE
    time_limit_minutes: TimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES
    rounds: list[InterviewRoundResponse] = Field(default_factory=list)


class WeaknessPracticeRequest(BaseModel):
    weakness: str = Field(min_length=1, max_length=500)
    suggestion: str | None = Field(default=None, max_length=500)
    round_type: str | None = Field(
        default=None,
        pattern="^(resume|technical|manager|hr)$",
    )


class WeaknessPracticeResponse(InterviewCreateResponse):
    source_interview_id: int
    practice_focus: str


class RoundAnswerRequest(BaseModel):
    question_id: int
    answer: str = Field(min_length=1, max_length=ROUND_ANSWER_MAX_LENGTH)
    finish_after_answer: bool = False


class RoundStartRequest(BaseModel):
    difficulty: InterviewDifficulty = DEFAULT_INTERVIEW_DIFFICULTY
    time_limit_minutes: TimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES


class AnswerDraftRequest(BaseModel):
    answer: str = Field(default="", max_length=ROUND_ANSWER_MAX_LENGTH)


class AnswerDraftResponse(BaseModel):
    question_id: int
    answer: str | None = None
    updated_at: datetime | None = None


class RoundFinishRequest(BaseModel):
    finish_type: str = Field(default="normal", pattern="^(normal|early|timeout)$")


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
    is_last_question: bool = False


class RoundAnswerResponse(BaseModel):
    action: str
    question: RoundQuestionResponse | None = None
    round_summary: dict[str, Any] | None = None
    answer_evaluation: dict[str, Any] | None = None
    short_term_memory: ShortTermMemoryStatus | None = None


class AnswerReanswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=ROUND_ANSWER_MAX_LENGTH)


class AnswerReanswerAttemptResponse(BaseModel):
    id: int
    attempt_number: int
    answer: str
    evaluation: dict[str, Any]
    score_delta: int | None = None
    created_at: datetime


class AnswerReanswerResponse(BaseModel):
    interview_id: int
    question_id: int
    question: str
    original_answer: str
    original_evaluation: dict[str, Any] | None = None
    attempt: AnswerReanswerAttemptResponse


class AnswerReanswerListResponse(BaseModel):
    interview_id: int
    question_id: int
    question: str
    original_answer: str
    original_evaluation: dict[str, Any] | None = None
    attempts: list[AnswerReanswerAttemptResponse] = Field(default_factory=list)


class InterviewStateResponse(BaseModel):
    interview_id: int
    mode: str
    overall_status: str
    target_position: str
    job_description: str | None = None
    interview_goal: InterviewGoal = DEFAULT_INTERVIEW_GOAL
    difficulty: InterviewDifficulty = DEFAULT_INTERVIEW_DIFFICULTY
    experience_mode: InterviewExperienceMode = DEFAULT_INTERVIEW_EXPERIENCE_MODE
    time_limit_minutes: TimeLimitMinutes = DEFAULT_TIME_LIMIT_MINUTES
    current_round: str | None = None
    elapsed_seconds: int = 0
    harness_status: str | None = None
    recovery_count: int = 0
    had_degradation: bool = False
    last_harness_error: str | None = None
    rounds: list[InterviewRoundResponse]
    current_question: RoundQuestionResponse | None = None
    qa_history: list[dict[str, Any]] = Field(default_factory=list)
    short_term_memory: ShortTermMemoryStatus | None = None
