from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class QuestionEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: int
    round_id: int
    question_id: int
    round_type: str
    dimensions: list[str]
    resume: dict[str, Any]
    target_position: str
    job_description: str | None = None
    interview_strategy: dict[str, Any] | None = None
    question: str
    answer: str


class QuestionEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=100)
    dimension_scores: list[DimensionScore]
    strengths: list[str]
    issues: list[str]
    evidence: list[str]
    should_follow_up: bool
    follow_up_direction: str | None = None

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence(cls, value: object) -> object:
        if isinstance(value, str):
            return [value]
        return value


class RoundEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: int
    round_id: int
    round_type: str
    dimensions: list[str]
    qa_history: list[dict[str, Any]]
    question_evaluations: list[dict[str, Any]]
    interview_strategy: dict[str, Any] | None = None
    is_reference_only: bool = False


class RoundEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=100)
    result: Literal["passed", "pending", "failed"]
    dimension_scores: list[DimensionScore]
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    evidence: list[str]
    is_reference_only: bool = False
    reference_note: str | None = None


class FinalEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: int
    resume_summary: dict[str, Any]
    target_position: str
    job_description: str | None = None
    interview_strategy: dict[str, Any] | None = None
    round_evaluations: list[dict[str, Any]]
    has_incomplete_rounds: bool = False
    has_reference_only_rounds: bool = False


class FinalRoundScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_type: str
    score: int | None = Field(default=None, ge=0, le=100)
    result: str | None = None
    is_reference_only: bool = False
    status: str | None = None


class FinalProblemDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    severity: Literal["high", "medium", "low"] = "medium"
    evidence: list[str] = Field(default_factory=list)
    impact: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)


class FinalRoundReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_type: str
    score: int | None = Field(default=None, ge=0, le=100)
    result: str | None = None
    status: str | None = None
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    is_reference_only: bool = False


class FinalActionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"] = "medium"
    steps: list[str] = Field(default_factory=list)
    expected_outcome: str | None = None


class FinalEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_score: int = Field(ge=0, le=100)
    round_scores: list[FinalRoundScore]
    ability_analysis: list[str]
    job_match: str
    core_strengths: list[str]
    main_risks: list[str]
    improvement_plan: list[str]
    final_conclusion: str
    confidence: Literal["high", "medium", "low"]
    reference_note: str | None = None
    problem_diagnosis: list[FinalProblemDiagnosis] = Field(default_factory=list)
    round_reviews: list[FinalRoundReview] = Field(default_factory=list)
    action_plan: list[FinalActionPlan] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
