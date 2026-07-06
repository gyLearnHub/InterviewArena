import pytest


def test_rag_metrics_cover_recall_mrr_reranker_latency_and_failure_rates() -> None:
    from app.services.rag_metrics import calculate_rag_metrics

    metrics = calculate_rag_metrics(
        [
            {
                "relevant_ids": [1],
                "retrieved_ids": [2, 1],
                "reranked_ids": [1, 2],
                "latency_ms": 10,
                "fallback_reason": None,
                "success": True,
            },
            {
                "relevant_ids": [3],
                "retrieved_ids": [3],
                "reranked_ids": [3],
                "latency_ms": 20,
                "fallback_reason": "chroma unavailable",
                "success": True,
            },
            {
                "relevant_ids": [4],
                "retrieved_ids": [],
                "reranked_ids": [],
                "latency_ms": 100,
                "fallback_reason": None,
                "success": False,
            },
        ],
        k=1,
    )

    assert metrics["recall_at_k"] == pytest.approx(2 / 3)
    assert metrics["mrr"] == pytest.approx(2 / 3)
    assert metrics["reranker_hit_rate"] == pytest.approx(2 / 3)
    assert metrics["reranker_hit_improvement"] == pytest.approx(1 / 3)
    assert metrics["p95_latency_ms"] == pytest.approx(92)
    assert metrics["degradation_rate"] == pytest.approx(1 / 3)
    assert metrics["non_degraded_failure_rate"] == pytest.approx(1 / 3)
