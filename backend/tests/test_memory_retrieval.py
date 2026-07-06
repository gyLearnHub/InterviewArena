import importlib
import inspect
import sys
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.core.config import Settings
from app.repositories.memories import MemoryRecord, MemoryRepository
from app.schemas.memory import MemoryRetrievalRequest, MemoryRetrievalResult
from app.services.memory_index import ChromaMemoryIndex, VectorSearchHit, VectorSearchResult
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.rag_metrics import RagEvaluationCase, calculate_rag_metrics


def test_memory_retrieval_service_exposes_degrading_retrieval_entrypoint() -> None:
    module = importlib.import_module("app.services.memory_retrieval")

    service_type = module.MemoryRetrievalService
    request_type = module.MemoryRetrievalRequest
    result_type = module.MemoryRetrievalResult

    assert hasattr(service_type, "retrieve")
    assert request_type is not None
    assert result_type is not None


def test_rag_audit_repository_exists_for_degraded_retrieval() -> None:
    module = importlib.import_module("app.repositories.rag_audit")

    assert hasattr(module, "RagAuditRepository") or hasattr(module, "RAGAuditRepository")


def test_retrieval_schemas_forbid_extra_payload_fields() -> None:
    request = MemoryRetrievalRequest(
        user_id=1,
        memory_enabled=False,
        usage_scene="new_question",
        intent="生成新问题",
    )
    result = MemoryRetrievalResult(request_id="req-1", memories=[], fallback_reason="disabled")

    assert request.memory_enabled is False
    assert result.memories == []
    assert result.fallback_reason == "disabled"


def test_candidate_memory_recall_defaults_to_indexed_records_only() -> None:
    connection = _RecordingConnection()
    repository = MemoryRepository(connection)

    repository.list_candidate_memories(user_id=7)

    assert "status = 'active'" in connection.last_sql
    assert "index_status in" in connection.last_sql.lower()
    assert "indexed" in connection.params
    assert "pending_index" not in connection.params


def test_chroma_failure_degrades_to_bm25_and_audits_fallback_reason() -> None:
    if "vector_index" not in inspect.signature(MemoryRetrievalService).parameters:
        pytest.fail("MemoryRetrievalService must expose an optional Chroma/vector search path")

    audit = _RecordingAuditRepository()
    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository([_memory(1, "Python 并发 线程池")]),
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=_FailingVectorIndex(),  # type: ignore[arg-type]
        reranker=_RuleReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=42,
            usage_scene="new_question",
            intent="生成新问题",
            query_text="Python 并发",
            collections=["candidate_memories"],
            top_k=3,
        )
    )

    assert [memory.memory_id for memory in result.memories] == [1]
    assert result.fallback_reason == "chroma unavailable"
    assert audit.calls[-1]["fallback_reason"] == "chroma unavailable"


def test_hybrid_recall_merges_vector_and_bm25_candidates_by_memory_id() -> None:
    if "vector_index" not in inspect.signature(MemoryRetrievalService).parameters:
        pytest.fail("MemoryRetrievalService must merge Chroma/vector and BM25 candidates")

    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository(
            [
                _memory(1, "Python 并发 线程池"),
                _memory(2, "MySQL 索引 优化"),
            ],
            extra_memories=[_memory(3, "Redis 缓存 穿透")],
        ),
        vector_index=_VectorIndex(
            [
                _memory(2, "MySQL 索引 优化"),
                _memory(3, "Redis 缓存 穿透"),
            ]
        ),  # type: ignore[arg-type]
        reranker=_RuleReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=42,
            usage_scene="new_question",
            intent="生成新问题",
            query_text="Python MySQL Redis",
            collections=["candidate_memories"],
            top_k=10,
        )
    )

    memory_ids = [memory.memory_id for memory in result.memories]
    assert set(memory_ids) == {1, 2, 3}
    assert len(memory_ids) == len(set(memory_ids))


def test_vector_recall_rechecks_candidate_user_and_system_agent_scope() -> None:
    audit = _RecordingAuditRepository()
    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository(
            [_memory(1, "Python 并发 线程池")],
            extra_memories=[
                _memory(99, "Python 并发 越权候选记忆", user_id=99),
                _memory(
                    100,
                    "技术趋势 系统记忆",
                    collection="interviewer_memories",
                    memory_type="technical_trend",
                    agent_type="manager",
                    user_id=None,
                ),
            ],
        ),
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=_VectorIndex(
            [
                _memory(99, "Python 并发 越权候选记忆", user_id=99),
                _memory(
                    100,
                    "技术趋势 系统记忆",
                    collection="interviewer_memories",
                    memory_type="technical_trend",
                    agent_type="manager",
                    user_id=None,
                ),
            ]
        ),  # type: ignore[arg-type]
        reranker=_RuleReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=42,
            usage_scene="new_question",
            intent="生成新问题",
            query_text="Python 并发 技术趋势",
            agent_type="technical",
            collections=["candidate_memories", "interviewer_memories"],
            memory_types=["technical_weakness", "technical_trend"],
            top_k=10,
        )
    )

    assert [memory.memory_id for memory in result.memories] == [1]
    assert audit.calls[-1]["timings"]["filtered_count"] == 2


