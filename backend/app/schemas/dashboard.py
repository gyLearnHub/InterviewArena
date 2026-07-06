from datetime import datetime

from pydantic import BaseModel, Field


class DashboardInterviewSummary(BaseModel):
    interview_id: int
    target_position: str
    status: str
    score: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class DashboardReportSummary(BaseModel):
    interview_id: int
    target_position: str
    score: int
    created_at: datetime | None = None
    used_candidate_memory: bool = False
    report_reliability_status: str = "normal"


class DashboardScoreTrendPoint(BaseModel):
    interview_id: int
    score: int
    created_at: datetime | None = None


class DashboardAbilitySummary(BaseModel):
    round_type: str
    score: int | None = None
    result: str | None = None
    status: str | None = None
    is_reference_only: bool = False


class DashboardWeakPointSource(BaseModel):
    interview_id: int
    target_position: str
    round_type: str | None = None
    score: int | None = None
    occurred_at: datetime | None = None
    evidence: list[str] = Field(default_factory=list)


class DashboardWeakPointSummary(BaseModel):
    title: str
    summary: str
    suggestion: str | None = None
    severity: str = "medium"
    occurrence_count: int = 1
    evidence: list[str] = Field(default_factory=list)
    sources: list[DashboardWeakPointSource] = Field(default_factory=list)
    updated_at: datetime | None = None


class DashboardSummary(BaseModel):
    interview_count: int
    report_count: int
    personalized_feedback_used: bool
    memory_status: str = "accumulating"
    candidate_memory_count: int = 0
    latest_interview: DashboardInterviewSummary | None = None
    latest_report: DashboardReportSummary | None = None
    score_trend: list[DashboardScoreTrendPoint] = Field(default_factory=list)
    score_delta: int | None = None
    abilities: list[DashboardAbilitySummary] = Field(default_factory=list)
    weak_points: list[DashboardWeakPointSummary] = Field(default_factory=list)
