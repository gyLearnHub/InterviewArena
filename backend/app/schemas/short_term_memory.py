from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ShortTermMemoryStatus(BaseModel):
    status: Literal["healthy", "compressed", "recovered", "degraded"]
    source: Literal["redis", "mysql"]
    compressed: bool = False
    fallback_used: bool = False
    updated_at: datetime | None = None


class ShortTermQA(BaseModel):
    question_id: int
    round_id: int | None = None
    round_type: str | None = None
    sequence: int
    question_type: str
    question_kind: str = "main"
    question: str
    answer: str
    evaluation: dict[str, Any] | None = None
    answer_truncated: bool = False


class RollingShortTermSummary(BaseModel):
    key_facts: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    covered_topics: list[str] = Field(default_factory=list)
    pending_follow_ups: list[str] = Field(default_factory=list)
    consistency_flags: list[str] = Field(default_factory=list)
    evidence_question_ids: list[int] = Field(default_factory=list)


class CompletedRoundMemory(BaseModel):
    round_id: int
    round_type: str
    status: str
    summary: dict[str, Any]


class ShortTermMemorySnapshot(BaseModel):
    schema_version: int = 1
    version: int = 0
    user_id: int
    interview_id: int
    current_round: str | None = None
    source_revision: str = ""
    recent_qa: list[ShortTermQA] = Field(default_factory=list)
    rolling_summary: RollingShortTermSummary = Field(
        default_factory=RollingShortTermSummary
    )
    completed_rounds: list[CompletedRoundMemory] = Field(default_factory=list)
    estimated_tokens: int = 0
    compression_count: int = 0
    updated_at: datetime
