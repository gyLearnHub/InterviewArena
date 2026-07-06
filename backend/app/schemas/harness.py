from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.harness.contracts import (
    CheckpointCreate,
    HarnessExecutionRequest,
    HarnessExecutionResult,
    ReplayRequest,
    RuleEvaluation,
)


class HarnessTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int
    interview_id: int
    round_id: int | None = None
    node_id: str
    node_type: str
    agent_type: str
    purpose: str
    status: str
    validation_status: str
    event_write_failed: bool = False
    prompt_version: str | None = None
    model_name: str | None = None
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any] | None = None
    context_summary: dict[str, Any]
    tool_summary: dict[str, Any]
    token_usage: dict[str, Any]
    retry_records: list[dict[str, Any]]
    degradation_records: list[dict[str, Any]]
    error_code: str | None = None
    error_detail: str | None = None
    elapsed_ms: int | None = None
    execution_mode: str = "normal"
    idempotency_key: str | None = None
    source_trace_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HarnessTraceEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    trace_id: int
    event_type: str
    status: str
    payload: dict[str, Any]
    error_message: str | None = None
    created_at: datetime | None = None


class HarnessTraceDetailResponse(HarnessTraceResponse):
    events: list[HarnessTraceEventResponse] = Field(default_factory=list)


class HarnessCheckpointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int
    interview_id: int
    round_id: int | None = None
    trace_id: int | None = None
    node_id: str
    checkpoint_type: str
    status: str
    snapshot: dict[str, Any]
    resume_version: str | None = None
    created_at: datetime | None = None


class HarnessRuleEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int
    interview_id: int
    trace_id: int | None = None
    replay_run_id: int | None = None
    rule_name: str
    status: str
    severity: str
    evidence: dict[str, Any]
    failure_reason: str | None = None
    overall_grade: str | None = None
    created_at: datetime | None = None


class HarnessReplayRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int
    interview_id: int
    source_trace_id: int
    new_trace_id: int | None = None
    mode: str
    status: str
    parameters: dict[str, Any]
    result_snapshot: dict[str, Any] | None = None
    diff_summary: dict[str, Any]
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class HarnessTraceSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    interview_id: int
    round_id: int | None = None
    node_id: str
    node_type: str
    agent_type: str = ""
    purpose: str = ""
    status: str
    validation_status: str = "pending"
    retry_records: list[dict[str, Any]] = Field(default_factory=list)
    degradation_records: list[dict[str, Any]] = Field(default_factory=list)
    error_code: str | None = None
    elapsed_ms: int | None = None
    execution_mode: str = "normal"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HarnessCheckpointSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    interview_id: int
    round_id: int | None = None
    trace_id: int | None = None
    node_id: str
    checkpoint_type: str
    status: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    resume_version: str | None = None
    created_at: datetime | None = None


class HarnessRuleEvaluationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    interview_id: int
    trace_id: int | None = None
    rule_name: str
    status: str
    severity: str = "info"
    evidence: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    overall_grade: str | None = None
    created_at: datetime | None = None


class InterviewHarnessStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interview_id: int
    harness_status: str | None = None
    recovery_count: int = 0
    had_degradation: bool = False
    traces: list[HarnessTraceSummaryResponse] = Field(default_factory=list)
    evaluations: list[HarnessRuleEvaluationSummaryResponse] = Field(default_factory=list)
    checkpoints: list[HarnessCheckpointSummaryResponse] = Field(default_factory=list)


__all__ = [
    "CheckpointCreate",
    "HarnessCheckpointResponse",
    "HarnessCheckpointSummaryResponse",
    "HarnessExecutionRequest",
    "HarnessExecutionResult",
    "HarnessReplayRunResponse",
    "HarnessRuleEvaluationResponse",
    "HarnessRuleEvaluationSummaryResponse",
    "HarnessTraceDetailResponse",
    "HarnessTraceEventResponse",
    "HarnessTraceResponse",
    "HarnessTraceSummaryResponse",
    "InterviewHarnessStatusResponse",
    "ReplayRequest",
    "RuleEvaluation",
]
