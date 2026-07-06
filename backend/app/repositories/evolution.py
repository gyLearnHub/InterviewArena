from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

DEFAULT_VERSION_BUNDLE_KEY = "global-default-v3.2-bootstrap"


@dataclass(frozen=True)
class EvolutionVersionBundleRecord:
    id: int
    bundle_key: str
    parent_bundle_id: int | None
    scope_type: str
    scope_key: str | None
    status: str
    risk_level: str
    content_hash: str
    diff: dict[str, Any]
    validation_summary: dict[str, Any]
    rollback_point: dict[str, Any] | None
    created_by_run_id: int | None
    created_at: datetime | None
    activated_at: datetime | None


@dataclass(frozen=True)
class EvolutionQualitySignalRecord:
    id: int
    user_id: int
    interview_id: int
    version_bundle_id: int | None
    job_family: str | None
    signal_type: str
    severity: str
    metrics: dict[str, Any]
    hard_trigger: bool
    threshold_trigger: bool
    source_refs: dict[str, Any]
    created_at: datetime | None


@dataclass(frozen=True)
class EvolutionRunRecord:
    id: int
    user_id: int | None
    dedupe_key: str | None
    trigger_type: str
    trigger_reason: str
    scope_type: str
    scope_key: str | None
    sample_count: int
    data_scope: dict[str, Any]
    anonymization_status: str
    audit_metadata: dict[str, Any]
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


@dataclass(frozen=True)
class EvolutionCandidateRecord:
    id: int
    run_id: int
    candidate_type: str
    target_artifact_key: str | None
    risk_level: str
    status: str
    proposal: dict[str, Any]
    diff: dict[str, Any]
    impact_scope: dict[str, Any]
    root_cause: dict[str, Any]
    validation_summary: dict[str, Any] | None
    approval_status: str
    approved_by: int | None
    approved_at: datetime | None
    manual_note: str | None
    rollback_point: dict[str, Any] | None
    application_result: dict[str, Any] | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class EvolutionValidationRunRecord:
    id: int
    candidate_id: int
    validation_type: str
    status: str
    sample_count: int
    baseline_bundle_id: int | None
    candidate_bundle_id: int | None
    hard_rule_result: dict[str, Any]
    soft_rule_diff: dict[str, Any]
    schema_result: dict[str, Any]
    api_contract_result: dict[str, Any]
    report_quality_diff: dict[str, Any]
    repeat_rate_diff: dict[str, Any]
    score_distribution_diff: dict[str, Any]
    test_result: dict[str, Any]
    details: dict[str, Any]
    created_at: datetime | None


@dataclass(frozen=True)
class EvolutionAuditEventRecord:
    id: int
    event_type: str
    run_id: int | None
    candidate_id: int | None
    validation_run_id: int | None
    version_bundle_id: int | None
    actor_user_id: int | None
    metadata: dict[str, Any]
    created_at: datetime | None


@dataclass(frozen=True)
class EvolutionArtifactRecord:
    id: int
    bundle_id: int
    artifact_type: str
    artifact_key: str
    version: str
    content: dict[str, Any]
    content_hash: str
    parent_artifact_id: int | None
    diff: dict[str, Any]
    risk_level: str
    created_at: datetime | None


class EvolutionRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get_active_version_bundle(
        self,
        *,
        scope_type: str = "global",
        scope_key: str | None = None,
    ) -> EvolutionVersionBundleRecord | None:
        scope_condition = "scope_key IS NULL" if scope_key is None else "scope_key = %s"
        params: tuple[Any, ...] = (scope_type,) if scope_key is None else (scope_type, scope_key)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, bundle_key, parent_bundle_id, scope_type, scope_key, status,
                       risk_level, content_hash, diff, validation_summary, rollback_point,
                       created_by_run_id, created_at, activated_at
                FROM evolution_version_bundles
                WHERE scope_type = %s
                  AND {scope_condition}
                  AND status = 'active'
                ORDER BY activated_at DESC, id DESC
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
        return _to_version_bundle(row)

    def get_version_bundle_by_key(
        self,
        bundle_key: str,
    ) -> EvolutionVersionBundleRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_key, parent_bundle_id, scope_type, scope_key, status,
                       risk_level, content_hash, diff, validation_summary, rollback_point,
                       created_by_run_id, created_at, activated_at
                FROM evolution_version_bundles
                WHERE bundle_key = %s
                LIMIT 1
                """,
                (bundle_key,),
            )
            row = cursor.fetchone()
        return _to_version_bundle(row)

    def get_version_bundle(self, bundle_id: int) -> EvolutionVersionBundleRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_key, parent_bundle_id, scope_type, scope_key, status,
                       risk_level, content_hash, diff, validation_summary, rollback_point,
                       created_by_run_id, created_at, activated_at
                FROM evolution_version_bundles
                WHERE id = %s
                LIMIT 1
                """,
                (bundle_id,),
            )
            row = cursor.fetchone()
        return _to_version_bundle(row)

    def get_or_create_active_default_version_bundle(self) -> EvolutionVersionBundleRecord:
        existing = self.get_version_bundle_by_key(DEFAULT_VERSION_BUNDLE_KEY)
        if existing is not None:
            return existing
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO evolution_version_bundles (
                        bundle_key, parent_bundle_id, scope_type, scope_key, status,
                        risk_level, content_hash, diff, validation_summary,
                        rollback_point, activated_at
                    )
                    VALUES (
                        %s, NULL, 'global', NULL, 'active', 'low',
                        SHA2(%s, 256), %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        DEFAULT_VERSION_BUNDLE_KEY,
                        DEFAULT_VERSION_BUNDLE_KEY,
                        _json_dumps({"reason": "v3.2 bootstrap default bundle"}),
                        _json_dumps({"status": "bootstrap", "phase": "stage_1"}),
                        _json_dumps({"type": "bootstrap_default"}),
                    ),
                )
        except Exception as exc:
            if not _is_duplicate_key_error(exc):
                raise
        created = self.get_version_bundle_by_key(DEFAULT_VERSION_BUNDLE_KEY)
        if created is None:
            raise RuntimeError("default evolution version bundle was not created")
        return created

    def create_quality_signal(
        self,
        *,
        user_id: int,
        interview_id: int,
        version_bundle_id: int | None,
        job_family: str | None,
        signal_type: str,
        severity: str,
        metrics: dict[str, Any],
        hard_trigger: bool,
        threshold_trigger: bool,
        source_refs: dict[str, Any],
    ) -> EvolutionQualitySignalRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evolution_quality_signals (
                    user_id, interview_id, version_bundle_id, job_family, signal_type,
                    severity, metrics, hard_trigger, threshold_trigger, source_refs
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    interview_id,
                    version_bundle_id,
                    job_family,
                    signal_type,
                    severity,
                    _json_dumps(metrics),
                    hard_trigger,
                    threshold_trigger,
                    _json_dumps(source_refs),
                ),
            )
            signal_id = int(cursor.lastrowid)
        return EvolutionQualitySignalRecord(
            id=signal_id,
            user_id=user_id,
            interview_id=interview_id,
            version_bundle_id=version_bundle_id,
            job_family=job_family,
            signal_type=signal_type,
            severity=severity,
            metrics=metrics,
            hard_trigger=hard_trigger,
            threshold_trigger=threshold_trigger,
            source_refs=source_refs,
            created_at=datetime.utcnow(),
        )

    def create_quality_signal_idempotent(
        self,
        **payload: Any,
    ) -> EvolutionQualitySignalRecord:
        try:
            return self.create_quality_signal(**payload)
        except Exception as exc:
            if not _is_duplicate_key_error(exc):
                raise
            existing = self.get_quality_signal_for_interview(
                int(payload["interview_id"]),
                str(payload["signal_type"]),
            )
            if existing is None:
                raise
            return existing

    def get_quality_signal_for_interview(
        self,
        interview_id: int,
        signal_type: str,
    ) -> EvolutionQualitySignalRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, interview_id, version_bundle_id, job_family,
                       signal_type, severity, metrics, hard_trigger, threshold_trigger,
                       source_refs, created_at
                FROM evolution_quality_signals
                WHERE interview_id = %s AND signal_type = %s
                LIMIT 1
                """,
                (interview_id, signal_type),
            )
            row = cursor.fetchone()
        return _to_quality_signal(row)

    def get_interview_harness_summary(self, interview_id: int) -> dict[str, Any]:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_rules,
                        SUM(CASE WHEN status <> 'passed' THEN 1 ELSE 0 END) AS failed_rules,
                        SUM(
                            CASE
                                WHEN status <> 'passed'
                                 AND severity IN ('hard', 'critical', 'blocker')
                                THEN 1 ELSE 0
                            END
                        ) AS failed_hard_rules
                        ,
                        SUM(
                            CASE
                                WHEN status <> 'passed'
                                 AND (
                                      LOWER(rule_name) LIKE '%overreach%'
                                   OR LOWER(rule_name) LIKE '%boundary%'
                                   OR LOWER(COALESCE(failure_reason, '')) LIKE '%overreach%'
                                   OR LOWER(COALESCE(failure_reason, '')) LIKE '%boundary%'
                                   OR LOWER(CAST(evidence AS CHAR)) LIKE '%overreach%'
                                   OR LOWER(CAST(evidence AS CHAR)) LIKE '%boundary%'
                                   OR CAST(evidence AS CHAR) LIKE '%越权%'
                                 )
                                THEN 1 ELSE 0
                            END
                        ) AS agent_overreach_count
                    FROM harness_rule_evaluations
                    WHERE interview_id = %s
                    """,
                    (interview_id,),
                )
                rule_row = cursor.fetchone() or {}
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_traces,
                        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_traces,
                        SUM(
                            CASE
                                WHEN validation_status = 'failed'
                                  OR LOWER(COALESCE(error_code, '')) LIKE '%json%'
                                  OR LOWER(COALESCE(error_code, '')) LIKE '%schema%'
                                  OR LOWER(COALESCE(error_code, '')) LIKE '%format%'
                                  OR LOWER(COALESCE(error_detail, '')) LIKE '%json%'
                                  OR LOWER(COALESCE(error_detail, '')) LIKE '%schema%'
                                  OR LOWER(COALESCE(error_detail, '')) LIKE '%format%'
                                THEN 1 ELSE 0
                            END
                        ) AS llm_output_format_error_count,
                        SUM(
                            CASE WHEN JSON_LENGTH(degradation_records) > 0 THEN 1 ELSE 0 END
                        ) AS degradation_count,
                        SUM(
                            CASE
                                WHEN status = 'failed'
                                 AND JSON_LENGTH(degradation_records) > 0
                                THEN 1 ELSE 0
                            END
                        ) AS blocking_degradation_count
                    FROM harness_traces
                    WHERE interview_id = %s
                    """,
                    (interview_id,),
                )
                trace_row = cursor.fetchone() or {}
                cursor.execute(
                    """
                    SELECT COUNT(*) AS negative_feedback_count
                    FROM harness_trace_events e
                    JOIN harness_traces t ON t.id = e.trace_id
                    WHERE t.interview_id = %s
                      AND (
                            LOWER(e.event_type) LIKE '%feedback%'
                         OR LOWER(e.event_type) LIKE '%rating%'
                         OR LOWER(e.event_type) LIKE '%thumb%'
                      )
                      AND (
                            LOWER(CAST(e.payload AS CHAR)) LIKE '%thumb_down%'
                         OR LOWER(CAST(e.payload AS CHAR)) LIKE '%thumbs_down%'
                         OR LOWER(CAST(e.payload AS CHAR)) LIKE '%dislike%'
                         OR LOWER(CAST(e.payload AS CHAR)) LIKE '%negative%'
                         OR LOWER(CAST(e.payload AS CHAR)) LIKE '%bad%'
                         OR CAST(e.payload AS CHAR) LIKE '%点踩%'
                         OR CAST(e.payload AS CHAR) LIKE '%差评%'
                      )
                    """,
                    (interview_id,),
                )
                feedback_row = cursor.fetchone() or {}
        except Exception:
            return {
                "available": False,
                "total_rules": 0,
                "failed_rules": 0,
                "failed_hard_rules": 0,
                "agent_overreach_count": 0,
                "total_traces": 0,
                "failed_traces": 0,
                "llm_output_format_error_count": 0,
                "degradation_count": 0,
                "blocking_degradation_count": 0,
                "negative_feedback_count": 0,
            }
        return {
            "available": True,
            "total_rules": int(rule_row.get("total_rules") or 0),
            "failed_rules": int(rule_row.get("failed_rules") or 0),
            "failed_hard_rules": int(rule_row.get("failed_hard_rules") or 0),
            "agent_overreach_count": int(rule_row.get("agent_overreach_count") or 0),
            "total_traces": int(trace_row.get("total_traces") or 0),
            "failed_traces": int(trace_row.get("failed_traces") or 0),
            "llm_output_format_error_count": int(
                trace_row.get("llm_output_format_error_count") or 0
            ),
            "degradation_count": int(trace_row.get("degradation_count") or 0),
            "blocking_degradation_count": int(trace_row.get("blocking_degradation_count") or 0),
            "negative_feedback_count": int(feedback_row.get("negative_feedback_count") or 0),
        }

    def get_evolution_overview(self) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM evolution_version_bundles")
            bundle_count = int((cursor.fetchone() or {}).get("count") or 0)
            cursor.execute("SELECT COUNT(*) AS count FROM evolution_runs")
            run_count = int((cursor.fetchone() or {}).get("count") or 0)
            cursor.execute("SELECT COUNT(*) AS count FROM evolution_candidates")
            candidate_count = int((cursor.fetchone() or {}).get("count") or 0)
            cursor.execute("SELECT COUNT(*) AS count FROM evolution_quality_signals")
            signal_count = int((cursor.fetchone() or {}).get("count") or 0)
            cursor.execute(
                """
                SELECT risk_level, COUNT(*) AS count
                FROM evolution_candidates
                GROUP BY risk_level
                """
            )
            risk_rows = cursor.fetchall()
        return {
            "version_bundle_count": bundle_count,
            "run_count": run_count,
            "candidate_count": candidate_count,
            "quality_signal_count": signal_count,
            "candidate_risk_distribution": {
                str(row["risk_level"]): int(row.get("count") or 0) for row in risk_rows
            },
        }

    def list_quality_signals(
        self,
        *,
        limit: int = 100,
        user_id: int | None = None,
        hard_trigger: bool | None = None,
        threshold_trigger: bool | None = None,
    ) -> list[EvolutionQualitySignalRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)
        if hard_trigger is not None:
            conditions.append("hard_trigger = %s")
            params.append(hard_trigger)
        if threshold_trigger is not None:
            conditions.append("threshold_trigger = %s")
            params.append(threshold_trigger)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, interview_id, version_bundle_id, job_family,
                       signal_type, severity, metrics, hard_trigger, threshold_trigger,
                       source_refs, created_at
                FROM evolution_quality_signals
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_quality_signal(row)) is not None]

    def count_completed_quality_signals(self) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM evolution_quality_signals
                WHERE signal_type = 'interview_completed'
                """
            )
            row = cursor.fetchone() or {}
        return int(row.get("count") or 0)

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
        audit_metadata: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
        status: str = "pending",
    ) -> EvolutionRunRecord:
        stable_dedupe_key = dedupe_key or _dedupe_key(
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            scope_type=scope_type,
            scope_key=scope_key,
            data_scope=data_scope,
        )
        existing = self.get_evolution_run_by_dedupe_key(stable_dedupe_key)
        if existing is not None:
            return existing
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO evolution_runs (
                        user_id, dedupe_key, trigger_type, trigger_reason, scope_type,
                        scope_key, sample_count, data_scope, anonymization_status,
                        audit_metadata, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        stable_dedupe_key,
                        trigger_type,
                        trigger_reason[:1000],
                        scope_type,
                        scope_key,
                        sample_count,
                        _json_dumps(data_scope),
                        anonymization_status,
                        _json_dumps(audit_metadata or {}),
                        status,
                    ),
                )
                run_id = int(cursor.lastrowid)
        except Exception as exc:
            if not _is_duplicate_key_error(exc):
                raise
            existing = self.get_evolution_run_by_dedupe_key(stable_dedupe_key)
            if existing is None:
                raise
            return existing
        run = self.get_evolution_run(run_id)
        if run is None:
            raise RuntimeError("evolution run was not created")
        self.record_evolution_audit_event(
            event_type="run_created",
            run_id=run.id,
            actor_user_id=user_id,
            metadata={
                "trigger_type": trigger_type,
                "trigger_reason": trigger_reason,
                "scope_type": scope_type,
                "scope_key": scope_key,
                "sample_count": sample_count,
                "data_scope": data_scope,
                "anonymization_status": anonymization_status,
                "audit_metadata": audit_metadata or {},
            },
        )
        return run

    def get_evolution_run(self, run_id: int) -> EvolutionRunRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, dedupe_key, trigger_type, trigger_reason, scope_type,
                       scope_key, sample_count, data_scope, anonymization_status,
                       audit_metadata, status, started_at, completed_at, error_message
                FROM evolution_runs
                WHERE id = %s
                LIMIT 1
                """,
                (run_id,),
            )
            row = cursor.fetchone()
        return _to_run(row)

    def get_evolution_run_by_dedupe_key(self, dedupe_key: str) -> EvolutionRunRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, dedupe_key, trigger_type, trigger_reason, scope_type,
                       scope_key, sample_count, data_scope, anonymization_status,
                       audit_metadata, status, started_at, completed_at, error_message
                FROM evolution_runs
                WHERE dedupe_key = %s
                LIMIT 1
                """,
                (dedupe_key,),
            )
            row = cursor.fetchone()
        return _to_run(row)

    def list_evolution_runs(
        self,
        *,
        user_id: int | None = None,
        trigger_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionRunRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            conditions.append("(user_id IS NULL OR user_id = %s)")
            params.append(user_id)
        if trigger_type is not None:
            conditions.append("trigger_type = %s")
            params.append(trigger_type)
        if status is not None:
            conditions.append("status = %s")
            params.append(status)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, dedupe_key, trigger_type, trigger_reason, scope_type,
                       scope_key, sample_count, data_scope, anonymization_status,
                       audit_metadata, status, started_at, completed_at, error_message
                FROM evolution_runs
                {where_clause}
                ORDER BY started_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_run(row)) is not None]

    def update_evolution_run_status(
        self,
        run_id: int,
        *,
        status: str,
        error_message: str | None = None,
        completed: bool = False,
    ) -> None:
        completed_assignment = ", completed_at = CURRENT_TIMESTAMP" if completed else ""
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE evolution_runs
                SET status = %s, error_message = %s{completed_assignment}
                WHERE id = %s
                """,
                (status, error_message[:1000] if error_message else None, run_id),
            )

    def merge_evolution_run_audit_metadata(
        self,
        run_id: int,
        metadata: dict[str, Any],
    ) -> None:
        current = self.get_evolution_run(run_id)
        if current is None:
            return
        merged = {**current.audit_metadata, **metadata}
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE evolution_runs
                SET audit_metadata = %s
                WHERE id = %s
                """,
                (_json_dumps(merged), run_id),
            )

    def record_evolution_audit_event(
        self,
        *,
        event_type: str,
        run_id: int | None = None,
        candidate_id: int | None = None,
        validation_run_id: int | None = None,
        version_bundle_id: int | None = None,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvolutionAuditEventRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evolution_audit_events (
                    event_type, run_id, candidate_id, validation_run_id,
                    version_bundle_id, actor_user_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event_type,
                    run_id,
                    candidate_id,
                    validation_run_id,
                    version_bundle_id,
                    actor_user_id,
                    _json_dumps(metadata or {}),
                ),
            )
            event_id = int(cursor.lastrowid)
        event = self.get_evolution_audit_event(event_id)
        if event is None:
            raise RuntimeError("evolution audit event was not created")
        return event

    def get_evolution_audit_event(self, event_id: int) -> EvolutionAuditEventRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, event_type, run_id, candidate_id, validation_run_id,
                       version_bundle_id, actor_user_id, metadata, created_at
                FROM evolution_audit_events
                WHERE id = %s
                LIMIT 1
                """,
                (event_id,),
            )
            row = cursor.fetchone()
        return _to_audit_event(row)

    def list_evolution_audit_events(
        self,
        *,
        user_id: int | None = None,
        run_id: int | None = None,
        candidate_id: int | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionAuditEventRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            conditions.append("(r.user_id IS NULL OR r.user_id = %s OR e.actor_user_id = %s)")
            params.extend([user_id, user_id])
        if run_id is not None:
            conditions.append("e.run_id = %s")
            params.append(run_id)
        if candidate_id is not None:
            conditions.append("e.candidate_id = %s")
            params.append(candidate_id)
        if event_type is not None:
            conditions.append("e.event_type = %s")
            params.append(event_type)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT e.id, e.event_type, e.run_id, e.candidate_id, e.validation_run_id,
                       e.version_bundle_id, e.actor_user_id, e.metadata, e.created_at
                FROM evolution_audit_events e
                LEFT JOIN evolution_runs r ON r.id = e.run_id
                {where_clause}
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_audit_event(row)) is not None]

    def create_candidate(
        self,
        *,
        run_id: int,
        candidate_type: str,
        target_artifact_key: str | None,
        risk_level: str,
        status: str,
        proposal: dict[str, Any],
        diff: dict[str, Any],
        impact_scope: dict[str, Any],
        root_cause: dict[str, Any],
        validation_summary: dict[str, Any] | None = None,
        approval_status: str = "pending",
        rollback_point: dict[str, Any] | None = None,
    ) -> EvolutionCandidateRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evolution_candidates (
                    run_id, candidate_type, target_artifact_key, risk_level, status,
                    proposal, diff, impact_scope, root_cause, validation_summary,
                    approval_status, rollback_point
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    candidate_type,
                    target_artifact_key,
                    risk_level,
                    status,
                    _json_dumps(proposal),
                    _json_dumps(diff),
                    _json_dumps(impact_scope),
                    _json_dumps(root_cause),
                    _json_dumps(validation_summary) if validation_summary is not None else None,
                    approval_status,
                    _json_dumps(rollback_point) if rollback_point is not None else None,
                ),
            )
            candidate_id = int(cursor.lastrowid)
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=None)
        if candidate is None:
            raise RuntimeError("evolution candidate was not created")
        self.record_evolution_audit_event(
            event_type="candidate_created",
            run_id=run_id,
            candidate_id=candidate.id,
            metadata={
                "candidate_type": candidate_type,
                "target_artifact_key": target_artifact_key,
                "risk_level": risk_level,
                "status": status,
                "impact_scope": impact_scope,
                "root_cause": root_cause,
            },
        )
        return candidate

    def get_evolution_candidate(
        self,
        *,
        candidate_id: int,
        user_id: int | None = None,
    ) -> EvolutionCandidateRecord | None:
        user_condition = ""
        params: list[Any] = [candidate_id]
        if user_id is not None:
            user_condition = "AND (r.user_id IS NULL OR r.user_id = %s)"
            params.append(user_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id, c.run_id, c.candidate_type, c.target_artifact_key,
                       c.risk_level, c.status, c.proposal, c.diff, c.impact_scope,
                       c.root_cause, c.validation_summary, c.approval_status,
                       c.approved_by, c.approved_at, c.manual_note, c.rollback_point,
                       c.application_result, c.created_at, c.updated_at
                FROM evolution_candidates c
                JOIN evolution_runs r ON r.id = c.run_id
                WHERE c.id = %s
                  {user_condition}
                LIMIT 1
                """,
                tuple(params),
            )
            row = cursor.fetchone()
        return _to_candidate(row)

    def list_evolution_candidates(
        self,
        *,
        user_id: int | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        candidate_type: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionCandidateRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            conditions.append("(r.user_id IS NULL OR r.user_id = %s)")
            params.append(user_id)
        if status is not None:
            conditions.append("c.status = %s")
            params.append(status)
        if risk_level is not None:
            conditions.append("c.risk_level = %s")
            params.append(risk_level)
        if candidate_type is not None:
            conditions.append("c.candidate_type = %s")
            params.append(candidate_type)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT c.id, c.run_id, c.candidate_type, c.target_artifact_key,
                       c.risk_level, c.status, c.proposal, c.diff, c.impact_scope,
                       c.root_cause, c.validation_summary, c.approval_status,
                       c.approved_by, c.approved_at, c.manual_note, c.rollback_point,
                       c.application_result, c.created_at, c.updated_at
                FROM evolution_candidates c
                JOIN evolution_runs r ON r.id = c.run_id
                {where_clause}
                ORDER BY c.created_at DESC, c.id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_candidate(row)) is not None]

    def update_candidate_status(
        self,
        candidate_id: int,
        *,
        status: str,
        validation_summary: dict[str, Any] | None = None,
        application_result: dict[str, Any] | None = None,
        rollback_point: dict[str, Any] | None = None,
        manual_note: str | None = None,
    ) -> None:
        assignments = ["status = %s"]
        params: list[Any] = [status]
        if validation_summary is not None:
            assignments.append("validation_summary = %s")
            params.append(_json_dumps(validation_summary))
        if application_result is not None:
            assignments.append("application_result = %s")
            params.append(_json_dumps(application_result))
        if rollback_point is not None:
            assignments.append("rollback_point = %s")
            params.append(_json_dumps(rollback_point))
        if manual_note is not None:
            assignments.append("manual_note = %s")
            params.append(manual_note)
        params.append(candidate_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE evolution_candidates SET {', '.join(assignments)} WHERE id = %s",
                tuple(params),
            )

    def approve_evolution_candidate(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        approved_by: int,
        manual_note: str | None = None,
        reason: str | None = None,
        apply_after_approval: bool = False,
        options: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> EvolutionCandidateRecord | dict[str, Any]:
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if candidate is None:
            raise ValueError("candidate not found")
        application_result = {
            "approved": True,
            "reason": reason,
            "apply_after_approval": apply_after_approval,
            "options": options or {},
            "audit_metadata": audit_metadata or {},
        }
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE evolution_candidates
                SET status = 'approved',
                    approval_status = 'approved',
                    approved_by = %s,
                    approved_at = CURRENT_TIMESTAMP,
                    manual_note = %s,
                    application_result = %s
                WHERE id = %s
                """,
                (approved_by, manual_note, _json_dumps(application_result), candidate_id),
            )
        self.record_evolution_audit_event(
            event_type="candidate_approved",
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            actor_user_id=approved_by,
            metadata=application_result,
        )
        if apply_after_approval:
            from app.evolution.applier import apply_candidate

            requested_options = options or {}
            scope_type = str(
                requested_options.get("scope_type")
                or candidate.impact_scope.get("scope_type")
                or "global"
            )
            scope_key = (
                requested_options.get("scope_key")
                or candidate.impact_scope.get("scope_key")
            )
            apply_candidate(
                self,
                candidate_id,
                manual_approval=True,
                scope_type=scope_type,
                scope_key=scope_key,
            )
        refreshed = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if refreshed is None:
            raise RuntimeError("approved evolution candidate could not be reloaded")
        return refreshed

    def reject_evolution_candidate(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        rejected_by: int,
        manual_note: str | None = None,
        reason: str | None = None,
        options: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> EvolutionCandidateRecord:
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if candidate is None:
            raise ValueError("candidate not found")
        application_result = {
            "rejected": True,
            "rejected_by": rejected_by,
            "reason": reason,
            "options": options or {},
            "audit_metadata": audit_metadata or {},
        }
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE evolution_candidates
                SET status = 'rejected',
                    approval_status = 'rejected',
                    manual_note = %s,
                    application_result = %s
                WHERE id = %s
                """,
                (manual_note, _json_dumps(application_result), candidate_id),
            )
        self.record_evolution_audit_event(
            event_type="candidate_rejected",
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            actor_user_id=rejected_by,
            metadata=application_result,
        )
        refreshed = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if refreshed is None:
            raise RuntimeError("rejected evolution candidate could not be reloaded")
        return refreshed

    def rerun_evolution_candidate_validation(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        validation_type: str = "manual_rerun",
        sample_count: int = 0,
        reason: str | None = None,
        manual_note: str | None = None,
        options: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> EvolutionValidationRunRecord:
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if candidate is None:
            raise ValueError("candidate not found")
        from app.evolution.validation import validate_candidate

        validation = validate_candidate(
            self,
            candidate_id,
            validation_type=validation_type,
            sample_count=sample_count,
            regression_scope={
                "reason": reason,
                "manual_note": manual_note,
                "options": options or {},
                "details": details or {},
                "audit_metadata": audit_metadata or {},
            },
        )
        if not isinstance(validation, EvolutionValidationRunRecord):
            raise RuntimeError("evolution validation rerun was not recorded")
        self.record_evolution_audit_event(
            event_type="candidate_validation_rerun",
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            validation_run_id=validation.id,
            actor_user_id=user_id,
            metadata={
                "reason": reason,
                "manual_note": manual_note,
                "options": options or {},
                "audit_metadata": audit_metadata or {},
            },
        )
        if manual_note:
            refreshed = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
            self.update_candidate_status(
                candidate_id,
                status=refreshed.status if refreshed is not None else candidate.status,
                manual_note=manual_note,
            )
        return validation

    def rollback_evolution_candidate(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        rolled_back_by: int,
        manual_note: str | None = None,
        reason: str | None = None,
        options: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if candidate is None:
            raise ValueError("candidate not found")
        from app.evolution.rollback import rollback_candidate

        rolled_back = rollback_candidate(
            self,
            candidate_id,
            reason=reason or manual_note or "manual rollback",
        )
        refreshed = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if refreshed is None:
            raise RuntimeError("rolled back evolution candidate could not be reloaded")
        payload = dict(refreshed.__dict__)
        payload.update(
            {
                "rolled_back": rolled_back,
                "rolled_back_by": rolled_back_by,
                "manual_note": manual_note or refreshed.manual_note,
                "options": options or {},
                "audit_metadata": audit_metadata or {},
            }
        )
        self.record_evolution_audit_event(
            event_type="candidate_rollback_requested",
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            actor_user_id=rolled_back_by,
            metadata={
                "rolled_back": rolled_back,
                "reason": reason,
                "manual_note": manual_note,
                "options": options or {},
                "audit_metadata": audit_metadata or {},
            },
        )
        return payload

    def mark_evolution_frontend_suggestion_handled(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        handled_by: int,
        manual_note: str | None = None,
        reason: str | None = None,
        options: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._update_frontend_suggestion_state(
            candidate_id=candidate_id,
            user_id=user_id,
            actor_id=handled_by,
            status="frontend_handled",
            action="mark_frontend_handled",
            manual_note=manual_note,
            reason=reason,
            options=options,
            audit_metadata=audit_metadata,
        )

    def request_evolution_frontend_suggestion_regeneration(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        requested_by: int,
        manual_note: str | None = None,
        reason: str | None = None,
        options: dict[str, Any] | None = None,
        audit_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._update_frontend_suggestion_state(
            candidate_id=candidate_id,
            user_id=user_id,
            actor_id=requested_by,
            status="regeneration_requested",
            action="request_frontend_regeneration",
            manual_note=manual_note,
            reason=reason,
            options=options,
            audit_metadata=audit_metadata,
        )

    def _update_frontend_suggestion_state(
        self,
        *,
        candidate_id: int,
        user_id: int | None,
        actor_id: int,
        status: str,
        action: str,
        manual_note: str | None,
        reason: str | None,
        options: dict[str, Any] | None,
        audit_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if candidate is None:
            raise ValueError("candidate not found")
        if candidate.candidate_type != "frontend_suggestion":
            raise ValueError("candidate is not a frontend suggestion")
        application_result = {
            "frontend_suggestion_action": action,
            "actor_id": actor_id,
            "reason": reason,
            "options": options or {},
            "audit_metadata": audit_metadata or {},
            "will_modify_files": False,
        }
        self.update_candidate_status(
            candidate_id,
            status=status,
            manual_note=manual_note,
            application_result=application_result,
        )
        self.record_evolution_audit_event(
            event_type=action,
            run_id=candidate.run_id,
            candidate_id=candidate.id,
            actor_user_id=actor_id,
            metadata=application_result,
        )
        refreshed = self.get_evolution_candidate(candidate_id=candidate_id, user_id=user_id)
        if refreshed is None:
            raise RuntimeError("frontend suggestion candidate could not be reloaded")
        payload = dict(refreshed.__dict__)
        payload.update(
            {
                "handled_by": actor_id,
                "requested_by": actor_id,
                "audit_metadata": audit_metadata or {},
            }
        )
        return payload

    def create_validation_run(
        self,
        *,
        candidate_id: int,
        validation_type: str,
        status: str,
        sample_count: int,
        baseline_bundle_id: int | None,
        candidate_bundle_id: int | None,
        hard_rule_result: dict[str, Any],
        soft_rule_diff: dict[str, Any],
        schema_result: dict[str, Any],
        api_contract_result: dict[str, Any],
        report_quality_diff: dict[str, Any],
        repeat_rate_diff: dict[str, Any],
        score_distribution_diff: dict[str, Any],
        test_result: dict[str, Any],
        details: dict[str, Any],
    ) -> EvolutionValidationRunRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evolution_validation_runs (
                    candidate_id, validation_type, status, sample_count,
                    baseline_bundle_id, candidate_bundle_id, hard_rule_result,
                    soft_rule_diff, schema_result, api_contract_result,
                    report_quality_diff, repeat_rate_diff, score_distribution_diff,
                    test_result, details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    candidate_id,
                    validation_type,
                    status,
                    sample_count,
                    baseline_bundle_id,
                    candidate_bundle_id,
                    _json_dumps(hard_rule_result),
                    _json_dumps(soft_rule_diff),
                    _json_dumps(schema_result),
                    _json_dumps(api_contract_result),
                    _json_dumps(report_quality_diff),
                    _json_dumps(repeat_rate_diff),
                    _json_dumps(score_distribution_diff),
                    _json_dumps(test_result),
                    _json_dumps(details),
                ),
            )
            validation_id = int(cursor.lastrowid)
        validation = self.get_validation_run(validation_id)
        if validation is None:
            raise RuntimeError("evolution validation run was not created")
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=None)
        self.record_evolution_audit_event(
            event_type="validation_recorded",
            run_id=candidate.run_id if candidate is not None else None,
            candidate_id=candidate_id,
            validation_run_id=validation.id,
            version_bundle_id=candidate_bundle_id,
            metadata={
                "validation_type": validation_type,
                "status": status,
                "sample_count": sample_count,
                "baseline_bundle_id": baseline_bundle_id,
                "candidate_bundle_id": candidate_bundle_id,
            },
        )
        return validation

    def get_validation_run(self, validation_id: int) -> EvolutionValidationRunRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, candidate_id, validation_type, status, sample_count,
                       baseline_bundle_id, candidate_bundle_id, hard_rule_result,
                       soft_rule_diff, schema_result, api_contract_result,
                       report_quality_diff, repeat_rate_diff, score_distribution_diff,
                       test_result, details, created_at
                FROM evolution_validation_runs
                WHERE id = %s
                LIMIT 1
                """,
                (validation_id,),
            )
            row = cursor.fetchone()
        return _to_validation_run(row)

    def list_evolution_validation_runs(
        self,
        *,
        user_id: int | None = None,
        candidate_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionValidationRunRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id is not None:
            conditions.append("(r.user_id IS NULL OR r.user_id = %s)")
            params.append(user_id)
        if candidate_id is not None:
            conditions.append("v.candidate_id = %s")
            params.append(candidate_id)
        if status is not None:
            conditions.append("v.status = %s")
            params.append(status)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT v.id, v.candidate_id, v.validation_type, v.status, v.sample_count,
                       v.baseline_bundle_id, v.candidate_bundle_id, v.hard_rule_result,
                       v.soft_rule_diff, v.schema_result, v.api_contract_result,
                       v.report_quality_diff, v.repeat_rate_diff, v.score_distribution_diff,
                       v.test_result, v.details, v.created_at
                FROM evolution_validation_runs v
                JOIN evolution_candidates c ON c.id = v.candidate_id
                JOIN evolution_runs r ON r.id = c.run_id
                {where_clause}
                ORDER BY v.created_at DESC, v.id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_validation_run(row)) is not None]

    def create_version_bundle(
        self,
        *,
        bundle_key: str,
        parent_bundle_id: int | None,
        scope_type: str,
        scope_key: str | None,
        status: str,
        risk_level: str,
        content_hash: str,
        diff: dict[str, Any],
        validation_summary: dict[str, Any],
        rollback_point: dict[str, Any] | None,
        created_by_run_id: int | None,
        activated: bool = False,
    ) -> EvolutionVersionBundleRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evolution_version_bundles (
                    bundle_key, parent_bundle_id, scope_type, scope_key, status,
                    risk_level, content_hash, diff, validation_summary, rollback_point,
                    created_by_run_id, activated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, IF(%s, CURRENT_TIMESTAMP, NULL))
                """,
                (
                    bundle_key,
                    parent_bundle_id,
                    scope_type,
                    scope_key,
                    status,
                    risk_level,
                    content_hash,
                    _json_dumps(diff),
                    _json_dumps(validation_summary),
                    _json_dumps(rollback_point) if rollback_point is not None else None,
                    created_by_run_id,
                    activated,
                ),
            )
        bundle = self.get_version_bundle_by_key(bundle_key)
        if bundle is None:
            raise RuntimeError("evolution version bundle was not created")
        self.record_evolution_audit_event(
            event_type="version_bundle_created",
            run_id=created_by_run_id,
            version_bundle_id=bundle.id,
            metadata={
                "bundle_key": bundle_key,
                "parent_bundle_id": parent_bundle_id,
                "scope_type": scope_type,
                "scope_key": scope_key,
                "status": status,
                "risk_level": risk_level,
                "activated": activated,
                "rollback_point": rollback_point,
            },
        )
        return bundle

    def activate_version_bundle(self, bundle_id: int) -> None:
        bundle = self.get_version_bundle(bundle_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE evolution_version_bundles target
                JOIN evolution_version_bundles current
                  ON current.scope_type = target.scope_type
                 AND COALESCE(current.scope_key, '') = COALESCE(target.scope_key, '')
                 AND current.status = 'active'
                SET current.status = 'archived'
                WHERE target.id = %s AND current.id <> target.id
                """,
                (bundle_id,),
            )
            cursor.execute(
                """
                UPDATE evolution_version_bundles
                SET status = 'active', activated_at = COALESCE(activated_at, CURRENT_TIMESTAMP)
                WHERE id = %s
                """,
                (bundle_id,),
            )
        self.record_evolution_audit_event(
            event_type="version_bundle_activated",
            run_id=bundle.created_by_run_id if bundle is not None else None,
            version_bundle_id=bundle_id,
            metadata={
                "bundle_key": bundle.bundle_key if bundle is not None else None,
                "scope_type": bundle.scope_type if bundle is not None else None,
                "scope_key": bundle.scope_key if bundle is not None else None,
            },
        )

    def list_bundle_artifacts(self, bundle_id: int) -> list[EvolutionArtifactRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_id, artifact_type, artifact_key, version, content,
                       content_hash, parent_artifact_id, diff, risk_level, created_at
                FROM evolution_artifacts
                WHERE bundle_id = %s
                ORDER BY id ASC
                """,
                (bundle_id,),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_artifact(row)) is not None]

    def list_effective_artifacts(self, bundle_id: int) -> list[EvolutionArtifactRecord]:
        chain: list[EvolutionVersionBundleRecord] = []
        seen: set[int] = set()
        current = self.get_version_bundle(bundle_id)
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(current)
            current = (
                self.get_version_bundle(current.parent_bundle_id)
                if current.parent_bundle_id is not None
                else None
            )
        artifacts_by_key: dict[tuple[str, str], EvolutionArtifactRecord] = {}
        for bundle in reversed(chain):
            for artifact in self.list_bundle_artifacts(bundle.id):
                artifacts_by_key[(artifact.artifact_type, artifact.artifact_key)] = artifact
        return list(artifacts_by_key.values())

    def create_artifact(
        self,
        *,
        bundle_id: int,
        artifact_type: str,
        artifact_key: str,
        version: str,
        content: dict[str, Any],
        content_hash: str,
        parent_artifact_id: int | None = None,
        diff: dict[str, Any] | None = None,
        risk_level: str = "low",
    ) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evolution_artifacts (
                    bundle_id, artifact_type, artifact_key, version, content,
                    content_hash, parent_artifact_id, diff, risk_level
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    bundle_id,
                    artifact_type,
                    artifact_key,
                    version,
                    _json_dumps(content),
                    content_hash,
                    parent_artifact_id,
                    _json_dumps(diff or {}),
                    risk_level,
                ),
            )
            return int(cursor.lastrowid)

    def list_evolution_version_bundles(
        self,
        *,
        user_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[EvolutionVersionBundleRecord]:
        del user_id
        params: list[Any] = []
        where_clause = ""
        if status is not None:
            where_clause = "WHERE status = %s"
            params.append(status)
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, bundle_key, parent_bundle_id, scope_type, scope_key, status,
                       risk_level, content_hash, diff, validation_summary, rollback_point,
                       created_by_run_id, created_at, activated_at
                FROM evolution_version_bundles
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [record for row in rows if (record := _to_version_bundle(row)) is not None]

    def get_evolution_summary(self, *, user_id: int | None = None) -> dict[str, Any]:
        runs = self.list_evolution_runs(user_id=user_id, limit=100)
        candidates = self.list_evolution_candidates(user_id=user_id, limit=100)
        bundles = self.list_evolution_version_bundles(user_id=user_id, limit=100)
        signals = self.list_quality_signals(user_id=user_id, limit=10)
        return {
            "run_count": len(runs),
            "candidate_count": len(candidates),
            "risk_distribution": _count_records_by(candidates, "risk_level"),
            "latest_quality_signals": [dict(item.__dict__) for item in signals],
            "version_bundle_status": _count_records_by(bundles, "status"),
        }


def _to_version_bundle(row: dict[str, Any] | None) -> EvolutionVersionBundleRecord | None:
    if row is None:
        return None
    return EvolutionVersionBundleRecord(
        id=int(row["id"]),
        bundle_key=str(row["bundle_key"]),
        parent_bundle_id=(
            int(row["parent_bundle_id"]) if row.get("parent_bundle_id") is not None else None
        ),
        scope_type=str(row["scope_type"]),
        scope_key=row.get("scope_key"),
        status=str(row["status"]),
        risk_level=str(row["risk_level"]),
        content_hash=str(row["content_hash"]),
        diff=_json_dict(row.get("diff")),
        validation_summary=_json_dict(row.get("validation_summary")),
        rollback_point=_json_dict_or_none(row.get("rollback_point")),
        created_by_run_id=(
            int(row["created_by_run_id"]) if row.get("created_by_run_id") is not None else None
        ),
        created_at=row.get("created_at"),
        activated_at=row.get("activated_at"),
    )


def _to_quality_signal(row: dict[str, Any] | None) -> EvolutionQualitySignalRecord | None:
    if row is None:
        return None
    return EvolutionQualitySignalRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        interview_id=int(row["interview_id"]),
        version_bundle_id=(
            int(row["version_bundle_id"]) if row.get("version_bundle_id") is not None else None
        ),
        job_family=row.get("job_family"),
        signal_type=str(row["signal_type"]),
        severity=str(row["severity"]),
        metrics=_json_dict(row.get("metrics")),
        hard_trigger=bool(row.get("hard_trigger")),
        threshold_trigger=bool(row.get("threshold_trigger")),
        source_refs=_json_dict(row.get("source_refs")),
        created_at=row.get("created_at"),
    )


