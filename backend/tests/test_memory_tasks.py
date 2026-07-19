import inspect
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import app.repositories.memory_tasks as memory_tasks_repository_module
import app.services.memory_tasks as memory_tasks_module
from app.repositories.memory_tasks import MemoryTaskRecord, MemoryTaskRepository
from app.services.memory_tasks import MemoryTaskRunner


def test_summary_task_creation_is_idempotent_by_interview() -> None:
    source = inspect.getsource(MemoryTaskRepository.create_summary_task).lower()

    assert "memory_summary" in source
    assert "interview_id" in source
    assert "on duplicate key update" in source
    assert "last_insert_id" in source


def test_clear_task_creation_is_atomic_by_active_dedupe_key() -> None:
    source = inspect.getsource(MemoryTaskRepository.create_or_get_clear_task).lower()

    assert "dedupe_key" in source
    assert "memory_clear:" in inspect.getsource(memory_tasks_repository_module._clear_dedupe_key)
    assert "on duplicate key update" in source
    assert "last_insert_id(id)" in source
    assert "latest_clear_task" not in source


def test_task_claim_retry_complete_lifecycle_is_supported() -> None:
    claim_source = inspect.getsource(MemoryTaskRepository.claim_due_task).lower()
    retry_source = inspect.getsource(MemoryTaskRepository.mark_failed_or_retry).lower()
    complete_source = inspect.getsource(MemoryTaskRepository.mark_completed).lower()

    assert "status = 'pending'" in claim_source
    assert "status = 'retry_wait'" in claim_source
    assert "status = 'processing'" in claim_source
    assert "retry_count = case" in claim_source
    assert "retry_count + 1" in claim_source
    assert "last_insert_id(id)" in claim_source
    assert "select last_insert_id()" in claim_source
    assert claim_source.index("update memory_tasks") < claim_source.index("select last_insert_id()")
    assert "utc_timestamp()" in claim_source
    assert "utc_timestamp()" in retry_source
    assert "utc_timestamp()" in complete_source
    assert "datetime.utcnow" not in retry_source
    assert "next_retry_at <= now()" not in claim_source
    assert "retry_wait" in retry_source
    assert "failed" in retry_source
    assert "completed" in complete_source
    for source in (retry_source, complete_source):
        assert "status = 'processing'" in source
        assert "processing_token" in source


def test_task_claim_recovers_timed_out_processing_tasks() -> None:
    claim_source = inspect.getsource(MemoryTaskRepository.claim_due_task).lower()

    assert "processing_timeout" in claim_source
    assert "retry_count < max_retries" in claim_source
    assert "retry_count >= max_retries" in claim_source
    assert "date_sub(utc_timestamp(), interval %s second)" in claim_source
    assert "coalesce(heartbeat_at, started_at) is null" in claim_source
    assert "max(1, processing_timeout_seconds)" in claim_source


def test_unexpired_processing_tasks_are_not_reclaimed_without_timeout() -> None:
    claim_source = inspect.getsource(MemoryTaskRepository.claim_due_task).lower()
    processing_clause_start = claim_source.index(
        "status = 'processing'",
        claim_source.index("or ("),
    )
    processing_clause = claim_source[processing_clause_start:]

    assert "retry_count < max_retries" in processing_clause
    assert "coalesce(heartbeat_at, started_at)" in processing_clause
    assert "<= date_sub(utc_timestamp(), interval %s second)" in processing_clause
    assert "order by created_at asc, id asc" in processing_clause


def test_memory_runner_commits_claim_before_handling_business_task() -> None:
    run_once_source = inspect.getsource(MemoryTaskRunner.run_once)
    claim_source = inspect.getsource(MemoryTaskRunner._claim_due_task)

    assert "_claim_due_task" in run_once_source
    assert "self._handle_task" in run_once_source
    assert run_once_source.index("self._claim_due_task()") < run_once_source.index(
        "self._handle_task",
    )
    assert "with mysql_connection() as connection" in claim_source
    assert "claim_due_task(" in claim_source
    assert "memory_task_processing_timeout_seconds" in claim_source


def test_mark_failed_or_retry_schedules_retry_before_limit() -> None:
    connection = _FakeConnection()
    repository = MemoryTaskRepository(connection)

    updated = repository.mark_failed_or_retry(
        _task(retry_count=0, max_retries=3),
        "temporary",
        "lease-token",
    )

    _sql, params = connection.cursor_obj.executions[-1]
    assert updated is True
    assert params == ("retry_wait", 1, 10, 10, "temporary", "retry_wait", 7, "lease-token")


def test_mark_failed_or_retry_fails_at_retry_limit() -> None:
    connection = _FakeConnection()
    repository = MemoryTaskRepository(connection)

    updated = repository.mark_failed_or_retry(
        _task(retry_count=2, max_retries=3),
        "still failing",
        "lease-token",
    )

    _sql, params = connection.cursor_obj.executions[-1]
    assert updated is True
    assert params == ("failed", 3, None, None, "still failing", "failed", 7, "lease-token")


def test_memory_clear_vector_failure_is_recorded_for_retry(monkeypatch) -> None:
    task = _task(retry_count=0, max_retries=3, task_type="memory_clear")
    retry_calls: list[tuple[MemoryTaskRecord, str]] = []
    runner = MemoryTaskRunner()
    monkeypatch.setattr(runner, "_claim_due_task", lambda: task)

    def fail_vector_delete(_connection: Any, _task_record: MemoryTaskRecord) -> dict[str, Any]:
        raise RuntimeError("chroma_delete_user_failed:PermissionError")

    monkeypatch.setattr(runner, "_handle_task", fail_vector_delete)

    @contextmanager
    def fake_mysql_connection() -> Any:
        yield object()

    class RecordingTaskRepository:
        def __init__(self, _connection: Any) -> None:
            pass

        def mark_failed_or_retry(
            self,
            failed_task: MemoryTaskRecord,
            error_message: str,
            processing_token: str,
        ) -> bool:
            assert processing_token == "lease-token"
            retry_calls.append((failed_task, error_message))
            return True

    monkeypatch.setattr(memory_tasks_module, "mysql_connection", fake_mysql_connection)
    monkeypatch.setattr(memory_tasks_module, "MemoryTaskRepository", RecordingTaskRepository)

    assert runner.run_once() is True
    assert retry_calls == [(task, "chroma_delete_user_failed:PermissionError")]


def _task(
    *,
    retry_count: int,
    max_retries: int,
    task_type: str = "memory_summary",
) -> MemoryTaskRecord:
    return MemoryTaskRecord(
        id=7,
        task_type=task_type,
        user_id=1,
        interview_id=22,
        memory_collection=None,
        memory_id=None,
        status="processing",
        retry_count=retry_count,
        max_retries=max_retries,
        next_retry_at=None,
        error_message=None,
        result=None,
        created_at=datetime(2026, 1, 1),
        started_at=None,
        completed_at=None,
        processing_token="lease-token",
        heartbeat_at=None,
    )


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    def cursor(self) -> "_FakeCursor":
        return self.cursor_obj


class _FakeCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...] | None]] = []
        self.rowcount = 1

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executions.append((sql, params))
