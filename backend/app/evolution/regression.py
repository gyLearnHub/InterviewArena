from __future__ import annotations

import hashlib
from typing import Any

from app.evolution.anonymization import aggregate_anonymized_signals


def build_regression_scope(
    *,
    repository: Any,
    requested_sample_count: int = 10,
    data_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del repository
    scope = dict(data_scope or {})
    scope.setdefault("sample_count", requested_sample_count)
    scope.setdefault("anonymized", True)
    scope.setdefault("source", "aggregated_quality_signals")
    scope.setdefault(
        "required_sample_fields",
        [
            "sample_id",
            "job_category",
            "question_type",
            "quality_label",
            "expected_rule_result",
            "expected_score_range",
        ],
    )
    return scope


def collect_regression_samples(
    repository: Any,
    *,
    requested_sample_count: int,
    data_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    list_signals = getattr(repository, "list_quality_signals", None)
    if not callable(list_signals):
        return {
            "sample_count": 0,
            "requested_sample_count": requested_sample_count,
            "anonymized": True,
            "source": "unavailable",
            "signals": [],
        }
    signals = list_signals(limit=requested_sample_count)
    regression_samples = [
        _build_regression_sample(signal, index=index)
        for index, signal in enumerate(signals, start=1)
    ]
    aggregate = aggregate_anonymized_signals(list(signals))
    aggregate.update(
        {
            "requested_sample_count": requested_sample_count,
            "anonymized": True,
            "source": "aggregated_quality_signals",
            "data_scope": dict(data_scope or {}),
            "regression_sample_set_version": _sample_set_version(regression_samples),
            "regression_samples": regression_samples,
        }
    )
    return aggregate


def _build_regression_sample(signal: Any, *, index: int) -> dict[str, Any]:
    value = _as_dict(signal)
    metrics = _dict(value.get("metrics"))
    score = _score(metrics.get("score"))
    return {
        "sample_id": f"quality-signal-{value.get('id') or index}",
        "source_signal_id": value.get("id"),
        "version_bundle_id": value.get("version_bundle_id"),
        "job_category": value.get("job_family") or "unknown",
        "question_type": _question_type(metrics, value),
        "quality_label": value.get("severity") or "unknown",
        "expected_rule_result": _expected_rule_result(value),
        "expected_score_range": _expected_score_range(score),
        "anonymized": True,
    }


def _sample_set_version(samples: list[dict[str, Any]]) -> str:
    ids = ",".join(str(item["sample_id"]) for item in samples)
    digest = hashlib.sha256(ids.encode("utf-8")).hexdigest()[:12]
    return f"regression-set-v3.2-{len(samples)}-{digest}"


def _question_type(metrics: dict[str, Any], signal: dict[str, Any]) -> str:
    for source in (
        metrics,
        _dict(metrics.get("question_quality")),
        _dict(signal.get("source_refs")),
    ):
        value = source.get("question_type") or source.get("round_type")
        if value:
            return str(value)
    return "mixed"


def _expected_rule_result(signal: dict[str, Any]) -> str:
    if bool(signal.get("hard_trigger")):
        return "manual_review_required"
    if bool(signal.get("threshold_trigger")):
        return "soft_rule_warning_allowed"
    return "passed"


def _expected_score_range(score: int | None) -> dict[str, int | None]:
    if score is None:
        return {"min": None, "max": None}
    return {"min": max(0, score - 10), "max": min(100, score + 10)}


def _score(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
