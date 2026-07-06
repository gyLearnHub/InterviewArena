from __future__ import annotations

from typing import Any

RAW_PRIVATE_KEYS = {
    "resume",
    "answer",
    "question",
    "final_conclusion",
    "job_description",
    "input_snapshot",
    "output_snapshot",
    "qa_history",
    "transcript",
    "candidate_name",
    "email",
    "phone",
    "content",
}


def anonymize_signal_for_global_use(signal: Any) -> dict[str, Any]:
    value = _as_dict(signal)
    metrics = dict(value.get("metrics") or {})
    return {
        "id": value.get("id"),
        "signal_type": value.get("signal_type"),
        "severity": value.get("severity"),
        "job_family": value.get("job_family"),
        "version_bundle_id": value.get("version_bundle_id"),
        "hard_trigger": bool(value.get("hard_trigger")),
        "threshold_trigger": bool(value.get("threshold_trigger")),
        "metrics": _strip_private(metrics),
    }


def aggregate_anonymized_signals(signals: list[Any]) -> dict[str, Any]:
    sanitized = [anonymize_signal_for_global_use(signal) for signal in signals]
    severity_counts: dict[str, int] = {}
    repeat_rates: list[float] = []
    similarity_values: list[float] = []
    report_vague_count = 0
    job_match_low_count = 0
    difficulty_anomaly_count = 0
    follow_up_low_count = 0
    scores: list[int] = []
    for item in sanitized:
        severity = str(item.get("severity") or "unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        question_quality = metrics.get("question_quality") if isinstance(metrics, dict) else {}
        report_quality = metrics.get("report_quality") if isinstance(metrics, dict) else {}
        job_match = metrics.get("job_match") if isinstance(metrics, dict) else {}
        difficulty = metrics.get("difficulty") if isinstance(metrics, dict) else {}
        follow_up = metrics.get("follow_up_quality") if isinstance(metrics, dict) else {}
        score = metrics.get("score") if isinstance(metrics, dict) else None
        repeat_rates.append(_float(_dict(question_quality).get("repeat_rate")))
        similarity_values.append(_float(_dict(question_quality).get("max_similarity")))
        if _float(_dict(report_quality).get("vagueness_score")) >= 0.55:
            report_vague_count += 1
        if _float(_dict(job_match).get("match_score"), default=1.0) < 0.25:
            job_match_low_count += 1
        if bool(_dict(difficulty).get("difficulty_anomaly")):
            difficulty_anomaly_count += 1
        if _float(_dict(follow_up).get("quality_score"), default=1.0) < 0.4:
            follow_up_low_count += 1
        if isinstance(score, int):
            scores.append(score)
        elif isinstance(score, float):
            scores.append(int(score))
    sample_count = len(sanitized)
    return {
        "sample_count": sample_count,
        "severity_counts": severity_counts,
        "aggregate_metrics": {
            "average_repeat_rate": _average(repeat_rates),
            "max_similarity": max(similarity_values) if similarity_values else 0.0,
            "report_vague_rate": _rate(report_vague_count, sample_count),
            "job_match_low_rate": _rate(job_match_low_count, sample_count),
            "difficulty_anomaly_rate": _rate(difficulty_anomaly_count, sample_count),
            "follow_up_low_rate": _rate(follow_up_low_count, sample_count),
            "score_average": _average([float(item) for item in scores]),
            "score_min": min(scores) if scores else None,
            "score_max": max(scores) if scores else None,
        },
        "signals": sanitized,
    }


def _strip_private(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_private(item)
            for key, item in value.items()
            if not _is_private_key(key)
        }
    if isinstance(value, list):
        return [_strip_private(item) for item in value]
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _is_private_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized in RAW_PRIVATE_KEYS or any(
        marker in normalized
        for marker in (
            "raw_resume",
            "raw_answer",
            "raw_question",
            "input_snapshot",
            "output_snapshot",
        )
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)
