from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FeedbackType = Literal["general", "bug", "question", "scoring", "report", "experience"]


class UserFeedbackSubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_type: FeedbackType = "general"
    content: str = Field(min_length=5, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)
    interview_id: int | None = Field(default=None, ge=1)
    round_id: int | None = Field(default=None, ge=1)
    question_id: int | None = Field(default=None, ge=1)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        content = value.strip()
        if len(content) < 5:
            raise ValueError("feedback content must be at least 5 characters")
        return content


class UserFeedbackSubmissionResponse(BaseModel):
    id: int
    feedback_type: FeedbackType
    content: str
    rating: int | None = None
    interview_id: int | None = None
    round_id: int | None = None
    question_id: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime
