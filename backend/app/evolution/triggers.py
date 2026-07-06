from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TriggerType = Literal["immediate", "sample_10", "sample_50", "daily_inspection", "manual"]


@dataclass(frozen=True)
class EvolutionRunTrigger:
    trigger_type: TriggerType
    trigger_reason: str
    scope_type: str = "global"
    scope_key: str | None = None
    sample_count: int = 0
    data_scope: dict[str, Any] = field(default_factory=dict)
    anonymization_status: str = "anonymized"
    audit_metadata: dict[str, Any] = field(default_factory=dict)


THRESHOLD_TRIGGER_MIN_COUNT = 3


def build_trigger_for_quality_signal(
    signal: Any,
    *,
    completed_signal_count: int = 0,
    threshold_count: int = THRESHOLD_TRIGGER_MIN_COUNT,
) -> list[EvolutionRunTrigger]:
    triggers: list[EvolutionRunTrigger] = []
    signal_dict = _as_dict(signal)
    interview_id = signal_dict.get("interview_id")
    source_refs = dict(signal_dict.get("source_refs") or {})
    metrics = dict(signal_dict.get("metrics") or {})
    reason_codes = list(metrics.get("trigger_reason_codes") or [])
    data_scope = {
        "quality_signal_id": signal_dict.get("id"),
        "interview_ids": [interview_id] if interview_id is not None else [],
        "source_refs": source_refs,
        "trigger_reason_codes": reason_codes,
    }
    if signal_dict.get("hard_trigger"):
        triggers.append(
            EvolutionRunTrigger(
                trigger_type="immediate",
                trigger_reason=_trigger_reason(signal_dict, "hard_trigger"),
                scope_type="interview",
                scope_key=str(interview_id) if interview_id is not None else None,
                sample_count=1,
                data_scope=data_scope,
                anonymization_status="single_interview_internal",
                audit_metadata={"source": "quality_signal", "trigger": "hard"},
            )
        )
    if signal_dict.get("threshold_trigger") and completed_signal_count >= threshold_count:
        trigger_type: TriggerType = "sample_10" if completed_signal_count < 50 else "sample_50"
        triggers.append(
            EvolutionRunTrigger(
                trigger_type=trigger_type,
                trigger_reason=_trigger_reason(signal_dict, "threshold_trigger"),
                scope_type="global",
                scope_key=None,
                sample_count=completed_signal_count,
                data_scope={
                    "quality_signal_id": signal_dict.get("id"),
                    "sample_window": f"latest_{min(completed_signal_count, 50)}",
                    "aggregated_only": True,
                    "trigger_reason_codes": reason_codes,
                },
                anonymization_status="aggregated_anonymized",
                audit_metadata={"source": "quality_signal", "trigger": "threshold"},
            )
        )
    elif signal_dict.get("threshold_trigger") and _single_signal_threshold_met(metrics):
        triggers.append(
            EvolutionRunTrigger(
                trigger_type="immediate",
                trigger_reason=_trigger_reason(signal_dict, "threshold_single_signal"),
                scope_type="interview",
                scope_key=str(interview_id) if interview_id is not None else None,
                sample_count=1,
                data_scope=data_scope,
                anonymization_status="single_interview_internal",
                audit_metadata={"source": "quality_signal", "trigger": "threshold_single"},
            )
        )
    if completed_signal_count > 0 and completed_signal_count % 10 == 0:
        triggers.append(
            EvolutionRunTrigger(
                trigger_type="sample_10",
                trigger_reason=f"completed interview sample reached {completed_signal_count}",
                sample_count=completed_signal_count,
                data_scope={"sample_window": "latest_10", "aggregated_only": True},
                anonymization_status="aggregated_anonymized",
                audit_metadata={"source": "sample_counter"},
            )
        )
    if completed_signal_count > 0 and completed_signal_count % 50 == 0:
        triggers.append(
            EvolutionRunTrigger(
                trigger_type="sample_50",
                trigger_reason=f"completed interview sample reached {completed_signal_count}",
                sample_count=completed_signal_count,
                data_scope={"sample_window": "latest_50", "aggregated_only": True},
                anonymization_status="aggregated_anonymized",
                audit_metadata={"source": "sample_counter"},
            )
        )
    return triggers


def create_runs_for_quality_signal(repository: Any, signal: Any) -> list[Any]:
    completed_count = _count_completed_signals(repository)
    results: list[Any] = []
    for trigger in build_trigger_for_quality_signal(
        signal,
        completed_signal_count=completed_count,
    ):
        create_run = getattr(repository, "create_evolution_run", None)
        if callable(create_run):
            results.append(
                create_run(
                    user_id=getattr(signal, "user_id", None),
                    trigger_type=trigger.trigger_type,
                    trigger_reason=trigger.trigger_reason,
                    scope_type=trigger.scope_type,
                    scope_key=trigger.scope_key,
                    sample_count=trigger.sample_count,
                    data_scope=trigger.data_scope,
                    anonymization_status=trigger.anonymization_status,
                    audit_metadata=trigger.audit_metadata,
                )
            )
    return results


def build_manual_trigger(
    *,
    trigger_type: TriggerType,
    trigger_reason: str,
    scope_type: str = "global",
    scope_key: str | None = None,
    sample_count: int = 0,
    data_scope: dict[str, Any] | None = None,
    anonymization_status: str = "anonymized",
    audit_metadata: dict[str, Any] | None = None,
) -> EvolutionRunTrigger:
    if not trigger_reason.strip():
        raise ValueError("trigger_reason is required.")
    if sample_count < 0:
        raise ValueError("sample_count cannot be negative.")

    return EvolutionRunTrigger(
        trigger_type=trigger_type,
        trigger_reason=trigger_reason.strip(),
        scope_type=scope_type.strip() or "global",
        scope_key=scope_key.strip() if scope_key else None,
        sample_count=sample_count,
        data_scope=dict(data_scope or {}),
        anonymization_status=anonymization_status.strip() or "anonymized",
        audit_metadata=dict(audit_metadata or {}),
    )


def _count_completed_signals(repository: Any) -> int:
    method = getattr(repository, "count_completed_quality_signals", None)
    if callable(method):
        return int(method())
    return 0


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _trigger_reason(signal: dict[str, Any], trigger_name: str) -> str:
    return (
        f"{trigger_name}: interview {signal.get('interview_id')} "
        f"{signal.get('signal_type', 'quality_signal')} severity={signal.get('severity')}"
    )[:1000]


def _single_signal_threshold_met(metrics: dict[str, Any]) -> bool:
    question_quality = dict(metrics.get("question_quality") or {})
    report_quality = dict(metrics.get("report_quality") or {})
    behavior = dict(metrics.get("behavior") or {})
    return (
        int(question_quality.get("repeat_count") or 0) >= 2
        or float(question_quality.get("max_similarity") or 0.0) >= 0.9
        or float(report_quality.get("vagueness_score") or 0.0) >= 0.8
        or bool(behavior.get("candidate_dropoff"))
    )


def build_daily_inspection_trigger(
    *,
    trigger_reason: str,
    sample_count: int = 0,
    sample_scope: dict[str, Any] | None = None,
    anonymization_status: str = "anonymized",
    audit_metadata: dict[str, Any] | None = None,
) -> EvolutionRunTrigger:
    data_scope = {
        "inspection_type": "daily",
        "sample_scope": dict(sample_scope or {}),
    }
    return build_manual_trigger(
        trigger_type="daily_inspection",
        trigger_reason=trigger_reason,
        sample_count=sample_count,
        data_scope=data_scope,
        anonymization_status=anonymization_status,
        audit_metadata=audit_metadata,
    )
