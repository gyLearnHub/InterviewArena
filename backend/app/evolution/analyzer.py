from __future__ import annotations

from typing import Any

from app.evolution.candidate_generator import generate_candidates_from_signal


def analyze_run(repository: Any, run_id: int, *, signals: list[Any] | None = None) -> list[Any]:
    update_status = getattr(repository, "update_evolution_run_status", None)
    run = _get_run(repository, run_id)
    if callable(update_status):
        update_status(run_id, status="analyzing")
    try:
        candidate_payloads: list[dict[str, Any]] = []
        for signal in signals or _signals_for_run(repository, run_id):
            candidate_payloads.extend(generate_candidates_from_signal(signal))
        if not candidate_payloads:
            if callable(update_status):
                update_status(
                    run_id,
                    status="completed",
                    completed=True,
                    error_message=(
                        "No actionable candidate could be generated from available signals."
                    ),
                )
            return []
        created = [
            repository.create_candidate(run_id=run_id, **payload) for payload in candidate_payloads
        ]
        _auto_apply_low_risk(repository, created, run=run)
        _record_run_audit(repository, run_id, created)
        if callable(update_status):
            update_status(run_id, status="completed", completed=True)
        return created
    except Exception as exc:
        if callable(update_status):
            update_status(
                run_id,
                status="failed",
                completed=True,
                error_message=str(exc) or exc.__class__.__name__,
            )
        raise


def _signals_for_run(repository: Any, run_id: int) -> list[Any]:
    run = _get_run(repository, run_id)
    data_scope = getattr(run, "data_scope", {}) if run is not None else {}
    signal_id = data_scope.get("quality_signal_id") if isinstance(data_scope, dict) else None
    list_signals = getattr(repository, "list_quality_signals", None)
    if not callable(list_signals):
        return []
    signals = list(list_signals(limit=100))
    if signal_id is None:
        return signals[:1]
    return [signal for signal in signals if getattr(signal, "id", None) == signal_id]


def _auto_apply_low_risk(repository: Any, candidates: list[Any], *, run: Any | None) -> None:
    try:
        from app.evolution.applier import apply_candidate
        from app.evolution.risk_classifier import can_auto_apply_candidate

        for candidate in candidates:
            if can_auto_apply_candidate(candidate.candidate_type, candidate.risk_level):
                apply_candidate(
                    repository,
                    candidate.id,
                    validation_sample_count=int(getattr(run, "sample_count", 0) or 0),
                    regression_scope=getattr(run, "data_scope", {}) if run is not None else {},
                )
    except Exception:
        return


def _get_run(repository: Any, run_id: int) -> Any | None:
    get_run = getattr(repository, "get_evolution_run", None)
    return get_run(run_id) if callable(get_run) else None


def _record_run_audit(repository: Any, run_id: int, candidates: list[Any]) -> None:
    merge_metadata = getattr(repository, "merge_evolution_run_audit_metadata", None)
    if not callable(merge_metadata):
        return
    refreshed = [_refresh_candidate(repository, candidate) for candidate in candidates]
    merge_metadata(
        run_id,
        {
            "validation_result": {
                "candidate_count": len(refreshed),
                "candidate_statuses": {
                    str(_candidate_id(candidate)): _candidate_value(candidate, "validation_summary")
                    for candidate in refreshed
                },
            },
            "application_result": {
                "candidate_count": len(refreshed),
                "candidate_statuses": {
                    str(_candidate_id(candidate)): _candidate_value(candidate, "application_result")
                    for candidate in refreshed
                },
            },
        },
    )


def _refresh_candidate(repository: Any, candidate: Any) -> Any:
    get_candidate = getattr(repository, "get_evolution_candidate", None)
    if not callable(get_candidate):
        return candidate
    return get_candidate(candidate_id=_candidate_id(candidate), user_id=None) or candidate


def _candidate_id(candidate: Any) -> int:
    if isinstance(candidate, dict):
        return int(candidate["id"])
    return int(candidate.id)


def _candidate_value(candidate: Any, key: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key)
    return getattr(candidate, key, None)
