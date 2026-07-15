from typing import Protocol

from fastapi import status

from app.core.errors import AppError, ErrorCode
from app.repositories.memories import MemoryRecord
from app.repositories.users import UserRecord
from app.schemas.memory import ManagedMemoryItem, ManagedMemoryListResponse

DEFAULT_MEMORY_MANAGEMENT_LIMIT = 100
MAX_MEMORY_MANAGEMENT_LIMIT = 200


class MemoryManagementRepositoryProtocol(Protocol):
    def list_user_candidate_memories(
        self,
        *,
        user_id: int,
        limit: int = DEFAULT_MEMORY_MANAGEMENT_LIMIT,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        ...

    def count_user_candidate_memories_by_status(self, *, user_id: int) -> dict[str, int]:
        ...

    def mark_candidate_memory_deleted(self, *, memory_id: int, user_id: int) -> bool:
        ...


class MemoryIndexDeleteProtocol(Protocol):
    def delete_memory_vectors(self, collection: str, memory_id: int) -> str | None:
        ...


class MemoryManagementService:
    def __init__(
        self,
        repository: MemoryManagementRepositoryProtocol,
        index_service: MemoryIndexDeleteProtocol | None = None,
    ) -> None:
        self.repository = repository
        self.index_service = index_service

    def list_memories(
        self,
        current_user: UserRecord,
        *,
        limit: int = DEFAULT_MEMORY_MANAGEMENT_LIMIT,
        offset: int = 0,
    ) -> ManagedMemoryListResponse:
        page_size = max(1, min(limit, MAX_MEMORY_MANAGEMENT_LIMIT))
        page_offset = max(0, offset)
        records = self.repository.list_user_candidate_memories(
            user_id=current_user.id,
            limit=page_size,
            offset=page_offset,
        )
        counts = self.repository.count_user_candidate_memories_by_status(user_id=current_user.id)
        total = sum(counts.values())
        next_offset = page_offset + len(records)
        return ManagedMemoryListResponse(
            items=[_to_item(record) for record in records],
            total=total,
            active_count=counts.get("active", 0),
            pending_review_count=counts.get("pending_review", 0),
            limit=page_size,
            offset=page_offset,
            next_offset=next_offset if next_offset < total else None,
        )

    def delete_memory(self, current_user: UserRecord, memory_id: int) -> None:
        deleted = self.repository.mark_candidate_memory_deleted(
            memory_id=memory_id,
            user_id=current_user.id,
        )
        if not deleted:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if self.index_service is not None:
            delete_error = self.index_service.delete_memory_vectors(
                "candidate_memories",
                memory_id,
            )
            if delete_error not in {None, "chroma_disabled"}:
                raise RuntimeError(delete_error)


def _to_item(record: MemoryRecord) -> ManagedMemoryItem:
    return ManagedMemoryItem(
        id=record.id,
        memory_type=record.memory_type,
        title=record.title,
        content=record.content,
        confidence=record.confidence,
        status=record.status,  # type: ignore[arg-type]
        index_status=record.index_status,  # type: ignore[arg-type]
        source_interview_id=record.source_interview_id,
        source_round_id=record.source_round_id,
        target_position=_string_or_none(record.structured_data.get("target_position")),
        evidence=_string_list(record.structured_data.get("evidence")),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:5]
