from typing import Any

from app.repositories.memories import MemoryRecord, MemoryRepository
from app.schemas.memory import MemoryItem
from app.services.local_models import tokenize
from app.services.memory_index import MemoryIndexService

ACTIVE_CONFIDENCE_THRESHOLD = 0.55


class MemoryLifecycleService:
    def __init__(
        self,
        repository: MemoryRepository,
        index_service: MemoryIndexService,
    ) -> None:
        self.repository = repository
        self.index_service = index_service

    def upsert_memory(
        self,
        *,
        item: MemoryItem,
        user_id: int | None,
        source_interview_id: int | None,
        target_position: str | None,
    ) -> MemoryRecord:
        status = "active" if item.confidence >= ACTIVE_CONFIDENCE_THRESHOLD else "pending_review"
        index_status = "pending_index" if status == "active" else "pending_index"
        confidence_detail = {
            "llm_confidence": item.confidence,
            "rule_threshold": ACTIVE_CONFIDENCE_THRESHOLD,
            "status": status,
        }
        structured_data = {
            **item.structured_data,
            "source": "memory_summary",
            "target_position": target_position,
        }
        tokens = tokenize(f"{item.title} {item.content}")
        existing = self.repository.find_similar(
            item=item.model_dump(),
            user_id=user_id,
            agent_type=item.agent_type,
        )
        if existing is not None:
            memory = self.repository.update_existing_memory(
                record=existing,
                content=item.content,
                structured_data=_merge_structured(existing.structured_data, structured_data),
                tokens=tokens,
                confidence=item.confidence,
                confidence_detail=confidence_detail,
                status=status,
                index_status=index_status,
            )
        else:
            memory = self.repository.insert_memory(
                collection=item.collection,
                user_id=user_id,
                agent_type=item.agent_type,
                position_key=item.position_key or target_position,
                scenario=item.scenario,
                memory_type=item.memory_type,
                title=item.title,
                content=item.content,
                structured_data=structured_data,
                tokens=tokens,
                confidence=item.confidence,
                confidence_detail=confidence_detail,
                status=status,
                index_status=index_status,
                source_interview_id=source_interview_id,
                source_round_id=item.source_round_id,
            )
        if memory.status == "active":
            self.index_service.index_memory(memory)
        else:
            self.index_service.delete_memory_vectors(memory.collection, memory.id)
        return memory

    def clear_user_candidate_memories(self, user_id: int) -> int:
        delete_error = self.index_service.delete_user_candidate_vectors(user_id)
        if delete_error not in {None, "chroma_disabled"}:
            raise RuntimeError(delete_error)
        return self.repository.delete_user_candidate_memories(user_id)

    def clear_user_memories(self, user_id: int) -> int:
        delete_error = self.index_service.delete_user_vectors(user_id)
        if delete_error not in {None, "chroma_disabled"}:
            raise RuntimeError(delete_error)
        return self.repository.delete_user_memories(user_id)


def _merge_structured(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    occurrences = int(old.get("occurrences") or 1) + 1
    evidence = []
    for value in [old.get("evidence"), new.get("evidence")]:
        if isinstance(value, list):
            evidence.extend(value)
    return {**old, **new, "occurrences": occurrences, "evidence": evidence[:20]}
