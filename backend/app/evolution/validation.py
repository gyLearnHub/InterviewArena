from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.evolution.regression import build_regression_scope, collect_regression_samples
from app.evolution.risk_classifier import can_apply_after_manual_approval, can_auto_apply_candidate

GLOBAL_BLOCKING_STATUSES = {"failed", "blocked"}


def validate_candidate(
    repository: Any,
    candidate_id: int,
    *,
    validation_type: str = "pre_apply_gate",
    sample_count: int = 0,
    regression_scope: dict[str, Any] | None = None,
    manual_approval: bool = False,
) -> Any:
    candidate = repository.get_evolution_candidate(candidate_id=candidate_id, user_id=None)
    if candidate is None:
        raise ValueError("candidate not found")
    baseline = repository.get_active_version_bundle(scope_type="global", scope_key=None)
    requested_sample_count = sample_count or _default_sample_count(validation_type)
    regression = build_regression_scope(
        repository=repository,
        requested_sample_count=requested_sample_count,
        data_scope=regression_scope,
    )
    samples = collect_regression_samples(
        repository,
        requested_sample_count=requested_sample_count,
        data_scope=regression,
    )
    replay_result = _replay_gate(repository, candidate, samples=samples)
    hard_rule_result = _hard_rule_gate(candidate, replay_result)
    schema_result = _schema_gate(candidate)
    api_contract_result = _api_contract_gate(candidate)
    report_quality_diff = _report_quality_gate(candidate, samples)
    repeat_rate_diff = _repeat_rate_gate(candidate, samples)
    score_distribution_diff = _score_distribution_gate(candidate, samples)
    output_comparison_result = _output_comparison_gate(
        repository,
        candidate,
        samples=samples,
        replay_result=replay_result,
    )
    test_result = _test_gate(candidate)
    blocking = any(
        item["status"] in GLOBAL_BLOCKING_STATUSES
        for item in [
            replay_result,
            hard_rule_result,
            schema_result,
            api_contract_result,
            report_quality_diff,
            repeat_rate_diff,
            score_distribution_diff,
            output_comparison_result,
            test_result,
        ]
    )
    applicable = (
        can_auto_apply_candidate(candidate.candidate_type, candidate.risk_level)
        or (
            manual_approval
            and candidate.approval_status == "approved"
            and can_apply_after_manual_approval(candidate.candidate_type, candidate.risk_level)
        )
    )
    can_apply = not blocking and applicable
    status = "passed" if can_apply else "blocked"
    details = {
        "can_apply": can_apply,
        "manual_approval": manual_approval,
        "regression_scope": regression,
        "replay_result": replay_result,
        "regression_samples": samples,
        "baseline_vs_candidate_comparison": output_comparison_result,
        "global_blocked": blocking,
        "evidence_package": {
            "change_summary": candidate.proposal,
            "root_cause": candidate.root_cause,
            "impact_scope": candidate.impact_scope,
            "rollback_plan": _rollback_plan(candidate),
            "risk_level": candidate.risk_level,
            "confirmation_gates": _confirmation_gates(candidate),
        },
    }
    validation = repository.create_validation_run(
        candidate_id=candidate.id,
        validation_type=validation_type,
        status=status,
        sample_count=int(samples.get("sample_count") or requested_sample_count),
        baseline_bundle_id=getattr(baseline, "id", None),
        candidate_bundle_id=None,
        hard_rule_result=hard_rule_result,
        soft_rule_diff=_status_payload("passed", "Soft-rule diff is recorded in candidate diff."),
        schema_result=schema_result,
        api_contract_result=api_contract_result,
        report_quality_diff=report_quality_diff,
        repeat_rate_diff=repeat_rate_diff,
        score_distribution_diff=score_distribution_diff,
        test_result=test_result,
        details=details,
    )
    repository.update_candidate_status(
        candidate.id,
        status="validation_passed" if can_apply else "waiting_approval",
        validation_summary={
            "status": status,
            "can_apply": can_apply,
            "manual_approval": manual_approval,
            "blocking": blocking,
            "validation_id": getattr(validation, "id", None),
        },
    )
    return validation


