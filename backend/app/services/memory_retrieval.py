import time
import uuid
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import safe_error_code
from app.repositories.memories import MemoryRecord, MemoryRepository
from app.repositories.rag_audit import RagAuditRepository
from app.schemas.memory import (
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    RetrievedMemory,
)
from app.services.bm25_index import BM25Index
from app.services.local_models import LocalReranker
from app.services.memory_index import ChromaMemoryIndex, VectorSearchHit, VectorSearchResult
from app.services.memory_query_rewriter import PROMPT_VERSION, MemoryQueryRewriter
from app.services.memory_usage_policy import MemoryUsagePolicy


class VectorSearcherProtocol(Protocol):
    def search(
        self,
        *,
        query_text: str,
        collections: list[str],
        user_id: int | None,
        agent_type: str | None,
        memory_types: list[str],
        top_k: int,
    ) -> VectorSearchResult | list[MemoryRecord]:
        ...


class MemoryRetrievalService:
    def __init__(
        self,
        *,
        memory_repository: MemoryRepository,
        audit_repository: RagAuditRepository | None = None,
        vector_index: ChromaMemoryIndex | None = None,
        vector_searcher: VectorSearcherProtocol | None = None,
        rewriter: MemoryQueryRewriter | None = None,
        reranker: LocalReranker | None = None,
        usage_policy: MemoryUsagePolicy | None = None,
    ) -> None:
        self.memories = memory_repository
        self.audit = audit_repository
        self.vector_index: VectorSearcherProtocol = (
            vector_index or vector_searcher or ChromaMemoryIndex()
        )
        self.rewriter = rewriter or MemoryQueryRewriter()
        self.reranker = reranker
        self._reranker_unavailable_reason: str | None = None
        self.policy = usage_policy or MemoryUsagePolicy()
        self.min_relevance_score = get_settings().memory_min_relevance_score

    def retrieve(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        request_id = uuid.uuid4().hex
        started_at = time.perf_counter()
        fallback_reason: str | None = None
        candidate_ids: list[str] = []
        injected_ids: list[str] = []
        scores: dict[str, float] = {}
        rewritten_query = request.query_text
        timings: dict[str, int] = {
            "rewrite_ms": 0,
            "initial_recall_ms": 0,
            "reranker_ms": 0,
            "total_ms": 0,
            "candidate_count": 0,
            "injected_count": 0,
            "filtered_count": 0,
            "degradation_count": 0,
        }
        try:
            rewrite_started_at = time.perf_counter()
            query, rewrite_fallback = self.rewriter.rewrite(request)
            timings["rewrite_ms"] = int((time.perf_counter() - rewrite_started_at) * 1000)
            rewritten_query = query
            fallback_reason = rewrite_fallback
            memory_types = self.policy.allowed_memory_types(request)
            collections = self.policy.allowed_collections(request)
            top_k = self.policy.top_k(request)
            recall_started_at = time.perf_counter()
            (
                candidates,
                vector_scores,
                vector_fallback,
                scope_filtered_count,
            ) = self._load_candidates(request, collections, memory_types, query, top_k)
            timings["initial_recall_ms"] = int((time.perf_counter() - recall_started_at) * 1000)
            if vector_fallback:
                fallback_reason = _join_fallbacks(fallback_reason, vector_fallback)
            candidate_ids = [_memory_key(item) for item in candidates]
            timings["candidate_count"] = len(candidates)
            rank_started_at = time.perf_counter()
            ranked, reranker_fallback_count, reranker_fallback = self._rank(
                query,
                candidates,
                top_k,
                vector_scores,
            )
            timings["reranker_ms"] = int((time.perf_counter() - rank_started_at) * 1000)
            timings["filtered_count"] = scope_filtered_count + max(0, len(candidates) - len(ranked))
            if reranker_fallback_count:
                timings["degradation_count"] += reranker_fallback_count
                fallback_reason = _join_fallbacks(
                    fallback_reason,
                    reranker_fallback or "reranker_fallback",
                )
            memories = [
                RetrievedMemory(
                    collection=record.collection,  # type: ignore[arg-type]
                    memory_id=record.id,
                    memory_type=record.memory_type,
                    title=record.title,
                    content=record.content,
                    confidence=record.confidence,
                    score=score,
                    created_at=record.created_at,
                )
                for record, score in ranked
            ]
            injected_ids = [
                f"{item.collection}:{item.memory_id}" for item in memories
            ]
            timings["injected_count"] = len(injected_ids)
            scores = {_memory_key(record): score for record, score in ranked}
            return MemoryRetrievalResult(
                request_id=request_id,
                memories=memories,
                fallback_reason=fallback_reason,
            )
        except Exception as exc:
            fallback_reason = safe_error_code(exc)
            return MemoryRetrievalResult(
                request_id=request_id,
                memories=[],
                fallback_reason=fallback_reason,
            )
        finally:
            timings["total_ms"] = int((time.perf_counter() - started_at) * 1000)
            if fallback_reason and timings["degradation_count"] == 0:
                timings["degradation_count"] = 1
            self._audit(
                request=request,
                request_id=request_id,
                rewritten_query=rewritten_query,
                candidate_ids=candidate_ids,
                injected_ids=injected_ids,
                scores=scores,
                fallback_reason=fallback_reason,
                timings=timings,
            )

    def _load_candidates(
        self,
        request: MemoryRetrievalRequest,
        collections: list[str],
        memory_types: list[str],
        query_text: str,
        top_k: int,
    ) -> tuple[list[MemoryRecord], dict[str, float], str | None, int]:
        records_by_key: dict[str, MemoryRecord] = {}
        vector_scores: dict[str, float] = {}
        vector_fallback: str | None = None
        scope_filtered_count = 0
        if not collections:
            return [], vector_scores, vector_fallback, scope_filtered_count

        bm25_candidates: list[MemoryRecord] = []
        if "candidate_memories" in collections and request.user_id is not None:
            bm25_candidates.extend(
                self.memories.list_candidate_memories(
                    user_id=request.user_id,
                    memory_types=memory_types or None,
                )
            )
        for collection in ("interviewer_memories", "agent_memories"):
            if collection in collections and request.user_id is not None:
                bm25_candidates.extend(
                    self.memories.list_system_memories(
                        collection=collection,
                        user_id=request.user_id,
                        agent_type=request.agent_type,
                        position_key=request.position_key,
                        scenario=request.scenario,
                        memory_types=memory_types or None,
                    )
                )
        for record in bm25_candidates:
            records_by_key[_memory_key(record)] = record
        if not records_by_key:
            return [], vector_scores, vector_fallback, scope_filtered_count

        try:
            vector_result = self.vector_index.search(
                query_text=query_text,
                collections=collections,
                user_id=request.user_id,
                agent_type=request.agent_type,
                memory_types=memory_types,
                top_k=top_k * 3,
            )
            if isinstance(vector_result, list):
                for record in vector_result:
                    if not isinstance(record, MemoryRecord):
                        continue
                    if not _is_record_in_scope(
                        record,
                        request=request,
                        collections=collections,
                        memory_types=memory_types,
                        require_indexed=True,
                    ):
                        scope_filtered_count += 1
                        continue
                    key = _memory_key(record)
                    records_by_key[key] = record
                    vector_scores[key] = 1.0
            else:
                for hit in vector_result.hits:
                    loaded_record = self.memories.get(hit.collection, hit.memory_id)
                    if loaded_record is None:
                        continue
                    if not _is_record_in_scope(
                        loaded_record,
                        request=request,
                        collections=collections,
                        memory_types=memory_types,
                        require_indexed=True,
                    ):
                        scope_filtered_count += 1
                        continue
                    key = _memory_key(loaded_record)
                    records_by_key[key] = loaded_record
                    vector_scores[key] = hit.score
                vector_fallback = vector_result.fallback_reason
        except Exception as exc:
            vector_fallback = safe_error_code(exc)

        return list(records_by_key.values()), vector_scores, vector_fallback, scope_filtered_count

    def _rank(
        self,
        query: str,
        candidates: list[MemoryRecord],
        top_k: int,
        vector_scores: dict[str, float],
    ) -> tuple[list[tuple[MemoryRecord, float]], int, str | None]:
        bm25_scores = {
            _memory_key(memory): score
            for memory, score in BM25Index(candidates).search(query, top_k * 3)
        }
        ranked: list[tuple[MemoryRecord, float]] = []
        reranker_fallback_count = 0
        reranker: LocalReranker | None = None
        if candidates and self._reranker_unavailable_reason is None:
            try:
                reranker = self._reranker()
            except Exception as exc:
                self._reranker_unavailable_reason = _reranker_failure_reason(exc)
                reranker_fallback_count = 1
        elif candidates:
            reranker_fallback_count = 1
        for memory in candidates:
            key = _memory_key(memory)
            bm25 = bm25_scores.get(key, 0.0)
            vector = vector_scores.get(key, 0.0)
            if reranker is None:
                rerank = bm25 * 0.5 + vector * 0.4 + memory.confidence * 0.1
            else:
                try:
                    rerank = reranker.score(query, memory.content, memory.confidence)
                except Exception as exc:
                    self._reranker_unavailable_reason = _reranker_failure_reason(exc)
                    reranker = None
                    reranker_fallback_count = 1
                    rerank = bm25 * 0.5 + vector * 0.4 + memory.confidence * 0.1
            score = vector * 0.35 + bm25 * 0.35 + rerank * 0.2 + memory.confidence * 0.1
            if score >= self.min_relevance_score:
                ranked.append((memory, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return (
            ranked[:top_k],
            reranker_fallback_count,
            self._reranker_unavailable_reason,
        )

    def _reranker(self) -> LocalReranker:
        if self.reranker is None:
            self.reranker = LocalReranker()
        return self.reranker

    def _audit(
        self,
        *,
        request: MemoryRetrievalRequest,
        request_id: str,
        rewritten_query: str | None,
        candidate_ids: list[str],
        injected_ids: list[str],
        scores: dict[str, float],
        fallback_reason: str | None,
        timings: dict[str, int],
    ) -> None:
        if self.audit is None:
            return
        try:
            self.audit.create(
                request_id=request_id,
                user_id=request.user_id,
                interview_id=request.interview_id,
                round_id=request.round_id,
                agent_type=request.agent_type,
                usage_scene=request.usage_scene,
                original_intent=request.intent,
                rewritten_query=rewritten_query,
                candidate_memory_ids=candidate_ids,
                injected_memory_ids=injected_ids,
                scores=scores,
                timings=timings,
                fallback_reason=fallback_reason,
                embedding_version=getattr(
                    getattr(self.vector_index, "embedding_model", None),
                    "version",
                    getattr(self.vector_index, "version", None),
                ),
                reranker_version=getattr(self.reranker, "version", None),
                prompt_version=PROMPT_VERSION,
            )
        except Exception:
            return


def _memory_key(memory: MemoryRecord | VectorSearchHit) -> str:
    if isinstance(memory, MemoryRecord):
        return f"{memory.collection}:{memory.id}"
    return f"{memory.collection}:{memory.memory_id}"


def _is_record_in_scope(
    record: MemoryRecord,
    *,
    request: MemoryRetrievalRequest,
    collections: list[str],
    memory_types: list[str],
    require_indexed: bool,
) -> bool:
    if record.collection not in collections:
        return False
    if memory_types and record.memory_type not in memory_types:
        return False
    if record.status != "active":
        return False
    if require_indexed and record.index_status != "indexed":
        return False
    if record.collection == "candidate_memories":
        return request.user_id is not None and record.user_id == request.user_id
    if record.collection in {"interviewer_memories", "agent_memories"}:
        if request.user_id is None or record.user_id != request.user_id:
            return False
        if not record.agent_type:
            return False
        if request.agent_type is None or record.agent_type != request.agent_type:
            return False
        if (
            record.collection == "interviewer_memories"
            and request.position_key
            and record.position_key not in {"", request.position_key}
        ):
            return False
        if (
            record.collection == "agent_memories"
            and request.scenario
            and record.scenario not in {"", request.scenario}
        ):
            return False
        return True
    return False


def _join_fallbacks(*values: str | None) -> str | None:
    filtered = [value for value in values if value]
    return ";".join(filtered) if filtered else None


def _reranker_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if message == "reranker_model_path_missing":
        return message
    return "reranker_fallback"
