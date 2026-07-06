from __future__ import annotations

import inspect
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.api.internal_harness import _ensure_internal_access
from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.evolution.scheduler import create_run_from_trigger, run_daily_inspection
from app.evolution.triggers import TriggerType, build_manual_trigger
from app.repositories.users import UserRecord


class EvolutionRepositoryProtocol(Protocol):
    def list_evolution_runs(
        self,
        *,
        user_id: int,
        trigger_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> Sequence[Any]:
        ...

    def create_evolution_run(
        self,
        *,
        user_id: int | None,
        trigger_type: str,
        trigger_reason: str,
        scope_type: str,
        scope_key: str | None,
        sample_count: int,
        data_scope: dict[str, Any],
        anonymization_status: str,
        audit_metadata: dict[str, Any],
    ) -> Any:
        ...

    def list_evolution_candidates(
        self,
        *,
        user_id: int,
        status: str | None = None,
        risk_level: str | None = None,
        candidate_type: str | None = None,
        limit: int = 100,
    ) -> Sequence[Any]:
        ...

    def get_evolution_candidate(self, *, candidate_id: int, user_id: int) -> Any | None:
        ...

    def list_evolution_version_bundles(
        self,
        *,
        user_id: int,
        status: str | None = None,
        limit: int = 100,
    ) -> Sequence[Any]:
        ...

    def list_evolution_validation_runs(
        self,
        *,
        user_id: int,
        candidate_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> Sequence[Any]:
        ...

    def list_evolution_audit_events(
        self,
        *,
        user_id: int,
        run_id: int | None = None,
        candidate_id: int | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> Sequence[Any]:
        ...

    def count_completed_quality_signals(self) -> int:
        ...


class EvolutionListResponse(BaseModel):
    items: list[dict[str, Any]]


class EvolutionSummaryResponse(BaseModel):
    run_count: int = 0
    candidate_count: int = 0
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    latest_quality_signals: list[dict[str, Any]] = Field(default_factory=list)
    version_bundle_status: dict[str, int] = Field(default_factory=dict)


class EvolutionRunCreateRequest(BaseModel):
    trigger_type: TriggerType = "manual"
    trigger_reason: str = Field(min_length=1, max_length=500)
    scope_type: str = Field(default="global", max_length=100)
    scope_key: str | None = Field(default=None, max_length=200)
    sample_count: int = Field(default=0, ge=0)
    sample_scope: dict[str, Any] = Field(default_factory=dict)
    data_scope: dict[str, Any] = Field(default_factory=dict)
    anonymization_status: str = Field(default="anonymized", max_length=100)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


class EvolutionCandidateActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    manual_note: str | None = Field(default=None, max_length=1000)
    apply_after_approval: bool = False
    options: dict[str, Any] = Field(default_factory=dict)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


class EvolutionValidationRerunRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    manual_note: str | None = Field(default=None, max_length=1000)
    sample_count: int = Field(default=0, ge=0)
    options: dict[str, Any] = Field(default_factory=dict)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


CurrentUserDep = Depends(get_current_user)


def require_internal_evolution_access(
    current_user: UserRecord = CurrentUserDep,
) -> None:
    _ensure_internal_access(current_user)


router = APIRouter(
    prefix="/internal/evolution",
    tags=["internal-evolution"],
    dependencies=[Depends(require_internal_evolution_access)],
)


def get_evolution_repository() -> Iterator[EvolutionRepositoryProtocol]:
    try:
        from app.repositories.evolution import EvolutionRepository
    except ModuleNotFoundError as exc:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            message="Evolution repository is not available.",
        ) from exc

    with mysql_connection() as connection:
        yield EvolutionRepository(connection)


EvolutionRepositoryDep = Depends(get_evolution_repository)


@router.get("/summary", response_model=EvolutionSummaryResponse)
def get_evolution_summary(
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> EvolutionSummaryResponse:
    if hasattr(repository, "get_evolution_summary"):
        return EvolutionSummaryResponse(
            **_repo_call_optional(
                repository,
                "get_evolution_summary",
                user_id=current_user.id,
            )
            or {}
        )

    runs = _repo_call_list(repository, "list_evolution_runs", user_id=current_user.id, limit=100)
    candidates = _repo_call_list(
        repository,
        "list_evolution_candidates",
        user_id=current_user.id,
        limit=100,
    )
    bundles = _repo_call_list(
        repository,
        "list_evolution_version_bundles",
        user_id=current_user.id,
        limit=100,
    )
    return EvolutionSummaryResponse(
        run_count=len(runs),
        candidate_count=len(candidates),
        risk_distribution=_count_by_key(candidates, "risk_level"),
        version_bundle_status=_count_by_key(bundles, "status"),
    )


@router.get("/runs", response_model=EvolutionListResponse)
def list_evolution_runs(
    trigger_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> EvolutionListResponse:
    return EvolutionListResponse(
        items=_repo_call_list(
            repository,
            "list_evolution_runs",
            user_id=current_user.id,
            trigger_type=trigger_type,
            status=status_filter,
            limit=limit,
        )
    )


@router.post("/runs", response_model=dict[str, Any])
def create_evolution_run(
    request: EvolutionRunCreateRequest,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    try:
        if request.trigger_type == "daily_inspection":
            result = run_daily_inspection(
                repository,
                user_id=current_user.id,
                trigger_reason=request.trigger_reason,
                sample_count=request.sample_count,
                sample_scope=request.sample_scope or request.data_scope,
                anonymization_status=request.anonymization_status,
                audit_metadata=_audit_metadata(request, current_user),
            )
        else:
            trigger = build_manual_trigger(
                trigger_type=request.trigger_type,
                trigger_reason=request.trigger_reason,
                scope_type=request.scope_type,
                scope_key=request.scope_key,
                sample_count=request.sample_count,
                data_scope=request.data_scope or {"sample_scope": request.sample_scope},
                anonymization_status=request.anonymization_status,
                audit_metadata=_audit_metadata(request, current_user),
            )
            result = create_run_from_trigger(repository, user_id=current_user.id, trigger=trigger)
    except ValueError as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT,
            message=str(exc),
        ) from exc

    return _as_dict(result)


@router.post("/candidates/{candidate_id}/approve", response_model=dict[str, Any])
def approve_evolution_candidate(
    candidate_id: int,
    request: EvolutionCandidateActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    payload = request or EvolutionCandidateActionRequest()
    candidate = _candidate_or_404(repository, candidate_id=candidate_id, user_id=current_user.id)
    candidate_type = _candidate_type(candidate)
    risk_level = _risk_level(candidate)
    if candidate_type == "frontend_suggestion":
        raise AppError(
            ErrorCode.FORBIDDEN,
            status.HTTP_403_FORBIDDEN,
            message="Frontend suggestions cannot be approved for automatic application.",
        )
    if risk_level == "high" and payload.apply_after_approval:
        raise AppError(
            ErrorCode.FORBIDDEN,
            status.HTTP_403_FORBIDDEN,
            message="High-risk candidates require manual confirmation and cannot be auto-applied.",
        )

    return _repo_call_action(
        repository,
        ("approve_evolution_candidate", "approve_candidate"),
        candidate_id=candidate_id,
        user_id=current_user.id,
        approved_by=current_user.id,
        manual_note=payload.manual_note,
        reason=payload.reason,
        apply_after_approval=payload.apply_after_approval,
        options=payload.options,
        audit_metadata=_action_audit_metadata(payload, current_user, action="approve"),
    )


@router.post("/candidates/{candidate_id}/reject", response_model=dict[str, Any])
def reject_evolution_candidate(
    candidate_id: int,
    request: EvolutionCandidateActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    payload = request or EvolutionCandidateActionRequest()
    _candidate_or_404(repository, candidate_id=candidate_id, user_id=current_user.id)
    return _repo_call_action(
        repository,
        ("reject_evolution_candidate", "reject_candidate"),
        candidate_id=candidate_id,
        user_id=current_user.id,
        rejected_by=current_user.id,
        manual_note=payload.manual_note,
        reason=payload.reason,
        options=payload.options,
        audit_metadata=_action_audit_metadata(payload, current_user, action="reject"),
    )


@router.post("/candidates/{candidate_id}/rerun-validation", response_model=dict[str, Any])
def rerun_evolution_candidate_validation(
    candidate_id: int,
    request: EvolutionValidationRerunRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    payload = request or EvolutionValidationRerunRequest()
    _candidate_or_404(repository, candidate_id=candidate_id, user_id=current_user.id)
    return _repo_call_action(
        repository,
        ("rerun_evolution_candidate_validation", "create_evolution_validation_run"),
        candidate_id=candidate_id,
        user_id=current_user.id,
        validation_type="manual_rerun",
        status="pending",
        sample_count=payload.sample_count,
        reason=payload.reason,
        manual_note=payload.manual_note,
        options=payload.options,
        details={"rerun_requested": True, "options": payload.options},
        audit_metadata=_action_audit_metadata(payload, current_user, action="rerun_validation"),
    )


@router.post("/candidates/{candidate_id}/rollback", response_model=dict[str, Any])
def rollback_evolution_candidate(
    candidate_id: int,
    request: EvolutionCandidateActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    payload = request or EvolutionCandidateActionRequest()
    _candidate_or_404(repository, candidate_id=candidate_id, user_id=current_user.id)
    return _repo_call_action(
        repository,
        ("rollback_evolution_candidate", "rollback_candidate"),
        candidate_id=candidate_id,
        user_id=current_user.id,
        rolled_back_by=current_user.id,
        manual_note=payload.manual_note,
        reason=payload.reason,
        options=payload.options,
        audit_metadata=_action_audit_metadata(payload, current_user, action="rollback"),
    )


@router.post("/frontend-suggestions/{candidate_id}/mark-handled", response_model=dict[str, Any])
def mark_frontend_suggestion_handled(
    candidate_id: int,
    request: EvolutionCandidateActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    payload = request or EvolutionCandidateActionRequest()
    candidate = _candidate_or_404(repository, candidate_id=candidate_id, user_id=current_user.id)
    if _candidate_type(candidate) != "frontend_suggestion":
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT,
            message="Only frontend suggestions can be marked as handled.",
        )
    return _repo_call_action(
        repository,
        (
            "mark_evolution_frontend_suggestion_handled",
            "mark_frontend_suggestion_handled",
        ),
        candidate_id=candidate_id,
        user_id=current_user.id,
        handled_by=current_user.id,
        manual_note=payload.manual_note,
        reason=payload.reason,
        options=payload.options,
        audit_metadata=_action_audit_metadata(
            payload,
            current_user,
            action="mark_frontend_handled",
        ),
    )


@router.post(
    "/frontend-suggestions/{candidate_id}/request-regeneration",
    response_model=dict[str, Any],
)
def request_frontend_suggestion_regeneration(
    candidate_id: int,
    request: EvolutionCandidateActionRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    payload = request or EvolutionCandidateActionRequest()
    candidate = _candidate_or_404(repository, candidate_id=candidate_id, user_id=current_user.id)
    if _candidate_type(candidate) != "frontend_suggestion":
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT,
            message="Only frontend suggestions can request regeneration.",
        )
    return _repo_call_action(
        repository,
        (
            "request_evolution_frontend_suggestion_regeneration",
            "request_frontend_suggestion_regeneration",
        ),
        candidate_id=candidate_id,
        user_id=current_user.id,
        requested_by=current_user.id,
        manual_note=payload.manual_note,
        reason=payload.reason,
        options=payload.options,
        audit_metadata=_action_audit_metadata(
            payload,
            current_user,
            action="request_frontend_regeneration",
        ),
    )


@router.get("/candidates", response_model=EvolutionListResponse)
def list_evolution_candidates(
    status_filter: str | None = Query(default=None, alias="status"),
    risk_level: str | None = Query(default=None),
    candidate_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> EvolutionListResponse:
    return EvolutionListResponse(
        items=_repo_call_list(
            repository,
            "list_evolution_candidates",
            user_id=current_user.id,
            status=status_filter,
            risk_level=risk_level,
            candidate_type=candidate_type,
            limit=limit,
        )
    )


@router.get("/candidates/{candidate_id}")
def get_evolution_candidate(
    candidate_id: int,
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> dict[str, Any]:
    candidate = _repo_call_optional(
        repository,
        "get_evolution_candidate",
        candidate_id=candidate_id,
        user_id=current_user.id,
    )
    if candidate is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return candidate


@router.get("/version-bundles", response_model=EvolutionListResponse)
def list_evolution_version_bundles(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> EvolutionListResponse:
    return EvolutionListResponse(
        items=_repo_call_list(
            repository,
            "list_evolution_version_bundles",
            user_id=current_user.id,
            status=status_filter,
            limit=limit,
        )
    )


@router.get("/validation-runs", response_model=EvolutionListResponse)
def list_evolution_validation_runs(
    candidate_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> EvolutionListResponse:
    return EvolutionListResponse(
        items=_repo_call_list(
            repository,
            "list_evolution_validation_runs",
            user_id=current_user.id,
            candidate_id=candidate_id,
            status=status_filter,
            limit=limit,
        )
    )


@router.get("/audit-events", response_model=EvolutionListResponse)
def list_evolution_audit_events(
    run_id: int | None = Query(default=None),
    candidate_id: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: UserRecord = CurrentUserDep,
    repository: EvolutionRepositoryProtocol = EvolutionRepositoryDep,
) -> EvolutionListResponse:
    return EvolutionListResponse(
        items=_repo_call_list(
            repository,
            "list_evolution_audit_events",
            user_id=current_user.id,
            run_id=run_id,
            candidate_id=candidate_id,
            event_type=event_type,
            limit=limit,
        )
    )


def _audit_metadata(
    request: EvolutionRunCreateRequest,
    current_user: UserRecord,
) -> dict[str, Any]:
    metadata = dict(request.audit_metadata)
    metadata.update(
        {
            "triggered_by_user_id": current_user.id,
            "triggered_by_username": current_user.username,
            "source": "internal_evolution_api",
        }
    )
    return metadata


def _action_audit_metadata(
    request: EvolutionCandidateActionRequest | EvolutionValidationRerunRequest,
    current_user: UserRecord,
    *,
    action: str,
) -> dict[str, Any]:
    metadata = dict(request.audit_metadata)
    metadata.update(
        {
            "action": action,
            "triggered_by_user_id": current_user.id,
            "triggered_by_username": current_user.username,
            "source": "internal_evolution_api",
        }
    )
    return metadata


def _candidate_or_404(
    repository: Any,
    *,
    candidate_id: int,
    user_id: int,
) -> dict[str, Any]:
    candidate = _repo_call_optional(
        repository,
        "get_evolution_candidate",
        candidate_id=candidate_id,
        user_id=user_id,
    )
    if candidate is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return candidate


def _candidate_type(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("candidate_type") or candidate.get("type") or "").lower()


def _risk_level(candidate: Mapping[str, Any]) -> str:
    return str(candidate.get("risk_level") or "").lower()


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
        message=f"Evolution repository action is not available: {method_names[0]}",
    )


def _call_repository(repository: Any, method_name: str, **kwargs: Any) -> Any:
    if not hasattr(repository, method_name):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            message=f"Evolution repository method is not available: {method_name}",
        )
    method = getattr(repository, method_name)
    try:
        return method(**_filter_kwargs(method, kwargs))
    except AppError:
        raise


def _filter_kwargs(method: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(method)
    parameters = signature.parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in parameters}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise AppError(
        ErrorCode.INTERNAL_ERROR,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Evolution repository returned an unsupported record type.",
    )


def _count_by_key(items: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts
