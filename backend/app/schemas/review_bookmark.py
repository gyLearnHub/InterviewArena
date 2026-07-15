import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.interview import InterviewCreateResponse

ReviewBookmarkRoundType = Literal["resume", "technical", "manager", "hr"]
ReviewBookmarkStatus = Literal["active", "practice_created", "mastered"]
ReviewBookmarkUpdateStatus = Literal["active", "mastered"]
ReviewBookmarkEvaluationSeverity = Literal["high", "medium", "low"]

REVIEW_BOOKMARK_EVALUATION_MAX_BYTES = 16 * 1024
REVIEW_BOOKMARK_EVALUATION_MAX_LIST_ITEMS = 8
REVIEW_BOOKMARK_EVALUATION_MAX_TEXT_LENGTH = 1000
REVIEW_BOOKMARK_EVALUATION_MAX_META_LENGTH = 128


class ReviewBookmarkEvaluationDimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(min_length=1, max_length=120)
    score: float | None = Field(default=None, ge=0, le=100)
    reason: str | None = Field(default=None, max_length=REVIEW_BOOKMARK_EVALUATION_MAX_TEXT_LENGTH)

    @field_validator("dimension", "reason", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        return _normalize_optional_text(value)


class ReviewBookmarkEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: int | None = Field(default=None, ge=1)
    question_id: int | None = Field(default=None, ge=1)
    round_id: int | None = Field(default=None, ge=1)
    round_type: ReviewBookmarkRoundType | None = None
    status: str | None = Field(default=None, max_length=32)
    source: str | None = Field(default=None, max_length=32)
    severity: ReviewBookmarkEvaluationSeverity | None = None
    total_score: float | None = Field(default=None, ge=0, le=100)
    dimension_scores: list[ReviewBookmarkEvaluationDimensionScore] | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_LIST_ITEMS,
    )
    strengths: list[str] | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_LIST_ITEMS,
    )
    issues: list[str] | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_LIST_ITEMS,
    )
    evidence: list[str] | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_LIST_ITEMS,
    )
    should_follow_up: bool | None = None
    follow_up_direction: str | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_TEXT_LENGTH,
    )
    impact: str | None = Field(default=None, max_length=REVIEW_BOOKMARK_EVALUATION_MAX_TEXT_LENGTH)
    prompt_version: str | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_META_LENGTH,
    )
    model_name: str | None = Field(
        default=None,
        max_length=REVIEW_BOOKMARK_EVALUATION_MAX_META_LENGTH,
    )

    @field_validator(
        "status",
        "source",
        "follow_up_direction",
        "impact",
        "prompt_version",
        "model_name",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        return _normalize_optional_text(value)

    @field_validator("strengths", "issues", "evidence", mode="before")
    @classmethod
    def normalize_string_list(cls, value: object) -> object:
        if value is None:
            return None
        items: object
        if isinstance(value, str):
            items = [value]
        else:
            items = value
        if not isinstance(items, list):
            return value
        normalized: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise PydanticCustomError(
                    "review_bookmark_evaluation_list_item",
                    "复盘评价列表项必须是字符串。",
                )
            text = item.strip()
            if text:
                normalized.append(text)
        return normalized or None

    @field_validator("dimension_scores", mode="after")
    @classmethod
    def normalize_empty_dimension_scores(
        cls,
        value: list[ReviewBookmarkEvaluationDimensionScore] | None,
    ) -> list[ReviewBookmarkEvaluationDimensionScore] | None:
        return value or None

    @field_validator("strengths", "issues", "evidence", mode="after")
    @classmethod
    def normalize_empty_string_list(cls, value: list[str] | None) -> list[str] | None:
        return value or None

    @model_validator(mode="after")
    def validate_total_size(self) -> "ReviewBookmarkEvaluation":
        try:
            validate_review_bookmark_evaluation_size(review_bookmark_evaluation_to_dict(self))
        except ValueError as exc:
            raise PydanticCustomError(
                "review_bookmark_evaluation_too_large",
                "复盘评价内容过大。",
            ) from exc
        return self


def review_bookmark_evaluation_to_dict(
    value: ReviewBookmarkEvaluation | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, ReviewBookmarkEvaluation):
        payload = value.model_dump(exclude_none=True)
    elif isinstance(value, Mapping):
        payload = ReviewBookmarkEvaluation.model_validate(dict(value)).model_dump(
            exclude_none=True,
        )
    else:
        raise ValueError("复盘评价内容格式不正确。")
    validate_review_bookmark_evaluation_size(payload)
    return payload


def review_bookmark_evaluation_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("复盘评价内容格式不正确。") from exc


def validate_review_bookmark_evaluation_size(value: Mapping[str, Any]) -> None:
    serialized = review_bookmark_evaluation_json(value)
    if len(serialized.encode("utf-8")) > REVIEW_BOOKMARK_EVALUATION_MAX_BYTES:
        raise ValueError("复盘评价内容过大。")


class ReviewBookmarkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: int | None = Field(default=None, ge=1)
    round_id: int | None = Field(default=None, ge=1)
    question_id: int | None = Field(default=None, ge=1)
    round_type: ReviewBookmarkRoundType | None = None
    title: str | None = Field(default=None, max_length=500)
    issue: str | None = Field(default=None, max_length=1000)
    suggestion: str | None = Field(default=None, max_length=1000)
    source_score: int | None = Field(default=None, ge=0, le=100)
    evaluation: ReviewBookmarkEvaluation | None = None

    @field_validator("title", "issue", "suggestion")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_text(value)
        return normalized if isinstance(normalized, str) else None


class ReviewBookmarkItem(BaseModel):
    id: int
    title: str
    issue: str
    suggestion: str | None = None
    status: ReviewBookmarkStatus | str = "active"
    source_score: int | None = None
    source_interview_id: int | None = None
    target_position: str
    round_id: int | None = None
    round_type: str | None = None
    question_id: int | None = None
    question: str | None = None
    answer: str | None = None
    practice_interview_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ReviewBookmarkUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewBookmarkUpdateStatus


class ReviewBookmarkBatchResponse(BaseModel):
    source_interview_id: int
    items: list[ReviewBookmarkItem]
    created_count: int


class ReviewBookmarkPracticeResponse(InterviewCreateResponse):
    bookmark_id: int
    source_interview_id: int | None = None
    practice_focus: str


def _normalize_optional_text(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return value
