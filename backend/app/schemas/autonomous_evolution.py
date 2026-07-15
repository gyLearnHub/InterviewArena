from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvolutionFamilyStatusResponse(BaseModel):
    job_family_key: str
    active_bundle_id: int | None = None
    active_bundle_key: str | None = None
    generation: int = 0
    bundle_status: str
    observation_count: int = 0
    consecutive_failures: int = 0
    eligible_interview_count: int = 0
    activated_at: datetime | None = None


class EvolutionRunStatusResponse(BaseModel):
    id: int
    job_family_key: str
    trigger_sequence: int
    status: str
    attempt_count: int
    max_retries: int
    candidate_artifact_key: str | None = None
    validation_summary: dict[str, Any] | None = None
    decision_summary: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None


class AutonomousEvolutionStatusResponse(BaseModel):
    enabled: bool
    trigger_interviews: int = Field(ge=1)
    synthetic_samples: int = Field(ge=1)
    observation_interviews: int = Field(ge=1)
    families: list[EvolutionFamilyStatusResponse]
    runs: list[EvolutionRunStatusResponse]
