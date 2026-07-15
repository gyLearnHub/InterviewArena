from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.harness.contracts import CheckpointCreate, HarnessExecutionRequest, RuleEvaluation

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class HarnessTraceRecord:
    id: int
    user_id: int
    interview_id: int
    round_id: int | None
    node_id: str
    node_type: str
    agent_type: str
    purpose: str
    status: str
    validation_status: str
    event_write_failed: bool
    prompt_version: str | None
    model_name: str | None
    model_params: JSONDict
    schema_version: str | None
    expected_schema: JSONDict | None
    input_snapshot: JSONDict
    output_snapshot: JSONDict | None
    context_summary: JSONDict
    tool_summary: JSONDict
    token_usage: JSONDict
    retry_records: list[JSONDict]
    degradation_records: list[JSONDict]
    error_code: str | None
    error_detail: str | None
    elapsed_ms: int | None
    execution_mode: str
    idempotency_key: str | None
    source_trace_id: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class HarnessTraceEventRecord:
    id: int
    trace_id: int
    event_type: str
    status: str
    payload: JSONDict
    error_message: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class HarnessCheckpointRecord:
    id: int
    user_id: int
    interview_id: int
    round_id: int | None
    trace_id: int | None
    node_id: str
    checkpoint_type: str
    status: str
    snapshot: JSONDict
    resume_version: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class HarnessRuleEvaluationRecord:
    id: int
    user_id: int
    interview_id: int
    trace_id: int | None
    rule_name: str
    status: str
    severity: str
    evidence: JSONDict
    failure_reason: str | None
    overall_grade: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class HarnessImprovementCandidateRecord:
    id: int
    user_id: int | None
    interview_id: int | None
    source_trace_id: int | None
    candidate_type: str
    status: str
    proposal: JSONDict
    sandbox_result: JSONDict | None
    regression_result: JSONDict | None
    approval_status: str
    applied_version: str | None
    rollback_point: str | None
    created_at: datetime | None
    updated_at: datetime | None


class HarnessRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_trace(self, request: HarnessExecutionRequest) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO harness_traces (
                    source_trace_id, user_id, interview_id, round_id, node_id, node_type,
                    agent_type, purpose, prompt_version, model_name, model_params,
                    schema_version, expected_schema, input_snapshot, context_summary,
                    tool_summary, token_usage, retry_records, degradation_records,
                    validation_status, status, execution_mode, idempotency_key
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, JSON_OBJECT(),
                    JSON_OBJECT(), JSON_OBJECT(), JSON_ARRAY(), JSON_ARRAY(), %s, %s, %s, %s
                )
                """,
                (
                    request.source_trace_id,
                    request.user_id,
                    request.interview_id,
                    request.round_id,
                    request.node_id,
                    request.node_type,
                    request.agent_type,
                    request.purpose,
                    request.prompt_version,
                    request.model_name,
                    _json_dumps(request.model_params),
                    request.schema_version,
                    _json_dumps_or_none(request.expected_schema),
                    _json_dumps(request.input_payload),
                    "pending",
                    "running",
                    request.execution_mode,
                    request.idempotency_key,
                ),
            )
            return int(cursor.lastrowid)

    def update_trace_status(
        self,
        trace_id: int,
        *,
        status: str,
        validation_status: str | None = None,
        output_snapshot: JSONDict | None = None,
        context_summary: JSONDict | None = None,
        tool_summary: JSONDict | None = None,
        token_usage: JSONDict | None = None,
        retry_records: list[JSONDict] | None = None,
        degradation_records: list[JSONDict] | None = None,
        elapsed_ms: int | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        event_write_failed: bool | None = None,
    ) -> None:
        assignments = ["status = %s"]
        params: list[Any] = [status]
        optional_values: list[tuple[str, Any, bool]] = [
            ("validation_status", validation_status, False),
            ("output_snapshot", output_snapshot, True),
            ("context_summary", context_summary, True),
            ("tool_summary", tool_summary, True),
            ("token_usage", token_usage, True),
            ("retry_records", retry_records, True),
            ("degradation_records", degradation_records, True),
            ("elapsed_ms", elapsed_ms, False),
            ("error_code", error_code, False),
            ("error_detail", error_detail[:2000] if error_detail is not None else None, False),
            ("event_write_failed", event_write_failed, False),
        ]
        for column, value, is_json in optional_values:
            if value is None:
                continue
            assignments.append(f"{column} = %s")
            params.append(_json_dumps(value) if is_json else value)
        params.append(trace_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE harness_traces SET {', '.join(assignments)} WHERE id = %s",
                tuple(params),
            )

    def create_trace_event(
        self,
        trace_id: int,
        event_type: str,
        payload: JSONDict | None = None,
        *,
        status: str = "succeeded",
        error_message: str | None = None,
    ) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO harness_trace_events (
                    trace_id, event_type, status, payload, error_message
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    trace_id,
                    event_type,
                    status,
                    _json_dumps(payload or {}),
                    error_message[:1000] if error_message is not None else None,
                ),
            )
            return int(cursor.lastrowid)

    def create_checkpoint(self, checkpoint: CheckpointCreate) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO harness_checkpoints (
                    user_id, interview_id, round_id, trace_id, node_id, checkpoint_type,
                    status, snapshot, resume_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    checkpoint.user_id,
                    checkpoint.interview_id,
                    checkpoint.round_id,
                    checkpoint.trace_id,
                    checkpoint.node_id,
                    checkpoint.checkpoint_type,
                    checkpoint.status,
                    _json_dumps(checkpoint.snapshot),
                    checkpoint.resume_version,
                ),
            )
            checkpoint_id = int(cursor.lastrowid)
            cursor.execute(
                "UPDATE interviews SET last_checkpoint_id = %s WHERE id = %s",
                (checkpoint_id, checkpoint.interview_id),
            )
            return checkpoint_id

    def latest_checkpoint(
        self,
        interview_id: int,
        *,
        round_id: int | None = None,
        node_id: str | None = None,
    ) -> HarnessCheckpointRecord | None:
        conditions = ["interview_id = %s", "status = %s"]
        params: list[Any] = [interview_id, "available"]
        if round_id is not None:
            conditions.append("round_id = %s")
            params.append(round_id)
        if node_id is not None:
            conditions.append("node_id = %s")
            params.append(node_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, interview_id, round_id, trace_id, node_id, checkpoint_type,
                       status, snapshot, resume_version, created_at
                FROM harness_checkpoints
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            )
            row = cursor.fetchone()
        return _to_checkpoint(row)

    def save_rule_evaluation(
        self,
        *,
        user_id: int,
        interview_id: int,
        evaluation: RuleEvaluation,
        trace_id: int | None = None,
    ) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO harness_rule_evaluations (
                    user_id, interview_id, trace_id, rule_name, status,
                    severity, evidence, failure_reason, overall_grade
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    interview_id,
                    trace_id,
                    evaluation.rule_name,
                    evaluation.status,
                    evaluation.severity,
                    _json_dumps(evaluation.evidence),
                    evaluation.failure_reason,
                    evaluation.overall_grade,
                ),
            )
            return int(cursor.lastrowid)

    def list_traces(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[HarnessTraceRecord]:
        conditions = ["interview_id = %s"]
        params: list[Any] = [interview_id]
        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)
        params.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, source_trace_id, user_id, interview_id, round_id, node_id, node_type,
                       agent_type, purpose, prompt_version, model_name, model_params,
                       schema_version, expected_schema, input_snapshot, output_snapshot,
                       context_summary, tool_summary, token_usage, retry_records,
                       degradation_records, validation_status, status, event_write_failed,
                       error_code, error_detail, elapsed_ms, execution_mode, idempotency_key,
                       created_at, updated_at
                FROM harness_traces
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_trace(row) for row in rows]

    def get_trace(self, trace_id: int, *, user_id: int | None = None) -> HarnessTraceRecord | None:
        conditions = ["id = %s"]
        params: list[Any] = [trace_id]
        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, source_trace_id, user_id, interview_id, round_id, node_id, node_type,
                       agent_type, purpose, prompt_version, model_name, model_params,
                       schema_version, expected_schema, input_snapshot, output_snapshot,
                       context_summary, tool_summary, token_usage, retry_records,
                       degradation_records, validation_status, status, event_write_failed,
                       error_code, error_detail, elapsed_ms, execution_mode, idempotency_key,
                       created_at, updated_at
                FROM harness_traces
                WHERE {" AND ".join(conditions)}
                """,
                tuple(params),
            )
            row = cursor.fetchone()
        return _to_trace(row) if row is not None else None

    def list_trace_events(self, trace_id: int) -> list[HarnessTraceEventRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, trace_id, event_type, status, payload, error_message, created_at
                FROM harness_trace_events
                WHERE trace_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (trace_id,),
            )
            rows = cursor.fetchall()
        return [_to_event(row) for row in rows]

    def list_checkpoints(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[HarnessCheckpointRecord]:
        conditions = ["interview_id = %s"]
        params: list[Any] = [interview_id]
        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)
        params.append(max(1, min(limit, 100)))
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, interview_id, round_id, trace_id, node_id, checkpoint_type,
                       status, snapshot, resume_version, created_at
                FROM harness_checkpoints
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        checkpoints: list[HarnessCheckpointRecord] = []
        for row in rows:
            checkpoint = _to_checkpoint(row)
            if checkpoint is not None:
                checkpoints.append(checkpoint)
        return checkpoints

    def list_rule_evaluations(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
        limit: int = 100,
    ) -> list[HarnessRuleEvaluationRecord]:
        conditions = ["interview_id = %s"]
        params: list[Any] = [interview_id]
        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)
        params.append(max(1, min(limit, 100)))
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, interview_id, trace_id, rule_name, status,
                       severity, evidence, failure_reason, overall_grade, created_at
                FROM harness_rule_evaluations
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_rule(row) for row in rows]

    def list_improvement_candidates(
        self,
        *,
        user_id: int,
        status: str | None = None,
    ) -> list[HarnessImprovementCandidateRecord]:
        conditions = ["(user_id = %s OR user_id IS NULL)"]
        params: list[Any] = [user_id]
        if status is not None:
            conditions.append("status = %s")
            params.append(status)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, interview_id, source_trace_id, candidate_type, status,
                       proposal, sandbox_result, regression_result, approval_status,
                       applied_version, rollback_point, created_at, updated_at
                FROM harness_improvement_candidates
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_improvement_candidate(row) for row in rows]

    def interview_belongs_to_user(self, *, interview_id: int, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM interviews WHERE id = %s AND user_id = %s LIMIT 1",
                (interview_id, user_id),
            )
            return cursor.fetchone() is not None

    def latest_user_trace_for_node(
        self,
        *,
        node_id: str,
        user_id: int,
    ) -> HarnessTraceRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, source_trace_id, user_id, interview_id, round_id, node_id, node_type,
                       agent_type, purpose, prompt_version, model_name, model_params,
                       schema_version, expected_schema, input_snapshot, output_snapshot,
                       context_summary, tool_summary, token_usage, retry_records,
                       degradation_records, validation_status, status, event_write_failed,
                       error_code, error_detail, elapsed_ms, execution_mode, idempotency_key,
                       created_at, updated_at
                FROM harness_traces
                WHERE node_id = %s AND user_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (node_id, user_id),
            )
            row = cursor.fetchone()
        return _to_trace(row) if row is not None else None