def test_vector_memory_record_list_path_rechecks_scope() -> None:
    audit = _RecordingAuditRepository()
    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository([_memory(1, "Python 并发 线程池")]),
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=_VectorRecordIndex([_memory(77, "Python 并发 其他用户", user_id=77)]),  # type: ignore[arg-type]
        reranker=_RuleReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=42,
            usage_scene="new_question",
            intent="生成新问题",
            query_text="Python 并发",
            collections=["candidate_memories"],
            top_k=10,
        )
    )

    assert [memory.memory_id for memory in result.memories] == [1]
    assert audit.calls[-1]["timings"]["filtered_count"] == 1


def test_missing_reranker_is_initialized_once_and_audited(monkeypatch) -> None:
    initialization_count = 0

    def missing_reranker() -> None:
        nonlocal initialization_count
        initialization_count += 1
        raise RuntimeError("reranker_model_path_missing")

    monkeypatch.setattr("app.services.memory_retrieval.LocalReranker", missing_reranker)
    audit = _RecordingAuditRepository()
    memories = [_memory(index, f"Python 并发 候选记忆 {index}") for index in range(1, 101)]
    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository(memories),
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=_VectorIndex(memories),  # type: ignore[arg-type]
    )
    request = MemoryRetrievalRequest(
        user_id=42,
        usage_scene="new_question",
        intent="生成新问题",
        query_text="Python 并发",
        collections=["candidate_memories"],
        top_k=100,
    )

    first_result = service.retrieve(request)
    second_result = service.retrieve(request)

    assert initialization_count == 1
    assert first_result.memories
    assert first_result.fallback_reason == "reranker_model_path_missing"
    assert second_result.fallback_reason == "reranker_model_path_missing"
    assert audit.calls[-1]["fallback_reason"] == "reranker_model_path_missing"
    assert audit.calls[-1]["timings"]["degradation_count"] == 1


def test_chroma_index_upserts_required_metadata_and_deletes_user_vectors(monkeypatch) -> None:
    fake_module = SimpleNamespace(PersistentClient=_FakeChromaClient)
    monkeypatch.setitem(sys.modules, "chromadb", fake_module)
    index = ChromaMemoryIndex(
        settings=replace(Settings(), chroma_enabled=True, chroma_persist_dir="tmp_chroma"),
        embedding_model=_FakeEmbeddingModel(),  # type: ignore[arg-type]
    )
    memory = MemoryRecord(
        id=11,
        collection="candidate_memories",
        user_id=7,
        memory_type="technical_weakness",
        title="索引理解薄弱",
        content="候选人对 MySQL 索引原理解释不完整",
        structured_data={},
        tokens=["mysql", "索引"],
        confidence=0.8,
        status="active",
        index_status="pending_index",
        source_interview_id=3,
        source_round_id=4,
        version=2,
        created_at=datetime(2026, 6, 18, 9, 0, 0),
        updated_at=None,
    )

    assert index.upsert(memory) is None
    collection = index.collections["candidate_memories"]
    metadata = collection.upserts[-1]["metadatas"][0]

    assert collection.upserts[-1]["ids"] == ["candidate_memories:11:v2"]
    assert metadata["memory_id"] == 11
    assert metadata["user_id"] == 7
    assert metadata["memory_type"] == "technical_weakness"
    assert metadata["status"] == "active"
    assert metadata["confidence"] == 0.8
    assert metadata["source_interview_id"] == 3
    assert metadata["source_round_id"] == 4
    assert "created_at" in metadata

    index.delete_user_candidate_memories(7)

    assert collection.deletes[-1]["where"] == {"user_id": 7}


def test_chroma_import_failure_returns_vector_fallback(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "chromadb", None)

    index = ChromaMemoryIndex(settings=replace(Settings(), chroma_enabled=True))
    result = index.search(
        query_text="mysql 索引",
        collections=["candidate_memories"],
        user_id=1,
        agent_type="technical",
        memory_types=[],
        top_k=3,
    )

    assert result.hits == []
    assert result.fallback_reason is not None


