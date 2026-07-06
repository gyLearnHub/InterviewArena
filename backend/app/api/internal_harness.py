import inspect
import os
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.core.errors import AppError, ErrorCode
from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.users import UserRecord

router = APIRouter(prefix="/internal/harness", tags=["internal-harness"])
CurrentUserDep = Depends(get_current_user)

SCORING_NODE_TYPES = {"question_evaluation", "round_evaluation", "final_evaluation", "scoring"}
FORBIDDEN_SCORING_CONTEXT_KEYS = {
    "candidate_memories",
    "interviewer_memories",
    "agent_memories",
    "long_term_memories",
}
DEFAULT_ALLOWED_TOOLS = {
    "round_question_generator",
    "question_evaluator",
    "round_evaluator",
    "final_evaluator",
    "context_retriever",
    "checkpoint_writer",
    "duplicate_question_detector",
    "memory_write_tracker",
}
HARD_RULE_NAMES = {
    "context_isolation",
    "score_evidence",
    "round_completeness",
    "owner_isolation",
}


class HarnessRepositoryProtocol(Protocol):
    def list_traces(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
        limit: int = 100,
    ) -> Sequence[Any]:
        ...

    def get_trace(self, trace_id: int, *, user_id: int | None = None) -> Any | None:
        ...

    def list_checkpoints(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
    ) -> Sequence[Any]:
        ...

    def list_rule_evaluations(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
    ) -> Sequence[Any]:
        ...

    def list_improvement_candidates(
        self,
        *,
        user_id: int,
        status: str | None = None,
    ) -> Sequence[Any]:
        ...


class HarnessActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    options: dict[str, Any] = Field(default_factory=dict)


class HarnessListResponse(BaseModel):
    items: list[dict[str, Any]]


class HarnessActionResponse(BaseModel):
    replay_run_id: int | str | None = None
    source_trace_id: int | str | None = None
    source_node_id: int | str | None = None
    status: str
    result: dict[str, Any] | None = None


def get_harness_repository() -> Iterator[HarnessRepositoryProtocol]:
    try:
        from app.repositories.harness import HarnessRepository
    except ModuleNotFoundError as exc:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            message="Harness repository is not available.",
        ) from exc

    with mysql_connection() as connection:
        yield HarnessRepository(connection)


HarnessRepositoryDep = Depends(get_harness_repository)