def _to_trace(row: dict[str, Any]) -> HarnessTraceRecord:
    return HarnessTraceRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        interview_id=int(row["interview_id"]),
        round_id=_optional_int(row.get("round_id")),
        node_id=str(row["node_id"]),
        node_type=str(row["node_type"]),
        agent_type=str(row["agent_type"]),
        purpose=str(row["purpose"]),
        status=str(row["status"]),
        validation_status=str(row["validation_status"]),
        event_write_failed=bool(row.get("event_write_failed")),
        prompt_version=row.get("prompt_version"),
        model_name=row.get("model_name"),
        model_params=_json_dict(row.get("model_params")),
        schema_version=row.get("schema_version"),
        expected_schema=_json_dict_or_none(row.get("expected_schema")),
        input_snapshot=_json_dict(row.get("input_snapshot")),
        output_snapshot=_json_dict_or_none(row.get("output_snapshot")),
        context_summary=_json_dict(row.get("context_summary")),
        tool_summary=_json_dict(row.get("tool_summary")),
        token_usage=_json_dict(row.get("token_usage")),
        retry_records=_json_dict_list(row.get("retry_records")),
        degradation_records=_json_dict_list(row.get("degradation_records")),
        error_code=row.get("error_code"),
        error_detail=row.get("error_detail"),
        elapsed_ms=_optional_int(row.get("elapsed_ms")),
        execution_mode=str(row.get("execution_mode") or "normal"),
        idempotency_key=row.get("idempotency_key"),
        source_trace_id=_optional_int(row.get("source_trace_id")),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _to_event(row: dict[str, Any]) -> HarnessTraceEventRecord:
    return HarnessTraceEventRecord(
        id=int(row["id"]),
        trace_id=int(row["trace_id"]),
        event_type=str(row["event_type"]),
        status=str(row["status"]),
        payload=_json_dict(row.get("payload")),
        error_message=row.get("error_message"),
        created_at=row.get("created_at"),
    )