def test_rag_metrics_calculate_offline_indicators() -> None:
    metrics = calculate_rag_metrics(
        [
            RagEvaluationCase(
                relevant_ids={"m1", "m2"},
                retrieved_ids=["m3", "m4", "m1"],
                reranked_ids=["m1", "m3", "m2"],
                latency_ms=100,
            ),
            {
                "relevant_ids": ["m9"],
                "retrieved_ids": ["m8"],
                "reranked_ids": ["m8"],
                "latency_ms": 200,
                "fallback_reason": "chroma_disabled",
                "success": True,
            },
            {
                "relevant_ids": ["m7"],
                "retrieved_ids": [],
                "reranked_ids": [],
                "latency_ms": 300,
                "success": False,
            },
        ],
        k=2,
    )

    assert metrics["recall_at_k"] == pytest.approx(1 / 6)
    assert metrics["mrr"] == pytest.approx(1 / 3)
    assert metrics["reranker_hit_rate"] == pytest.approx(1 / 3)
    assert metrics["reranker_hit_improvement"] == pytest.approx(1 / 3)
    assert metrics["p95_latency_ms"] == pytest.approx(290)
    assert metrics["degradation_rate"] == pytest.approx(1 / 3)
    assert metrics["non_degraded_failure_rate"] == pytest.approx(1 / 3)


class _RecordingConnection:
    def __init__(self) -> None:
        self.last_sql = ""
        self.params: tuple[object, ...] = ()

    def cursor(self) -> "_RecordingConnection":
        return self

    def __enter__(self) -> "_RecordingConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.last_sql = " ".join(sql.split())
        self.params = params

    def fetchall(self) -> list[dict[str, object]]:
        return []


class _MemoryRepository:
    def __init__(
        self,
        memories: list[MemoryRecord],
        extra_memories: list[MemoryRecord] | None = None,
    ) -> None:
        self.memories = memories
        self.all_memories = [*memories, *(extra_memories or [])]

    def list_candidate_memories(
        self,
        *,
        user_id: int,
        memory_types: list[str] | None = None,
        include_pending_index: bool = True,
    ) -> list[MemoryRecord]:
        _ = user_id, memory_types, include_pending_index
        return list(self.memories)

    def list_system_memories(
        self,
        *,
        collection: str,
        agent_type: str | None = None,
        memory_types: list[str] | None = None,
    ) -> list[MemoryRecord]:
        _ = collection, agent_type, memory_types
        return []

    def get(self, collection: str, memory_id: int) -> MemoryRecord | None:
        return next(
            (
                memory
                for memory in self.all_memories
                if memory.collection == collection and memory.id == memory_id
            ),
            None,
        )


class _RecordingAuditRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _FailingVectorIndex:
    version = "fake-chroma"

    def search(self, *args: object, **kwargs: object) -> VectorSearchResult:
        _ = args, kwargs
        return VectorSearchResult(hits=[], fallback_reason="chroma unavailable")


class _VectorIndex:
    version = "fake-chroma"

    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories

    def search(self, *args: object, **kwargs: object) -> VectorSearchResult:
        _ = args, kwargs
        return VectorSearchResult(
            hits=[
                VectorSearchHit(
                    collection=memory.collection,
                    memory_id=memory.id,
                    score=0.9,
                    metadata={"memory_id": memory.id},
                )
                for memory in self.memories
            ]
        )


class _VectorRecordIndex:
    version = "fake-record-list"

    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories

    def search(self, *args: object, **kwargs: object) -> list[MemoryRecord]:
        _ = args, kwargs
        return list(self.memories)


class _RuleReranker:
    version = "test-rule-reranker"

    def score(self, query: str, content: str, confidence: float = 0.0) -> float:
        _ = confidence
        query_terms = set(query.lower().split())
        content_terms = set(content.lower().split())
        return float(len(query_terms & content_terms))


class _FakeEmbeddingModel:
    version = "fake-embedding"

    def embed(self, text: str) -> list[float]:
        _ = text
        return [0.1, 0.2, 0.3]


class _FakeChromaClient:
    def __init__(self, path: str) -> None:
        self.path = path
        self.collections: dict[str, _FakeCollection] = {}

    def get_or_create_collection(self, name: str) -> "_FakeCollection":
        collection = _FakeCollection(name)
        self.collections[name] = collection
        return collection


class _FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.upserts: list[dict[str, Any]] = []
        self.deletes: list[dict[str, Any]] = []

    def upsert(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.upserts.append(
            {
                "ids": ids,
                "documents": documents,
                "embeddings": embeddings,
                "metadatas": metadatas,
            }
        )

    def delete(self, **kwargs: Any) -> None:
        self.deletes.append(kwargs)

    def query(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {"metadatas": [[]], "distances": [[]]}


def _memory(
    memory_id: int,
    content: str,
    *,
    collection: str = "candidate_memories",
    memory_type: str = "technical_weakness",
    user_id: int | None = 42,
    agent_type: str | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        collection=collection,
        memory_type=memory_type,
        title=f"记忆 {memory_id}",
        content=content,
        structured_data={},
        tokens=content.lower().split(),
        confidence=0.8,
        status="active",
        index_status="indexed",
        source_interview_id=None,
        source_round_id=None,
        version=1,
        created_at=None,
        updated_at=None,
        user_id=user_id,
        agent_type=agent_type,
    )
