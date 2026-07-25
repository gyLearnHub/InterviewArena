from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MemoryCollection = Literal["candidate_memories", "interviewer_memories", "agent_memories"]
MemoryStatus = Literal["active", "pending_review", "superseded", "archived", "deleted"]
MemoryIndexStatus = Literal["pending_index", "indexed", "index_failed", "pending_delete"]
MemoryTaskStatus = Literal["idle", "pending", "processing", "completed", "failed", "retry_wait"]
MemoryUsageScene = Literal["new_question", "follow_up", "feedback", "interviewer", "agent"]


class MemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: MemoryCollection
    id: int | None = None
    memory_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2000)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    source_round_id: int | None = None
    agent_type: str | None = Field(default=None, min_length=1, max_length=64)
    position_key: str | None = Field(default=None, min_length=1, max_length=128)
    scenario: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_collection_identity(self) -> "MemoryItem":
        if self.collection == "interviewer_memories":
            if not self.agent_type or not self.position_key:
                raise ValueError(
                    "interviewer memories require agent_type and position_key"
                )
        elif self.collection == "agent_memories":
            if not self.agent_type or not self.scenario:
                raise ValueError("agent memories require agent_type and scenario")
        return self


class MemorySummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_memories: list[MemoryItem] = Field(default_factory=list, max_length=20)
    interviewer_memories: list[MemoryItem] = Field(default_factory=list, max_length=20)
    agent_memories: list[MemoryItem] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_collection_buckets(self) -> "MemorySummaryOutput":
        buckets = {
            "candidate_memories": self.candidate_memories,
            "interviewer_memories": self.interviewer_memories,
            "agent_memories": self.agent_memories,
        }
        for expected_collection, items in buckets.items():
            if any(item.collection != expected_collection for item in items):
                raise ValueError(
                    f"{expected_collection} contains an item for another collection"
                )
        return self


class MemoryClearStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int | None
    status: MemoryTaskStatus
    deleted_count: int = 0
    error_message: str | None = None


class MemoryGenerationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending_count: int = Field(default=0, ge=0)
    processing_count: int = Field(default=0, ge=0)
    retry_wait_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)


class MemoryRetryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requeued_count: int = Field(ge=0)


class ManagedMemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    memory_type: str
    title: str
    content: str
    confidence: float
    status: MemoryStatus
    index_status: MemoryIndexStatus
    source_interview_id: int | None = None
    source_round_id: int | None = None
    target_position: str | None = None
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ManagedMemoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ManagedMemoryItem]
    total: int
    active_count: int
    pending_review_count: int
    limit: int
    offset: int
    next_offset: int | None = None
    memory_types: list[str] = Field(default_factory=list)


class RetrievedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: MemoryCollection
    memory_id: int
    memory_type: str
    title: str
    content: str
    confidence: float
    score: float
    created_at: datetime | None = None


class MemoryRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int | None = None
    memory_enabled: bool = True
    interview_id: int | None = None
    round_id: int | None = None
    agent_type: str | None = None
    position_key: str | None = None
    scenario: str | None = None
    usage_scene: MemoryUsageScene
    intent: str
    query_text: str | None = None
    memory_types: list[str] = Field(default_factory=list)
    collections: list[MemoryCollection] = Field(default_factory=list)
    top_k: int | None = None


class MemoryRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    memories: list[RetrievedMemory]
    fallback_reason: str | None = None
