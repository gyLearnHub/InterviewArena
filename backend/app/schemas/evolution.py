from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EvolutionVersionBundleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    bundle_key: str
    parent_bundle_id: int | None = None
    scope_type: str
    scope_key: str | None = None
    status: str
    risk_level: str
    content_hash: str
    diff: dict[str, Any]
    validation_summary: dict[str, Any]
    rollback_point: dict[str, Any] | None = None
    created_by_run_id: int | None = None
    created_at: datetime | None = None
    activated_at: datetime | None = None


class EvolutionQualitySignalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int
    interview_id: int
    version_bundle_id: int | None = None
    job_family: str | None = None
    signal_type: str
    severity: str
    metrics: dict[str, Any]
    hard_trigger: bool
    threshold_trigger: bool
    source_refs: dict[str, Any]
    created_at: datetime | None = None


class EvolutionOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_bundle_count: int
    run_count: int
    candidate_count: int
    quality_signal_count: int
    candidate_risk_distribution: dict[str, int]


class EvolutionRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int | None = None
    dedupe_key: str | None = None
    trigger_type: str
    trigger_reason: str
    scope_type: str
    scope_key: str | None = None
    sample_count: int
    data_scope: dict[str, Any]
    anonymization_status: str
    audit_metadata: dict[str, Any]
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class EvolutionCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    run_id: int
    candidate_type: str
    target_artifact_key: str | None = None
    risk_level: str
    status: str
    proposal: dict[str, Any]
    diff: dict[str, Any]
    impact_scope: dict[str, Any]
    root_cause: dict[str, Any]
    validation_summary: dict[str, Any] | None = None
    approval_status: str
    approved_by: int | None = None
    approved_at: datetime | None = None
    manual_note: str | None = None
    rollback_point: dict[str, Any] | None = None
    application_result: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EvolutionValidationRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    candidate_id: int
    validation_type: str
    status: str
    sample_count: int
    baseline_bundle_id: int | None = None
    candidate_bundle_id: int | None = None
    hard_rule_result: dict[str, Any]
    soft_rule_diff: dict[str, Any]
    schema_result: dict[str, Any]
    api_contract_result: dict[str, Any]
    report_quality_diff: dict[str, Any]
    repeat_rate_diff: dict[str, Any]
    score_distribution_diff: dict[str, Any]
    test_result: dict[str, Any]
    details: dict[str, Any]
    created_at: datetime | None = None


class EvolutionAuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    event_type: str
    run_id: int | None = None
    candidate_id: int | None = None
    validation_run_id: int | None = None
    version_bundle_id: int | None = None
    actor_user_id: int | None = None
    metadata: dict[str, Any]
    created_at: datetime | None = None
