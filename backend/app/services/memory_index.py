from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.repositories.memories import MemoryRecord, MemoryRepository
from app.services.local_models import LocalEmbeddingModel

COLLECTIONS = ("candidate_memories", "interviewer_memories", "agent_memories")


@dataclass(frozen=True)
class VectorSearchHit:
    collection: str
    memory_id: int
    score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class VectorSearchResult:
    hits: list[VectorSearchHit]
    fallback_reason: str | None = None


class ChromaMemoryIndex:
    """Optional ChromaDB adapter.

    MySQL remains the authority. ChromaDB is used only when CHROMA_ENABLED is
    true and the chromadb package can be imported.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        embedding_model: LocalEmbeddingModel | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding_model: LocalEmbeddingModel | None = embedding_model
        self.client: Any | None = None
        self.collections: dict[str, Any] = {}
        self.fallback_reason: str | None = None
        if not self.settings.chroma_enabled:
            self.fallback_reason = "chroma_disabled"
            return
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=self.settings.chroma_persist_dir)
            self.collections = {
                name: self.client.get_or_create_collection(name=name) for name in COLLECTIONS
            }
        except Exception as exc:
            self.fallback_reason = f"chroma_unavailable:{exc.__class__.__name__}"
            self.client = None
            self.collections = {}

    @property
    def enabled(self) -> bool:
        return self.client is not None and not self.fallback_reason

    def upsert(self, memory: MemoryRecord) -> str | None:
        if not self.enabled:
            return self.fallback_reason
        if memory.status != "active":
            return "memory_not_active"
        try:
            embedding_model = self._embedding_model()
            collection = self.collections[memory.collection]
            self.delete_memory(memory.collection, memory.id)
            collection.upsert(
                ids=[_document_id(memory)],
                documents=[memory.content],
                embeddings=[embedding_model.embed(memory.content)],
                metadatas=[_metadata(memory)],
            )
            return None
        except Exception as exc:
            return f"chroma_upsert_failed:{exc.__class__.__name__}"

    def delete_memory(self, collection_name: str, memory_id: int) -> str | None:
        if not self.enabled:
            return self.fallback_reason
        try:
            self.collections[collection_name].delete(where={"memory_id": int(memory_id)})
            return None
        except Exception as exc:
            return f"chroma_delete_failed:{exc.__class__.__name__}"

    def delete_user_candidate_memories(self, user_id: int) -> str | None:
        if not self.enabled:
            return self.fallback_reason
        try:
            self.collections["candidate_memories"].delete(where={"user_id": int(user_id)})
            return None
        except Exception as exc:
            return f"chroma_delete_user_failed:{exc.__class__.__name__}"

    def search(
        self,
        *,
        query_text: str,
        collections: list[str],
        user_id: int | None,
        agent_type: str | None,
        memory_types: list[str],
        top_k: int,
    ) -> VectorSearchResult:
        if not self.enabled:
            return VectorSearchResult(hits=[], fallback_reason=self.fallback_reason)
        hits: list[VectorSearchHit] = []
        fallback_reasons: list[str] = []
        try:
            query_embedding = self._embedding_model().embed(query_text)
        except Exception as exc:
            return VectorSearchResult(
                hits=[],
                fallback_reason=f"embedding_model_unavailable:{exc.__class__.__name__}",
            )
        for collection_name in collections:
            if collection_name not in self.collections:
                continue
            where = _search_where(collection_name, user_id, agent_type)
            try:
                result = self.collections[collection_name].query(
                    query_embeddings=[query_embedding],
                    n_results=max(1, top_k),
                    where=where,
                    include=["metadatas", "distances"],
                )
                hits.extend(_hits_from_query_result(collection_name, result, memory_types))
            except Exception as exc:
                fallback_reasons.append(f"{collection_name}:{exc.__class__.__name__}")
        hits.sort(key=lambda item: item.score, reverse=True)
        reason = ";".join(fallback_reasons) if fallback_reasons else None
        return VectorSearchResult(hits=hits[:top_k], fallback_reason=reason)

    def _embedding_model(self) -> LocalEmbeddingModel:
        if self.embedding_model is None:
            self.embedding_model = LocalEmbeddingModel(self.settings)
        return self.embedding_model


class MemoryIndexService:
    def __init__(
        self,
        repository: MemoryRepository,
        vector_index: ChromaMemoryIndex | None = None,
    ) -> None:
        self.repository = repository
        self.vector_index = vector_index or ChromaMemoryIndex()

    def index_memory(self, memory: MemoryRecord) -> None:
        if memory.status != "active":
            return
        fallback_reason = self.vector_index.upsert(memory)
        if fallback_reason is None or fallback_reason in {"chroma_disabled"}:
            self.repository.mark_indexed(memory.collection, memory.id)
        else:
            self.repository.mark_index_failed(memory.collection, memory.id)

    def delete_user_candidate_vectors(self, user_id: int) -> str | None:
        return self.vector_index.delete_user_candidate_memories(user_id)

    def delete_memory_vectors(self, collection: str, memory_id: int) -> str | None:
        return self.vector_index.delete_memory(collection, memory_id)


def _document_id(memory: MemoryRecord) -> str:
    return f"{memory.collection}:{memory.id}:v{memory.version}"


def _metadata(memory: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": memory.id,
        "user_id": memory.user_id or 0,
        "memory_type": memory.memory_type,
        "agent_type": memory.agent_type or "",
        "status": memory.status,
        "confidence": float(memory.confidence),
        "source_interview_id": memory.source_interview_id or 0,
        "source_round_id": memory.source_round_id or 0,
        "created_at": memory.created_at.isoformat() if memory.created_at else "",
    }


def _search_where(
    collection_name: str,
    user_id: int | None,
    agent_type: str | None,
) -> dict[str, Any]:
    filters: list[dict[str, Any]] = [{"status": "active"}]
    if collection_name == "candidate_memories" and user_id is not None:
        filters.append({"user_id": int(user_id)})
    if collection_name in {"interviewer_memories", "agent_memories"} and agent_type:
        filters.append({"agent_type": agent_type})
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def _hits_from_query_result(
    collection_name: str,
    result: dict[str, Any],
    memory_types: list[str],
) -> list[VectorSearchHit]:
    metadatas = (result.get("metadatas") or [[]])[0] or []
    distances = (result.get("distances") or [[]])[0] or []
    allowed_types = set(memory_types)
    hits: list[VectorSearchHit] = []
    for index, metadata in enumerate(metadatas):
        if not isinstance(metadata, dict):
            continue
        if allowed_types and metadata.get("memory_type") not in allowed_types:
            continue
        memory_id = metadata.get("memory_id")
        if not isinstance(memory_id, int):
            continue
        distance = distances[index] if index < len(distances) else 1.0
        score = 1.0 / (1.0 + float(distance))
        hits.append(
            VectorSearchHit(
                collection=collection_name,
                memory_id=memory_id,
                score=score,
                metadata=metadata,
            )
        )
    return hits
