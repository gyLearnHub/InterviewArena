from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.interview import JOB_DESCRIPTION_MAX_LENGTH

JobMatchPosition = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
JobMatchDescription = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=JOB_DESCRIPTION_MAX_LENGTH,
    ),
]
JobMatchItemText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]
JobMatchSummaryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


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


class JobMatchAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_position: JobMatchPosition
    job_description: JobMatchDescription


class MatchedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: JobMatchItemText
    evidence: JobMatchItemText


class MissingRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: JobMatchItemText
    evidence_gap: JobMatchItemText


class RiskQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: JobMatchItemText
    related_requirement: JobMatchItemText


class PreparationSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: JobMatchItemText
    related_requirement: JobMatchItemText


class JobMatchAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: JobMatchSummaryText
    matched_requirements: list[MatchedRequirement] = Field(max_length=20)
    missing_requirements: list[MissingRequirement] = Field(max_length=20)
    risk_questions: list[RiskQuestion] = Field(max_length=20)
    preparation_suggestions: list[PreparationSuggestion] = Field(max_length=20)


class JobMatchAnalysisResponse(JobMatchAnalysisResult):
    resume_id: int
    target_position: JobMatchPosition
    analysis_basis: str
