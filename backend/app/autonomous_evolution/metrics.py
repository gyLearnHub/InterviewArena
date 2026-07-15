from __future__ import annotations

from statistics import fmean
from typing import Any


def historical_quality_score(sample: dict[str, Any]) -> float:
    components: list[tuple[float, float]] = []
    score = _number(sample.get("report_score"))
    if score is not None:
        components.append((min(1.0, max(0.0, score / 100.0)), 0.4))
    components.append((1.0 if sample.get("harness_status") == "completed" else 0.0, 0.15))

    rules = sample.get("harness_rules") or []
    if rules:
        passed = sum(1 for item in rules if item.get("status") == "passed")
        components.append((passed / len(rules), 0.15))

    qa_history = [
        item
        for item in sample.get("qa_history") or []
        if item.get("question_status", "active") == "active"
    ]
    if qa_history:
        normalized = [_normalize_question(str(item.get("question") or "")) for item in qa_history]
        nonempty = [item for item in normalized if item]
        unique_ratio = len(set(nonempty)) / len(nonempty) if nonempty else 0.0
        answered_count = sum(
            bool(str(item.get("answer") or "").strip()) for item in qa_history
        )
        answered_ratio = answered_count / len(qa_history)
        components.append(((unique_ratio + answered_ratio) / 2.0, 0.15))

    ratings = [
        rating
        for item in sample.get("user_feedback") or []
        if (rating := _number(item.get("rating"))) is not None
    ]
    if ratings:
        components.append((min(1.0, max(0.0, fmean(ratings) / 5.0)), 0.15))

    total_weight = sum(weight for _, weight in components)
    return sum(value * weight for value, weight in components) / total_weight


def aggregate_metrics(items: list[dict[str, float]]) -> dict[str, float]:
    keys = sorted({key for item in items for key in item})
    return {
        key: fmean(float(item[key]) for item in items if key in item)
        for key in keys
    }


def max_regression(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> tuple[float, list[str]]:
    regressions: list[tuple[str, float]] = []
    for key, old_value in baseline.items():
        if key not in candidate:
            continue
        regressions.append((key, old_value - candidate[key]))
    if not regressions:
        return 0.0, []
    worst = max(value for _, value in regressions)
    return worst, [key for key, value in regressions if value > 0.05]


def _normalize_question(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
