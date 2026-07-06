from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredResumeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basic_info: dict[str, Any]
    education: list[dict[str, Any]]
    work_experience: list[dict[str, Any]]
    project_experience: list[dict[str, Any]]
    skills: list[Any]
    certificates_awards: list[Any]


class ResumeUploadResponse(BaseModel):
    id: int
    structured_data: StructuredResumeData


class ResumeParseTaskResponse(BaseModel):
    task_id: int
    status: str
    resume_id: int | None = None
    structured_data: StructuredResumeData | None = None
    error_message: str | None = None


class ResumeListItem(BaseModel):
    id: int
    name: str
    uploaded_at: datetime
    last_used_at: datetime | None = None
    parse_status: str
    is_default: bool = False


class ResumeDetailResponse(ResumeListItem):
    structured_data: StructuredResumeData


class ResumeUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