@router.get("/interviews/{interview_id}/traces", response_model=HarnessListResponse)
def list_interview_traces(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> HarnessListResponse:
    _ensure_internal_access(current_user)
    items = _repo_call_list(
        repository,
        "list_traces",
        interview_id=interview_id,
        user_id=current_user.id,
    )
    return HarnessListResponse(items=items)


@router.get("/traces/{trace_id}")
def get_trace_detail(
    trace_id: int,
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> dict[str, Any]:
    _ensure_internal_access(current_user)
    trace = _repo_call_optional(repository, "get_trace", trace_id=trace_id, user_id=current_user.id)
    if trace is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    _assert_trace_belongs_to_user(repository, trace, current_user.id)
    return trace


@router.post("/traces/{trace_id}/replay", response_model=HarnessActionResponse)
def replay_trace(
    trace_id: int,
    request: HarnessActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> HarnessActionResponse:
    _ensure_internal_access(current_user)
    trace = _repo_call_optional(repository, "get_trace", trace_id=trace_id, user_id=current_user.id)
    if trace is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    _assert_trace_belongs_to_user(repository, trace, current_user.id)
    payload = request or HarnessActionRequest()
    result = _repo_call_action(
        repository,
        ("replay_trace", "create_replay_run"),
        trace_id=trace_id,
        user_id=current_user.id,
        reason=payload.reason,
        options=payload.options,
        mode="replay",
    )
    return _to_action_response(result, source_trace_id=trace_id)


@router.post("/nodes/{node_id}/rerun", response_model=HarnessActionResponse)
def rerun_node(
    node_id: str,
    request: HarnessActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> HarnessActionResponse:
    _ensure_internal_access(current_user)
    payload = request or HarnessActionRequest()
    result = _repo_call_action(
        repository,
        ("rerun_node", "create_replay_run"),
        node_id=node_id,
        user_id=current_user.id,
        reason=payload.reason,
        options=payload.options,
        mode="rerun",
    )
    return _to_action_response(result, source_node_id=node_id)


@router.get("/interviews/{interview_id}/evaluations", response_model=HarnessListResponse)
def list_interview_evaluations(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> HarnessListResponse:
    _ensure_internal_access(current_user)
    items = _repo_call_list(
        repository,
        "list_rule_evaluations",
        interview_id=interview_id,
        user_id=current_user.id,
    )
    return HarnessListResponse(items=items)


@router.get("/interviews/{interview_id}/checkpoints", response_model=HarnessListResponse)
def list_interview_checkpoints(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> HarnessListResponse:
    _ensure_internal_access(current_user)
    items = _repo_call_list(
        repository,
        "list_checkpoints",
        interview_id=interview_id,
        user_id=current_user.id,
    )
    return HarnessListResponse(items=items)


@router.get("/improvement-candidates", response_model=HarnessListResponse)
def list_improvement_candidates(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: UserRecord = CurrentUserDep,
    repository: HarnessRepositoryProtocol = HarnessRepositoryDep,
) -> HarnessListResponse:
    _ensure_internal_access(current_user)
    items = _repo_call_list(
        repository,
        "list_improvement_candidates",
        user_id=current_user.id,
        status=status_filter,
    )
    return HarnessListResponse(items=items)


def require_trace_created(trace: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if trace is None:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            message="Trace main record could not be created.",
        )
    return trace


def mark_event_write_failed(trace: dict[str, Any], error: str) -> dict[str, Any]:
    updated = dict(trace)
    updated["event_write_failed"] = True
    updated["event_write_error"] = error
    return updated


def validate_scoring_context_isolation(node_type: str, context: Mapping[str, Any]) -> None:
    if node_type not in SCORING_NODE_TYPES:
        return
    leaked_keys = sorted(key for key in FORBIDDEN_SCORING_CONTEXT_KEYS if context.get(key))
    if leaked_keys:
        raise AppError(
            ErrorCode.FORBIDDEN,
            status.HTTP_403_FORBIDDEN,
            message="Scoring nodes cannot receive long-term memory context.",
            details={"forbidden_keys": leaked_keys},
        )


def validate_tool_whitelist(
    tool_name: str,
    allowed_tools: set[str] | None = None,
) -> None:
    allowed = allowed_tools or DEFAULT_ALLOWED_TOOLS
    if tool_name not in allowed:
        raise AppError(
            ErrorCode.FORBIDDEN,
            status.HTTP_403_FORBIDDEN,
            message="Tool is not allowed for this harness node.",
            details={"tool_name": tool_name},
        )


def evaluate_hard_rules(evaluations: Sequence[Mapping[str, Any]]) -> str:
    for item in evaluations:
        name = str(item.get("rule_name") or item.get("name") or "")
        result = str(item.get("status") or item.get("result") or "").lower()
        hard = bool(item.get("hard_rule")) or name in HARD_RULE_NAMES
        if hard and result in {"failed", "fail"}:
            return "FAIL"
    if any(
        str(item.get("status") or item.get("result") or "").lower() == "warning"
        for item in evaluations
    ):
        return "PASS_WITH_WARNINGS"
    return "PASS"


def _ensure_internal_access(user: UserRecord) -> None:
    _ensure_internal_api_enabled()
    if not _is_internal_harness_user(user):
        raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)


def _ensure_internal_api_enabled() -> None:
    if os.getenv("HARNESS_INTERNAL_API_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)


def _is_internal_harness_user(user: UserRecord) -> bool:
    allowed_ids = _csv_env("HARNESS_INTERNAL_USER_IDS")
    allowed_usernames = _csv_env("HARNESS_INTERNAL_USERNAMES")
    if str(user.id) in allowed_ids:
        return True
    return user.username in allowed_usernames


def _csv_env(name: str) -> set[str]:
    value = os.getenv(name, "")
    return {item.strip() for item in value.split(",") if item.strip()}


def _repo_call_list(repository: Any, method_name: str, **kwargs: Any) -> list[dict[str, Any]]:
    result = _call_repository(repository, method_name, **kwargs)
    if result is None:
        return []
    return [_as_dict(item) for item in result]


def _repo_call_optional(repository: Any, method_name: str, **kwargs: Any) -> dict[str, Any] | None:
    result = _call_repository(repository, method_name, **kwargs)
    if result is None:
        return None
    return _as_dict(result)


def _repo_call_action(
    repository: Any,
    method_names: tuple[str, ...],
    **kwargs: Any,
) -> dict[str, Any]:
    for method_name in method_names:
        if hasattr(repository, method_name):
            result = _call_repository(repository, method_name, **kwargs)
            return _as_dict(result or {"status": "accepted"})
    raise AppError(
        ErrorCode.INTERNAL_ERROR,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        message="Harness replay/rerun repository operation is not available.",
    )


def _call_repository(repository: Any, method_name: str, **kwargs: Any) -> Any:
    if not hasattr(repository, method_name):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            message=f"Harness repository method is not available: {method_name}",
        )
    method = getattr(repository, method_name)
    call_kwargs = _filter_kwargs(method, kwargs)
    try:
        return method(**call_kwargs)
    except AppError:
        raise


def _filter_kwargs(method: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(method)
    parameters = signature.parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in parameters}


def _assert_trace_belongs_to_user(
    repository: Any,
    trace: Mapping[str, Any],
    user_id: int,
) -> None:
    trace_user_id = trace.get("user_id")
    if trace_user_id is not None:
        if int(trace_user_id) != user_id:
            raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)
        return

    interview_id = trace.get("interview_id")
    if interview_id is not None and hasattr(repository, "interview_belongs_to_user"):
        belongs = _call_repository(
            repository,
            "interview_belongs_to_user",
            interview_id=int(interview_id),
            user_id=user_id,
        )
        if belongs:
            return

    raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)


def _to_action_response(
    result: Mapping[str, Any],
    *,
    source_trace_id: int | None = None,
    source_node_id: str | None = None,
) -> HarnessActionResponse:
    return HarnessActionResponse(
        replay_run_id=result.get("replay_run_id") or result.get("id"),
        source_trace_id=result.get("source_trace_id") or source_trace_id,
        source_node_id=result.get("source_node_id") or source_node_id,
        status=str(result.get("status") or "accepted"),
        result=_as_dict(result.get("result")) if result.get("result") is not None else None,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, BaseModel):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise AppError(
        ErrorCode.INTERNAL_ERROR,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Harness repository returned an unsupported record type.",
    )
