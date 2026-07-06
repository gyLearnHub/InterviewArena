from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JSONDict = dict[str, Any]

HarnessStatus = Literal[
    "pending",
    "running",
    "retrying",
    "degraded",
    "paused",
    "failed",
    "completed",
]
ExecutionMode = Literal["normal", "replay", "rerun"]
ValidationStatus = Literal["pending", "passed", "warning", "failed"]
RuleStatus = Literal["passed", "warning", "failed"]
RuleSeverity = Literal["info", "warning", "hard"]
ReplayMode = Literal["replay", "rerun"]

SCORING_NODE_TYPES = {
    "question_scoring",
    "question_evaluation",
    "round_scoring",
    "round_evaluation",
    "final_scoring",
    "final_evaluation",
    "report_scoring",
}
LONG_TERM_MEMORY_KEYS = {
    "candidate_memories",
    "interviewer_memories",
    "agent_memories",
    "long_term_memories",
    "memory_ids",
}


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(default=2, ge=0, le=5)
    retryable_error_codes: list[str] = Field(default_factory=list)


class TokenBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_prompt_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    max_cost_cents: int | None = Field(default=None, ge=0)


class HarnessExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    user_id: int = Field(gt=0)
    interview_id: int = Field(gt=0)
    round_id: int | None = Field(default=None, gt=0)
    node_id: str = Field(min_length=1, max_length=128)
    node_type: str = Field(min_length=1, max_length=64)
    agent_type: str = Field(min_length=1, max_length=64)
    purpose: str = Field(min_length=1, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=128)
    model_params: JSONDict = Field(default_factory=dict)
    expected_schema: JSONDict | None = None
    schema_version: str | None = Field(default=None, max_length=64)
    context_refs: JSONDict = Field(default_factory=dict)
    retrieval_params: JSONDict = Field(default_factory=dict)
    input_payload: JSONDict = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    tool_name: str | None = Field(default=None, max_length=128)
    timeout_seconds: int = Field(default=45, ge=1, le=300)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    token_budget: TokenBudget | None = None
    execution_mode: ExecutionMode = "normal"
    idempotency_key: str | None = Field(default=None, max_length=128)
    source_trace_id: int | None = Field(default=None, gt=0)

    @field_validator("allowed_tools")
    @classmethod
    def normalize_allowed_tools(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_scoring_memory_inputs(self) -> HarnessExecutionRequest:
        if not is_scoring_node(self.node_type):
            return self
        illegal = find_long_term_memory_keys(
            {
                "context_refs": self.context_refs,
                "retrieval_params": self.retrieval_params,
                "input_payload": self.input_payload,
            }
        )
        if illegal:
            joined = ", ".join(sorted(illegal))
            raise ValueError(f"scoring nodes cannot receive long-term memory inputs: {joined}")
        return self


class TraceEventResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int | None = None
    status: Literal["succeeded", "failed"]
    error_message: str | None = None


class RuleEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_name: str = Field(min_length=1, max_length=128)
    status: RuleStatus
    severity: RuleSeverity = "warning"
    evidence: JSONDict = Field(default_factory=dict)
    failure_reason: str | None = Field(default=None, max_length=1000)
    overall_grade: Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"] | None = None


class HarnessExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: int
    business_result: JSONDict | list[Any] | str | int | float | bool | None = None
    validation_status: ValidationStatus
    injected_context_summary: JSONDict = Field(default_factory=dict)
    tool_call_summary: JSONDict = Field(default_factory=dict)
    token_usage: JSONDict = Field(default_factory=dict)
    elapsed_ms: int | None = Field(default=None, ge=0)
    retry_records: list[JSONDict] = Field(default_factory=list)
    degradation_records: list[JSONDict] = Field(default_factory=list)
    rule_evaluations: list[RuleEvaluation] = Field(default_factory=list)
    checkpoint_id: int | None = None
    replay_run_id: int | None = None
    source_trace_id: int | None = None
    result_diff: JSONDict | None = None
    event_write_failed: bool = False
    status: HarnessStatus
    error_code: str | None = None
    error_detail: str | None = None


class CheckpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(gt=0)
    interview_id: int = Field(gt=0)
    round_id: int | None = Field(default=None, gt=0)
    trace_id: int | None = Field(default=None, gt=0)
    node_id: str = Field(min_length=1, max_length=128)
    checkpoint_type: str = Field(min_length=1, max_length=64)
    snapshot: JSONDict
    resume_version: str | None = Field(default=None, max_length=64)
    status: str = Field(default="available", max_length=32)


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_trace_id: int = Field(gt=0)
    mode: ReplayMode = "replay"
    parameters: JSONDict = Field(default_factory=dict)


def is_scoring_node(node_type: str) -> bool:
    normalized = node_type.strip().lower()
    return normalized in SCORING_NODE_TYPES or "scor" in normalized or "evaluation" in normalized


def find_long_term_memory_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in LONG_TERM_MEMORY_KEYS:
                found.add(str(key))
            found.update(find_long_term_memory_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(find_long_term_memory_keys(item))
    return found
