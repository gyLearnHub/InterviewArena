from contextlib import contextmanager
from typing import Any

import app.services.cache_cleanup_tasks as cleanup_service
import pytest
from app.repositories.cache_cleanup_tasks import (
    CacheCleanupTaskRecord,
    CacheCleanupTaskRepository,
)
from app.services.short_term_memory_store import ShortTermMemoryStoreError


def _task() -> CacheCleanupTaskRecord:
    return CacheCleanupTaskRecord(
        id=7,
        user_id=3,
        interview_ids=[11, 12],
        status="processing",
        attempt_count=1,
        max_retries=20,
        processing_token="lease-token",
    )


def test_cache_cleanup_failure_is_persisted_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, Any]] = []

    class FailingStore:
        def delete_many(self, user_id: int, interview_ids: list[int]) -> int:
            events.append(("delete", (user_id, interview_ids)))
            raise ShortTermMemoryStoreError("redis unavailable")

    class FakeRepository:
        def __init__(self, _connection: Any) -> None:
            pass

        def retry(self, task: CacheCleanupTaskRecord, message: str) -> bool:
            events.append(("retry", (task.id, message)))
            return True

    @contextmanager
    def fake_connection() -> Any:
        yield object()

    monkeypatch.setattr(cleanup_service, "get_short_term_memory_store", FailingStore)
    monkeypatch.setattr(cleanup_service, "CacheCleanupTaskRepository", FakeRepository)
    monkeypatch.setattr(cleanup_service, "mysql_connection", fake_connection)

    cleanup_service._process_task(_task())

    assert events == [
        ("delete", (3, [11, 12])),
        ("retry", (7, "redis unavailable")),
    ]


def test_cache_cleanup_success_requires_processing_token() -> None:
    complete_source = __import__("inspect").getsource(
        CacheCleanupTaskRepository.complete
    )
    retry_source = __import__("inspect").getsource(CacheCleanupTaskRepository.retry)

    for source in (complete_source, retry_source):
        assert "status = 'processing'" in source
        assert "processing_token" in source


def test_cache_cleanup_claim_recovers_stale_processing_tasks() -> None:
    source = __import__("inspect").getsource(CacheCleanupTaskRepository.claim_due)

    assert "status = 'retry_wait'" in source
    assert "status = 'processing'" in source
    assert "LAST_INSERT_ID" in source
