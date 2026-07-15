from __future__ import annotations

import logging
from typing import Any

from app.autonomous_evolution.anonymization import contains_direct_identifier
from app.autonomous_evolution.metrics import historical_quality_score
from app.autonomous_evolution.repository import AutonomousEvolutionRepository
from app.core.config import get_settings

LOGGER = logging.getLogger(__name__)


class RuntimeHardGateError(RuntimeError):
    pass


def observe_completed_interview(connection: Any, interview_id: int) -> None:
    try:
        repository = AutonomousEvolutionRepository(connection)
        bundle = repository.get_interview_bundle(interview_id)
        if bundle is None or not bundle.is_active or bundle.status != "observing":
            return
        sample = repository.load_interview_sample(interview_id)
        quality = historical_quality_score(sample)
        hard_errors = _hard_errors(sample)
        count, average, has_hard_error = repository.record_observation(
            bundle_id=bundle.id,
            interview_id=interview_id,
            quality_score=quality,
            hard_error=bool(hard_errors),
            metrics={"quality_score": quality, "hard_errors": hard_errors},
        )
        repository.record_event(
            bundle_id=bundle.id,
            event_type="observation_recorded",
            payload={
                "interview_id": interview_id,
                "quality_score": quality,
                "observation_count": count,
                "average_quality": average,
                "hard_errors": hard_errors,
            },
        )
        if has_hard_error:
            repository.rollback_bundle(bundle.id, reason="runtime hard gate failed")
            return
        settings = get_settings()
        if count < settings.evolution_observation_interviews:
            return
        baseline = bundle.baseline_quality or 0.0
        if baseline > 0.0 and average < baseline * 0.90:
            repository.rollback_bundle(
                bundle.id,
                reason="observation quality dropped by more than 10 percent",
            )
        else:
            repository.finish_observation(bundle.id)
    except Exception:
        LOGGER.exception(
            "failed to observe completed interview %s for autonomous evolution",
            interview_id,
        )
        return


def record_runtime_execution(
    connection: Any,
    interview_id: int,
    *,
    succeeded: bool,
    hard_error: bool = False,
) -> None:
    try:
        AutonomousEvolutionRepository(connection).record_execution_outcome(
            interview_id,
            succeeded=succeeded,
            hard_error=hard_error,
        )
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()
    except Exception:
        LOGGER.exception(
            "failed to record autonomous evolution runtime outcome for interview %s",
            interview_id,
        )
        return


def validate_runtime_output(value: Any) -> None:
    if contains_direct_identifier(value):
        raise RuntimeHardGateError("runtime output contains a direct identifier")
    invalid_score = _find_invalid_score(value)
    if invalid_score is not None:
        raise RuntimeHardGateError(
            f"runtime output score is outside the allowed boundary: {invalid_score}"
        )


def is_hard_runtime_error(error: Exception) -> bool:
    if isinstance(error, RuntimeHardGateError):
        return True
    details = getattr(error, "details", None)
    return isinstance(details, dict) and details.get("error") == "invalid_model_output"


def _hard_errors(sample: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if any(
        item.get("status") == "failed" and item.get("severity") == "hard"
        for item in sample.get("harness_rules") or []
    ):
        errors.append("hard Harness rule failed")
    if any(
        item.get("validation_status") == "failed"
        for item in sample.get("harness_traces") or []
    ):
        errors.append("runtime output validation failed")
    if any(
        contains_direct_identifier(item.get("output_snapshot"))
        for item in sample.get("harness_traces") or []
    ):
        errors.append("runtime output contains a direct identifier")
    report_score = sample.get("report_score")
    if report_score is not None and (
        isinstance(report_score, bool)
        or not isinstance(report_score, (int, float))
        or not 0 <= float(report_score) <= 100
    ):
        errors.append("report score is outside the allowed boundary")
    return errors


def _find_invalid_score(value: Any) -> Any | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if item is not None and str(key) in {"score", "total_score"} and (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not 0 <= float(item) <= 100
            ):
                return item
            nested = _find_invalid_score(item)
            if nested is not None:
                return nested
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested = _find_invalid_score(item)
            if nested is not None:
                return nested
    return None
