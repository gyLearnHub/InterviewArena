from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    content: str = Field(min_length=1)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    source_round_id: int | None = None
    agent_type: str | None = None
    position_key: str | None = None
    scenario: str | None = None


class MemorySummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_memories: list[MemoryItem] = Field(default_factory=list)
    interviewer_memories: list[MemoryItem] = Field(default_factory=list)
    agent_memories: list[MemoryItem] = Field(default_factory=list)


class MemoryClearStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: int | None
    status: MemoryTaskStatus
    deleted_count: int = 0
    error_message: str | None = None


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
