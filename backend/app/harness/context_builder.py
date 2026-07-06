from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.harness.contracts import (
    HarnessExecutionRequest,
    find_long_term_memory_keys,
    is_scoring_node,
)


class ContextIsolationError(RuntimeError):
    pass


class ContextBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False
    degradation_reason: str | None = None


class ContextBuilder:
    def build(self, request: HarnessExecutionRequest) -> ContextBuildResult:
        illegal = find_long_term_memory_keys(
            {
                "context_refs": request.context_refs,
                "retrieval_params": request.retrieval_params,
                "input_payload": request.input_payload,
            }
        )
        if is_scoring_node(request.node_type) and illegal:
            joined = ", ".join(sorted(illegal))
            raise ContextIsolationError(f"scoring context contains long-term memory: {joined}")
        summary = {
            "context_ref_keys": sorted(request.context_refs.keys()),
            "retrieval_param_keys": sorted(request.retrieval_params.keys()),
            "has_long_term_memory": bool(illegal),
            "scoring_node": is_scoring_node(request.node_type),
        }
        return ContextBuildResult(
            context={
                "refs": request.context_refs,
                "retrieval_params": request.retrieval_params,
            },
            summary=summary,
        )
