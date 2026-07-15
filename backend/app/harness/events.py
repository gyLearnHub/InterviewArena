import hashlib
import json
from importlib import import_module
from typing import Any

from app.harness.contracts import HarnessExecutionRequest, ValidationStatus
from app.repositories.harness import HarnessRepository


def get_harness_repository(connection: Any | None) -> Any | None:
    if connection is None:
        return None
    try:
        return HarnessRepository(connection)
    except Exception:
        return None


def build_harness_request(
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    agent_type: str | None,
    purpose: str,
    payload: dict[str, Any],
    prompt_version: str | None = None,
) -> Any:
    payload_key = _harness_payload_key(
        {"payload": payload, "prompt_version": prompt_version}
    )
    data: dict[str, Any] = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": round_id,
        "node_id": f"{interview_id}:{round_id or 'interview'}:{node_type}",
        "node_type": node_type,
        "agent_type": agent_type or node_type,
        "purpose": purpose,
        "prompt_version": prompt_version,
        "context_refs": payload,
        "input_payload": payload,
        "execution_mode": "normal",
        "idempotency_key": (
            f"{interview_id}:{round_id or 0}:{node_type}:{purpose}:{payload_key}"
        ),
    }
    try:
        return HarnessExecutionRequest(**data)
    except Exception:
        return data


def snapshot_harness_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: snapshot_harness_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [snapshot_harness_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def save_fallback_rule_evaluations(
    *,
    repository: Any,
    request: Any,
    trace_id: int,
    validation_status: str,
    error_detail: str | None = None,
    checkpoint_id: int | None = None,
) -> None:
    try:
        output_validation = import_module("app.harness.output_validation")
        rules = import_module("app.harness.rules")
        validation = output_validation.OutputValidationResult(
            validation_status=_coerce_validation_status(validation_status),
            errors=[error_detail] if validation_status == "failed" and error_detail else [],
        )
        evaluator = rules.RuleEvaluator(repository)
        evaluations = evaluator.evaluate_node(
            request,
            trace_id=trace_id,
            checkpoint_id=checkpoint_id,
            output_validation=validation,
            retry_count=0,
            event_write_failed=False,
        )
        evaluator.save_all(
            user_id=request.user_id,
            interview_id=request.interview_id,
            trace_id=trace_id,
            evaluations=evaluations,
        )
    except Exception:
        return


def _harness_payload_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        snapshot_harness_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]


def _coerce_validation_status(value: str) -> ValidationStatus:
    if value in {"pending", "passed", "warning", "failed"}:
        return value  # type: ignore[return-value]
    return "failed"


def record_harness_event(
    *,
    connection: Any | None,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    """Best-effort event recording inside the caller's current transaction."""
    if connection is None:
        return False

    repository = HarnessRepository(connection)
    node_id = f"{interview_id}:{round_id or 'interview'}:{node_type}"
    try:
        trace = repository.latest_user_trace_for_node(node_id=node_id, user_id=user_id)
        if trace is None:
            request = HarnessExecutionRequest(
                user_id=user_id,
                interview_id=interview_id,
                round_id=round_id,
                node_id=node_id,
                node_type=node_type,
                agent_type=node_type,
                purpose=f"event:{event_type}",
                input_payload=payload,
            )
            trace_id = repository.create_trace(request)
            created_trace = True
        else:
            trace_id = trace.id
            created_trace = False

        repository.create_trace_event(trace_id, event_type, payload)
        if created_trace:
            repository.update_trace_status(
                trace_id,
                status="completed",
                validation_status="passed",
                output_snapshot={"event_type": event_type, "payload": payload},
            )
        return True
    except Exception:
        return False