def _to_run(row: dict[str, Any] | None) -> EvolutionRunRecord | None:
    if row is None:
        return None
    return EvolutionRunRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]) if row.get("user_id") is not None else None,
        dedupe_key=row.get("dedupe_key"),
        trigger_type=str(row["trigger_type"]),
        trigger_reason=str(row["trigger_reason"]),
        scope_type=str(row.get("scope_type") or "global"),
        scope_key=row.get("scope_key"),
        sample_count=int(row.get("sample_count") or 0),
        data_scope=_json_dict(row.get("data_scope")),
        anonymization_status=str(row.get("anonymization_status") or "not_required"),
        audit_metadata=_json_dict(row.get("audit_metadata")),
        status=str(row.get("status") or "pending"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        error_message=row.get("error_message"),
    )


def _to_candidate(row: dict[str, Any] | None) -> EvolutionCandidateRecord | None:
    if row is None:
        return None
    return EvolutionCandidateRecord(
        id=int(row["id"]),
        run_id=int(row["run_id"]),
        candidate_type=str(row["candidate_type"]),
        target_artifact_key=row.get("target_artifact_key"),
        risk_level=str(row["risk_level"]),
        status=str(row["status"]),
        proposal=_json_dict(row.get("proposal")),
        diff=_json_dict(row.get("diff")),
        impact_scope=_json_dict(row.get("impact_scope")),
        root_cause=_json_dict(row.get("root_cause")),
        validation_summary=_json_dict_or_none(row.get("validation_summary")),
        approval_status=str(row.get("approval_status") or "pending"),
        approved_by=int(row["approved_by"]) if row.get("approved_by") is not None else None,
        approved_at=row.get("approved_at"),
        manual_note=row.get("manual_note"),
        rollback_point=_json_dict_or_none(row.get("rollback_point")),
        application_result=_json_dict_or_none(row.get("application_result")),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _to_validation_run(row: dict[str, Any] | None) -> EvolutionValidationRunRecord | None:
    if row is None:
        return None
    return EvolutionValidationRunRecord(
        id=int(row["id"]),
        candidate_id=int(row["candidate_id"]),
        validation_type=str(row["validation_type"]),
        status=str(row["status"]),
        sample_count=int(row.get("sample_count") or 0),
        baseline_bundle_id=(
            int(row["baseline_bundle_id"]) if row.get("baseline_bundle_id") is not None else None
        ),
        candidate_bundle_id=(
            int(row["candidate_bundle_id"]) if row.get("candidate_bundle_id") is not None else None
        ),
        hard_rule_result=_json_dict(row.get("hard_rule_result")),
        soft_rule_diff=_json_dict(row.get("soft_rule_diff")),
        schema_result=_json_dict(row.get("schema_result")),
        api_contract_result=_json_dict(row.get("api_contract_result")),
        report_quality_diff=_json_dict(row.get("report_quality_diff")),
        repeat_rate_diff=_json_dict(row.get("repeat_rate_diff")),
        score_distribution_diff=_json_dict(row.get("score_distribution_diff")),
        test_result=_json_dict(row.get("test_result")),
        details=_json_dict(row.get("details")),
        created_at=row.get("created_at"),
    )


def _to_audit_event(row: dict[str, Any] | None) -> EvolutionAuditEventRecord | None:
    if row is None:
        return None
    return EvolutionAuditEventRecord(
        id=int(row["id"]),
        event_type=str(row["event_type"]),
        run_id=int(row["run_id"]) if row.get("run_id") is not None else None,
        candidate_id=int(row["candidate_id"]) if row.get("candidate_id") is not None else None,
        validation_run_id=(
            int(row["validation_run_id"]) if row.get("validation_run_id") is not None else None
        ),
        version_bundle_id=(
            int(row["version_bundle_id"]) if row.get("version_bundle_id") is not None else None
        ),
        actor_user_id=int(row["actor_user_id"]) if row.get("actor_user_id") is not None else None,
        metadata=_json_dict(row.get("metadata")),
        created_at=row.get("created_at"),
    )


def _to_artifact(row: dict[str, Any] | None) -> EvolutionArtifactRecord | None:
    if row is None:
        return None
    return EvolutionArtifactRecord(
        id=int(row["id"]),
        bundle_id=int(row["bundle_id"]),
        artifact_type=str(row["artifact_type"]),
        artifact_key=str(row["artifact_key"]),
        version=str(row["version"]),
        content=_json_dict(row.get("content")),
        content_hash=str(row["content_hash"]),
        parent_artifact_id=(
            int(row["parent_artifact_id"]) if row.get("parent_artifact_id") is not None else None
        ),
        diff=_json_dict(row.get("diff")),
        risk_level=str(row["risk_level"]),
        created_at=row.get("created_at"),
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_dict_or_none(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _json_dict(value)


def _is_duplicate_key_error(exc: Exception) -> bool:
    args = getattr(exc, "args", ())
    code = args[0] if args else None
    return code == 1062 or "duplicate" in str(exc).casefold()


def _dedupe_key(
    *,
    trigger_type: str,
    trigger_reason: str,
    scope_type: str,
    scope_key: str | None,
    data_scope: dict[str, Any],
) -> str:
    payload = {
        "trigger_type": trigger_type,
        "trigger_reason": trigger_reason,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "data_scope": data_scope,
    }
    digest = hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()
    return f"evo:{trigger_type}:{digest[:48]}"


def _count_records_by(records: list[Any], attr_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(getattr(record, attr_name, None) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts
