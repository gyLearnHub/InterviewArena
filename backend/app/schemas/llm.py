from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basic_info: dict[str, Any]
    education: list[dict[str, Any]]
    work_experience: list[dict[str, Any]]
    project_experience: list[dict[str, Any]]
    skills: list[str]
    certificates_awards: list[Any]


class QuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: str = Field(min_length=1)
    question: str = Field(min_length=1)


class FeedbackResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    weaknesses: list[str]
    suggestions: list[str]