def _to_checkpoint(row: dict[str, Any] | None) -> HarnessCheckpointRecord | None:
    if row is None:
        return None
    return HarnessCheckpointRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        interview_id=int(row["interview_id"]),
        round_id=_optional_int(row.get("round_id")),
        trace_id=_optional_int(row.get("trace_id")),
        node_id=str(row["node_id"]),
        checkpoint_type=str(row["checkpoint_type"]),
        status=str(row["status"]),
        snapshot=_json_dict(row.get("snapshot")),
        resume_version=row.get("resume_version"),
        created_at=row.get("created_at"),
    )


def _to_rule(row: dict[str, Any]) -> HarnessRuleEvaluationRecord:
    return HarnessRuleEvaluationRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        interview_id=int(row["interview_id"]),
        trace_id=_optional_int(row.get("trace_id")),
        rule_name=str(row["rule_name"]),
        status=str(row["status"]),
        severity=str(row["severity"]),
        evidence=_json_dict(row.get("evidence")),
        failure_reason=row.get("failure_reason"),
        overall_grade=row.get("overall_grade"),
        created_at=row.get("created_at"),
    )


def _to_improvement_candidate(row: dict[str, Any]) -> HarnessImprovementCandidateRecord:
    return HarnessImprovementCandidateRecord(
        id=int(row["id"]),
        user_id=_optional_int(row.get("user_id")),
        interview_id=_optional_int(row.get("interview_id")),
        source_trace_id=_optional_int(row.get("source_trace_id")),
        candidate_type=str(row["candidate_type"]),
        status=str(row["status"]),
        proposal=_json_dict(row.get("proposal")),
        sandbox_result=_json_dict_or_none(row.get("sandbox_result")),
        regression_result=_json_dict_or_none(row.get("regression_result")),
        approval_status=str(row["approval_status"]),
        applied_version=row.get("applied_version"),
        rollback_point=row.get("rollback_point"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_dumps_or_none(value: Any) -> str | None:
    return _json_dumps(value) if value is not None else None


def _json_dict(value: Any) -> JSONDict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_dict_or_none(value: Any) -> JSONDict | None:
    if value is None:
        return None
    parsed = _json_dict(value)
    return parsed if parsed else None


def _json_dict_list(value: Any) -> list[JSONDict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []
