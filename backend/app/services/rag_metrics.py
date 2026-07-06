from dataclasses import dataclass
from statistics import quantiles
from typing import Any


@dataclass(frozen=True)
class RagEvaluationCase:
    relevant_ids: set[str]
    retrieved_ids: list[str]
    reranked_ids: list[str]
    latency_ms: float
    fallback_reason: str | None = None
    success: bool = True


def calculate_rag_metrics(
    cases: list[RagEvaluationCase | dict[str, Any]],
    *,
    k: int = 5,
) -> dict[str, float]:
    normalized = [_to_case(case) for case in cases]
    if not normalized:
        return {
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "reranker_hit_rate": 0.0,
            "reranker_hit_improvement": 0.0,
            "p95_latency_ms": 0.0,
            "degradation_rate": 0.0,
            "non_degraded_failure_rate": 0.0,
        }

    recall = sum(_recall_at_k(case.reranked_ids, case.relevant_ids, k) for case in normalized)
    mrr = sum(_reciprocal_rank(case.reranked_ids, case.relevant_ids) for case in normalized)
    before_hit_rate = sum(
        _has_hit(case.retrieved_ids[:k], case.relevant_ids) for case in normalized
    )
    after_hit_rate = sum(_has_hit(case.reranked_ids[:k], case.relevant_ids) for case in normalized)
    degradation_count = sum(1 for case in normalized if case.fallback_reason)
    non_degraded_failures = sum(
        1 for case in normalized if not case.success and not case.fallback_reason
    )
    total = len(normalized)
    return {
        "recall_at_k": recall / total,
        "mrr": mrr / total,
        "reranker_hit_rate": after_hit_rate / total,
        "reranker_hit_improvement": (after_hit_rate - before_hit_rate) / total,
        "p95_latency_ms": _p95([case.latency_ms for case in normalized]),
        "degradation_rate": degradation_count / total,
        "non_degraded_failure_rate": non_degraded_failures / total,
    }


def _to_case(case: RagEvaluationCase | dict[str, Any]) -> RagEvaluationCase:
    if isinstance(case, RagEvaluationCase):
        return case
    return RagEvaluationCase(
        relevant_ids={str(item) for item in case.get("relevant_ids", [])},
        retrieved_ids=[str(item) for item in case.get("retrieved_ids", [])],
        reranked_ids=[str(item) for item in case.get("reranked_ids", [])],
        latency_ms=float(case.get("latency_ms", 0.0)),
        fallback_reason=case.get("fallback_reason"),
        success=bool(case.get("success", True)),
    )


def _recall_at_k(ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    return len(set(ids[:k]) & relevant_ids) / len(relevant_ids)


def _reciprocal_rank(ids: list[str], relevant_ids: set[str]) -> float:
    for index, item in enumerate(ids, start=1):
        if item in relevant_ids:
            return 1.0 / index
    return 0.0


def _has_hit(ids: list[str], relevant_ids: set[str]) -> int:
    return 1 if set(ids) & relevant_ids else 0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=20, method="inclusive")[18]