def _replay_gate(repository: Any, candidate: Any, *, samples: dict[str, Any]) -> dict[str, Any]:
    replay_method = getattr(repository, "run_candidate_replay_gate", None)
    if callable(replay_method):
        result = replay_method(candidate=candidate, samples=samples)
        if isinstance(result, Mapping):
            return dict(result)
        return _status_payload("passed", "Repository replay gate returned no structured payload.")
    connection = getattr(repository, "connection", None)
    if connection is None:
        return _status_payload("passed", "In-memory repository accepted replay gate.")
    try:
        from app.repositories.harness import HarnessRepository

        harness = HarnessRepository(connection)
        replay_runs: list[dict[str, Any]] = []
        for interview_id in _candidate_interview_ids(candidate, samples):
            for trace in harness.list_traces(interview_id, limit=3):
                result = harness.replay_trace(
                    trace_id=trace.id,
                    user_id=trace.user_id,
                    reason=f"evolution validation candidate {candidate.id}",
                    options={"candidate_id": candidate.id},
                )
                replay_runs.append(result)
        failed = [item for item in replay_runs if item.get("status") != "completed"]
        if failed:
            return {
                "status": "failed",
                "message": "One or more Harness replay runs failed.",
                "replay_runs": replay_runs,
            }
        return {
            "status": "passed",
            "message": "Harness replay gate completed without business mutation.",
            "replay_runs": replay_runs,
            "replay_sample_count": len(replay_runs),
        }
    except Exception as exc:
        return _status_payload("failed", str(exc) or exc.__class__.__name__)


def _hard_rule_gate(candidate: Any, replay_result: dict[str, Any]) -> dict[str, Any]:
    root_cause = getattr(candidate, "root_cause", {}) or {}
    if root_cause.get("category") == "harness_failure":
        return _status_payload("blocked", "Harness hard rule failures require manual handling.")
    if replay_result.get("status") in GLOBAL_BLOCKING_STATUSES:
        return _status_payload("blocked", "Harness replay failed.")
    return _status_payload("passed", "No hard-rule blocker in candidate proposal.")


def _schema_gate(candidate: Any) -> dict[str, Any]:
    payload = _candidate_text(candidate)
    if "schema" in payload or "json schema" in payload:
        return _status_payload("blocked", "Schema-affecting changes require explicit review.")
    return _status_payload("passed", "No JSON Schema change declared.")


def _api_contract_gate(candidate: Any) -> dict[str, Any]:
    payload = _candidate_text(candidate)
    if "api_contract" in payload or "api contract" in payload or "接口契约" in payload:
        return _status_payload("blocked", "API contract changes are not auto-applicable.")
    return _status_payload("passed", "No API contract change declared.")


def _report_quality_gate(candidate: Any, samples: dict[str, Any]) -> dict[str, Any]:
    aggregate = _aggregate_metrics(samples)
    payload = _candidate_text(candidate)
    declared_drop = _declared_negative_delta(candidate, "report_quality")
    if declared_drop < 0 or "reduce_report_detail" in payload:
        return {
            "status": "blocked",
            "message": "Candidate declares a report-quality regression.",
            "baseline_report_vague_rate": aggregate.get("report_vague_rate", 0.0),
            "declared_delta": declared_drop,
        }
    return {
        "status": "passed",
        "message": "Report quality gate has no declared regression.",
        "baseline_report_vague_rate": aggregate.get("report_vague_rate", 0.0),
        "sample_count": samples.get("sample_count", 0),
    }


def _repeat_rate_gate(candidate: Any, samples: dict[str, Any]) -> dict[str, Any]:
    aggregate = _aggregate_metrics(samples)
    payload = _candidate_text(candidate)
    declared_delta = _declared_negative_delta(candidate, "repeat_rate")
    if declared_delta > 0 or "allow_repeat" in payload:
        return {
            "status": "blocked",
            "message": "Candidate would increase question repeat rate.",
            "baseline_repeat_rate": aggregate.get("average_repeat_rate", 0.0),
            "declared_delta": declared_delta,
        }
    return {
        "status": "passed",
        "message": "Repeat-rate gate has no declared increase.",
        "baseline_repeat_rate": aggregate.get("average_repeat_rate", 0.0),
        "baseline_max_similarity": aggregate.get("max_similarity", 0.0),
        "sample_count": samples.get("sample_count", 0),
    }


def _score_distribution_gate(candidate: Any, samples: dict[str, Any]) -> dict[str, Any]:
    aggregate = _aggregate_metrics(samples)
    declared_delta = _declared_negative_delta(candidate, "score_distribution_width")
    if declared_delta > 0:
        return {
            "status": "blocked",
            "message": "Candidate declares wider score distribution.",
            "baseline_score_min": aggregate.get("score_min"),
            "baseline_score_max": aggregate.get("score_max"),
            "declared_delta": declared_delta,
        }
    return {
        "status": "passed",
        "message": "Score-distribution gate has no declared widening.",
        "baseline_score_average": aggregate.get("score_average", 0.0),
        "baseline_score_min": aggregate.get("score_min"),
        "baseline_score_max": aggregate.get("score_max"),
        "sample_count": samples.get("sample_count", 0),
    }


