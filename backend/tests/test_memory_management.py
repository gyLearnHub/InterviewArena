from datetime import datetime

import pytest
from app.core.errors import AppError, ErrorCode
from app.repositories.memories import MemoryRecord
from app.repositories.users import UserRecord
from app.services.memory_management import MemoryManagementService


class FakeMemoryManagementRepository:
    def __init__(self, records: list[MemoryRecord]) -> None:
        self.records = records
        self.deleted: list[tuple[int, int]] = []
        self.list_calls: list[tuple[int, int, int]] = []

    def list_user_candidate_memories(
        self,
        *,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        self.list_calls.append((user_id, limit, offset))
        return [
            record
            for record in self.records
            if record.user_id == user_id and record.status != "deleted"
        ][offset : offset + limit]

    def count_user_candidate_memories_by_status(self, *, user_id: int) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            if record.user_id != user_id or record.status == "deleted":
                continue
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts

    def mark_candidate_memory_deleted(self, *, memory_id: int, user_id: int) -> bool:
        for index, record in enumerate(self.records):
            if record.id == memory_id and record.user_id == user_id and record.status != "deleted":
                self.records[index] = MemoryRecord(
                    **{
                        **record.__dict__,
                        "status": "deleted",
                        "index_status": "pending_delete",
                    }
                )
                self.deleted.append((memory_id, user_id))
                return True
        return False


class FakeMemoryIndexService:
    def __init__(self, delete_error: str | None = None) -> None:
        self.deleted_vectors: list[tuple[str, int]] = []
        self.delete_error = delete_error

    def delete_memory_vectors(self, collection: str, memory_id: int) -> str | None:
        self.deleted_vectors.append((collection, memory_id))
        return self.delete_error


def test_list_memories_returns_user_items_and_summary_counts() -> None:
    service = MemoryManagementService(
        FakeMemoryManagementRepository(
            [
                _memory(1, user_id=1, status="active"),
                _memory(2, user_id=1, status="pending_review"),
                _memory(3, user_id=2, status="active"),
            ]
        )
    )

    response = service.list_memories(_user(1))

    assert [item.id for item in response.items] == [1, 2]
    assert response.total == 2
    assert response.active_count == 1
    assert response.pending_review_count == 1
    assert response.items[0].target_position == "后端工程师"
    assert response.items[0].evidence == ["回答缺少量化结果"]


def test_list_memories_returns_global_counts_and_next_offset() -> None:
    repository = FakeMemoryManagementRepository(
        [
            _memory(1, user_id=1, status="active"),
            _memory(2, user_id=1, status="pending_review"),
            _memory(3, user_id=1, status="active"),
            _memory(4, user_id=1, status="archived"),
            _memory(5, user_id=2, status="active"),
        ]
    )
    service = MemoryManagementService(repository)

    response = service.list_memories(_user(1), limit=2, offset=2)

    assert [item.id for item in response.items] == [3, 4]
    assert response.total == 4
    assert response.active_count == 2
    assert response.pending_review_count == 1
    assert response.limit == 2
    assert response.offset == 2
    assert response.next_offset is None
    assert repository.list_calls == [(1, 2, 2)]


def test_delete_memory_marks_current_users_memory_and_deletes_vector() -> None:
    repository = FakeMemoryManagementRepository([_memory(1, user_id=1)])
    index_service = FakeMemoryIndexService()
    service = MemoryManagementService(repository, index_service)

    service.delete_memory(_user(1), 1)

    assert repository.deleted == [(1, 1)]
    assert index_service.deleted_vectors == [("candidate_memories", 1)]


def test_delete_memory_rejects_missing_or_other_users_memory() -> None:
    service = MemoryManagementService(FakeMemoryManagementRepository([_memory(1, user_id=2)]))

    with pytest.raises(AppError) as error_info:
        service.delete_memory(_user(1), 1)

    assert error_info.value.code == ErrorCode.NOT_FOUND
    assert error_info.value.status_code == 404


def test_delete_memory_reports_vector_delete_failure() -> None:
    repository = FakeMemoryManagementRepository([_memory(1, user_id=1)])
    service = MemoryManagementService(
        repository,
        FakeMemoryIndexService("chroma_delete_failed:RuntimeError"),
    )

    with pytest.raises(RuntimeError, match="chroma_delete_failed:RuntimeError"):
        service.delete_memory(_user(1), 1)

    assert repository.records[0].status == "deleted"
    assert repository.records[0].index_status == "pending_delete"


def test_delete_memory_accepts_disabled_chroma() -> None:
    repository = FakeMemoryManagementRepository([_memory(1, user_id=1)])
    service = MemoryManagementService(
        repository,
        FakeMemoryIndexService("chroma_disabled"),
    )

    service.delete_memory(_user(1), 1)

    assert repository.deleted == [(1, 1)]


def _user(user_id: int) -> UserRecord:
    return UserRecord(id=user_id, username=f"user-{user_id}", password_hash="hash")


def _memory(memory_id: int, *, user_id: int, status: str = "active") -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        collection="candidate_memories",
        memory_type="technical_weakness",
        title=f"记忆 {memory_id}",
        content="回答需要补充场景、行动和量化结果。",
        structured_data={
            "target_position": "后端工程师",
            "evidence": ["回答缺少量化结果"],
        },
        tokens=["回答", "量化"],
        confidence=0.82,
        status=status,
        index_status="indexed",
        source_interview_id=100,
        source_round_id=10,
        version=1,
        created_at=datetime(2026, 7, 8, 10, 0, 0),
        updated_at=datetime(2026, 7, 8, 11, 0, 0),
        user_id=user_id,
    )
