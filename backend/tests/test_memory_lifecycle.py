from pathlib import Path

from app.repositories.memories import MemoryRecord, MemoryRepository
from app.schemas.memory import MemoryIndexStatus, MemoryStatus
from app.services.memory_index import MemoryIndexService
from app.services.memory_lifecycle import MemoryLifecycleService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _ddl() -> str:
    return (PROJECT_ROOT / "database" / "init_mysql.sql").read_text(encoding="utf-8").lower()


def test_candidate_memory_tables_have_required_lifecycle_columns() -> None:
    ddl = _ddl()

    assert "create table if not exists candidate_memories" in ddl
    assert "memory_type" in ddl
    assert "structured_data" in ddl
    assert "confidence" in ddl
    assert "confidence_detail" in ddl
    assert "status" in ddl
    assert "index_status" in ddl
    assert "tokens" in ddl
    assert "source_interview_id" in ddl
    assert "source_round_id" in ddl
    assert "superseded_by_id" in ddl


def test_memory_status_schema_lists_lifecycle_states() -> None:
    assert set(MemoryStatus.__args__) == {
        "active",
        "pending_review",
        "superseded",
        "archived",
        "deleted",
    }
    assert set(MemoryIndexStatus.__args__) == {
        "pending_index",
        "indexed",
        "index_failed",
        "pending_delete",
    }


def test_memory_clear_schema_preserves_history_and_reports() -> None:
    ddl = _ddl()

    assert "create table if not exists feedback_reports" in ddl
    assert "create table if not exists interviews" in ddl
    assert "create table if not exists interview_qa" in ddl
    assert "candidate_memories" in ddl
    assert "on delete restrict" in ddl
    assert hasattr(MemoryRepository, "mark_user_candidate_pending_delete")
    assert hasattr(MemoryRepository, "delete_user_candidate_memories")


def test_memory_index_skips_pending_review_memories() -> None:
    repository = _IndexRepository()
    service = MemoryIndexService(repository)  # type: ignore[arg-type]

    service.index_memory(_memory(status="pending_review", index_status="pending_index"))

    assert repository.indexed == []


def test_clear_user_candidate_memories_triggers_vector_delete_path() -> None:
    repository = _LifecycleRepository()
    index_service = _RecordingIndexService()
    service = MemoryLifecycleService(
        repository,  # type: ignore[arg-type]
        index_service,  # type: ignore[arg-type]
    )

    deleted_count = service.clear_user_candidate_memories(42)

    assert deleted_count == 3
    assert repository.deleted_users == [42]
    assert index_service.vector_delete_users == [42]
    assert repository.pending_delete_users == []
    assert repository.commit_count == 0


def test_clear_user_candidate_memories_deletes_only_pre_marked_snapshot() -> None:
    repository = _LifecycleRepository(
        memories=[
            {"user_id": 42, "status": "deleted", "index_status": "pending_delete"},
            {"user_id": 42, "status": "deleted", "index_status": "pending_delete"},
            {"user_id": 42, "status": "active", "index_status": "pending_index"},
            {"user_id": 7, "status": "deleted", "index_status": "pending_delete"},
        ]
    )
    index_service = _RecordingIndexService()
    service = MemoryLifecycleService(
        repository,  # type: ignore[arg-type]
        index_service,  # type: ignore[arg-type]
    )

    deleted_count = service.clear_user_candidate_memories(42)

    assert deleted_count == 2
    assert repository.memories == [
        {"user_id": 42, "status": "active", "index_status": "pending_index"},
        {"user_id": 7, "status": "deleted", "index_status": "pending_delete"},
    ]
    assert repository.pending_delete_users == []


def test_clear_user_candidate_memories_keeps_pending_state_when_vector_delete_fails() -> None:
    repository = _LifecycleRepository()
    index_service = _RecordingIndexService("chroma_delete_user_failed:PermissionError")
    service = MemoryLifecycleService(
        repository,  # type: ignore[arg-type]
        index_service,  # type: ignore[arg-type]
    )

    try:
        service.clear_user_candidate_memories(42)
    except RuntimeError as exc:
        assert str(exc) == "chroma_delete_user_failed:PermissionError"
    else:
        raise AssertionError("vector deletion failure must be retryable")

    assert repository.pending_delete_users == []
    assert repository.commit_count == 0
    assert repository.deleted_users == []


class _IndexRepository:
    def __init__(self) -> None:
        self.indexed: list[tuple[str, int]] = []

    def mark_indexed(self, collection: str, memory_id: int) -> None:
        self.indexed.append((collection, memory_id))


class _LifecycleRepository:
    def __init__(self, memories: list[dict[str, object]] | None = None) -> None:
        self.pending_delete_users: list[int] = []
        self.deleted_users: list[int] = []
        self.memories = memories
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def mark_user_candidate_pending_delete(self, user_id: int) -> int:
        self.pending_delete_users.append(user_id)
        return 3

    def delete_user_candidate_memories(self, user_id: int) -> int:
        self.deleted_users.append(user_id)
        if self.memories is not None:
            before = len(self.memories)
            self.memories = [
                memory
                for memory in self.memories
                if not (
                    memory["user_id"] == user_id
                    and memory["status"] == "deleted"
                    and memory["index_status"] == "pending_delete"
                )
            ]
            return before - len(self.memories)
        return 3


class _RecordingIndexService:
    def __init__(self, delete_result: str | None = None) -> None:
        self.vector_delete_users: list[int] = []
        self.delete_result = delete_result

    def delete_user_candidate_vectors(self, user_id: int) -> str | None:
        self.vector_delete_users.append(user_id)
        return self.delete_result


def _memory(
    *,
    memory_id: int = 1,
    status: str = "active",
    index_status: str = "pending_index",
    content: str = "Python 并发薄弱",
    tokens: list[str] | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        collection="candidate_memories",
        memory_type="technical_weakness",
        title=f"记忆 {memory_id}",
        content=content,
        structured_data={},
        tokens=tokens or ["python", "并发", "薄弱"],
        confidence=0.8,
        status=status,
        index_status=index_status,
        source_interview_id=None,
        source_round_id=None,
        version=1,
        created_at=None,
        updated_at=None,
        user_id=42,
    )