def _output_comparison_gate(
    repository: Any,
    candidate: Any,
    *,
    samples: dict[str, Any],
    replay_result: dict[str, Any],
) -> dict[str, Any]:
    compare_method = getattr(repository, "compare_candidate_outputs", None)
    if callable(compare_method):
        result = compare_method(candidate=candidate, samples=samples, replay_result=replay_result)
        return result if isinstance(result, dict) else _status_payload(
            "failed",
            "Candidate output comparison returned an unsupported result.",
        )
    if replay_result.get("status") in GLOBAL_BLOCKING_STATUSES:
        return _status_payload("blocked", "Replay failed before output comparison.")
    declared = _declared_output_delta(candidate)
    if declared.get("api_contract_changed") and not declared.get("api_contract_declared"):
        return {
            "status": "blocked",
            "message": "Candidate declares an undeclared API contract change.",
            "declared_delta": declared,
        }
    return {
        "status": "passed",
        "message": "Static baseline/candidate comparison found no declared regression.",
        "comparison_mode": "static_declared_delta",
        "regression_sample_set_version": samples.get("regression_sample_set_version"),
        "sample_ids": [
            item.get("sample_id")
            for item in samples.get("regression_samples", [])
            if isinstance(item, dict)
        ],
        "declared_delta": declared,
    }


def _test_gate(candidate: Any) -> dict[str, Any]:
    proposal = getattr(candidate, "proposal", {}) or {}
    if candidate.candidate_type != "backend_patch":
        return _status_payload("passed", "No backend file patch will be executed.")
    test_result = proposal.get("test_result") or {}
    replay_result = proposal.get("replay_result") or {}
    if test_result.get("status") == "passed" and replay_result.get("status") == "passed":
        return {
            "status": "passed",
            "message": "Backend patch draft has test and replay evidence.",
            "test_result": test_result,
            "replay_result": replay_result,
        }
    return {
        "status": "blocked",
        "message": "Backend patch draft requires passing test and replay evidence.",
        "test_result": test_result,
        "replay_result": replay_result,
    }


def _candidate_interview_ids(candidate: Any, samples: dict[str, Any]) -> list[int]:
    values: list[Any] = []
    impact_scope = getattr(candidate, "impact_scope", {}) or {}
    if impact_scope.get("interview_id") is not None:
        values.append(impact_scope.get("interview_id"))
    for sample in samples.get("signals", []):
        refs = sample.get("source_refs") if isinstance(sample, dict) else None
        if isinstance(refs, dict) and refs.get("interview_id") is not None:
            values.append(refs["interview_id"])
    interview_ids: list[int] = []
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in interview_ids:
            interview_ids.append(parsed)
    return interview_ids[:5]


def _rollback_plan(candidate: Any) -> dict[str, Any]:
    return {
        "strategy": "reactivate_previous_version_bundle",
        "candidate_id": getattr(candidate, "id", None),
        "target_artifact_key": getattr(candidate, "target_artifact_key", None),
    }


def _confirmation_gates(candidate: Any) -> dict[str, Any]:
    risk_level = str(getattr(candidate, "risk_level", "") or "")
    base = {
        "change_summary": True,
        "root_cause": bool(getattr(candidate, "root_cause", None)),
        "harness_replay_result": True,
        "hard_rule_result": True,
        "soft_rule_diff": True,
        "report_quality_diff": True,
        "score_distribution_diff": True,
        "api_contract_result": True,
        "test_result": True,
        "rollback_plan": True,
    }
    if risk_level == "high":
        base.update(
            {
                "impact_analysis": True,
                "permission_isolation_check": True,
                "latest_50_regression": True,
                "gray_release_suggestion": True,
                "post_release_monitoring": True,
            }
        )
    return base


def _candidate_text(candidate: Any) -> str:
    return f"{candidate.candidate_type} {candidate.proposal} {candidate.diff}".casefold()


def _declared_output_delta(candidate: Any) -> dict[str, Any]:
    output_delta: dict[str, Any] = {}
    for source_name in ("proposal", "diff", "validation_summary"):
        source = getattr(candidate, source_name, None)
        if isinstance(source, dict):
            output_delta.update(_dict(source.get("expected_delta")))
            output_delta.update(_dict(source.get("output_delta")))
            if "api_contract_changed" in source:
                output_delta["api_contract_changed"] = source["api_contract_changed"]
            if "api_contract_declared" in source:
                output_delta["api_contract_declared"] = source["api_contract_declared"]
    return output_delta


def _aggregate_metrics(samples: dict[str, Any]) -> dict[str, Any]:
    value = samples.get("aggregate_metrics")
    return value if isinstance(value, dict) else {}


def _declared_negative_delta(candidate: Any, key: str) -> float:
    values: list[Any] = []
    for source_name in ("proposal", "diff", "validation_summary"):
        source = getattr(candidate, source_name, None)
        if isinstance(source, dict):
            values.extend(
                [
                    source.get(key),
                    source.get(f"{key}_delta"),
                    _dict(source.get("expected_delta")).get(key),
                ]
            )
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _default_sample_count(validation_type: str) -> int:
    return 50 if "50" in validation_type or "deep" in validation_type else 10


def _status_payload(status: str, message: str) -> dict[str, Any]:
    return {"status": status, "message": message}
