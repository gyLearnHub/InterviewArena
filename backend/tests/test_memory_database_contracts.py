from typing import Any

import pytest
from app.db import mysql
from app.repositories.memories import MemoryRepository
from scripts.migrate_v1 import INIT_SQL_TABLES_TO_CREATE


def test_memory_tables_define_user_round_uniqueness_and_foreign_keys() -> None:
    ddl = _ddl()

    assert "unique key uk_candidate_memory_summary" in ddl
    assert "user_id, memory_type, title, source_interview_id, source_round_id, version" in ddl
    assert "constraint fk_candidate_memories_user_id" in ddl
    assert "constraint fk_candidate_memories_source_interview_id" in ddl
    assert "constraint fk_candidate_memories_source_round_id" in ddl
    assert "key idx_rag_audit_logs_interview_round (interview_id, round_id)" in ddl
    assert "key idx_memory_tasks_user_type_status (user_id, task_type, status)" in ddl
    assert "dedupe_key varchar(128) null" in ddl
    assert "unique key uk_memory_tasks_dedupe_key (dedupe_key)" in ddl


def test_harness_tables_are_in_init_sql_and_migration_table_list() -> None:
    ddl = _ddl()
    required_tables = {
        "harness_traces",
        "harness_trace_events",
        "harness_checkpoints",
        "harness_replay_runs",
        "harness_rule_evaluations",
        "harness_improvement_candidates",
    }

    for table_name in required_tables:
        assert f"create table if not exists {table_name}" in ddl
        assert table_name in INIT_SQL_TABLES_TO_CREATE

    assert "constraint fk_harness_checkpoints_trace_id" in ddl
    assert "constraint fk_harness_rule_evaluations_trace_id" in ddl
    assert "key idx_harness_traces_interview_created" in ddl


def test_mysql_connection_commits_success_and_rolls_back_failure(monkeypatch) -> None:
    success_connection = _TransactionConnection()
    monkeypatch.setattr(mysql, "create_connection", lambda database_url=None: success_connection)

    with mysql.mysql_connection("mysql://u:p@127.0.0.1/db") as connection:
        assert connection is success_connection

    assert success_connection.committed is True
    assert success_connection.rolled_back is False
    assert success_connection.closed is True

    failure_connection = _TransactionConnection()
    monkeypatch.setattr(mysql, "create_connection", lambda database_url=None: failure_connection)

    with pytest.raises(RuntimeError):
        with mysql.mysql_connection("mysql://u:p@127.0.0.1/db"):
            raise RuntimeError("boom")

    assert failure_connection.committed is False
    assert failure_connection.rolled_back is True
    assert failure_connection.closed is True


def test_repository_update_existing_memory_versions_and_preserves_collection_scope() -> None:
    connection = _RecordingConnection()
    repository = MemoryRepository(connection)
    record = _row(memory_id=5)
    connection.fetchone_results.extend([record, record])

    updated = repository.update_existing_memory(
        record=repository.get("candidate_memories", 5),  # type: ignore[arg-type]
        content="new content",
        structured_data={"evidence": ["x"]},
        tokens=["new", "content"],
        confidence=0.8,
        confidence_detail={"status": "active"},
        status="active",
        index_status="indexed",
    )

    update_sql = connection.executed[1][0].lower()
    assert "update candidate_memories" in update_sql
    assert "version = version + 1" in update_sql
    assert "where id = %s" in update_sql
    assert connection.executed[1][1][-1] == 5
    assert updated.id == 5


def test_candidate_memory_queries_are_user_scoped() -> None:
    connection = _RecordingConnection()
    repository = MemoryRepository(connection)

    repository.list_candidate_memories(user_id=7, memory_types=["technical_weakness"])

    sql, params = connection.executed[-1]
    normalized = " ".join(sql.lower().split())
    assert "from candidate_memories" in normalized
    assert "user_id = %s" in normalized
    assert "memory_type in (%s)" in normalized
    assert params[0] == 7
    assert "technical_weakness" in params


class _TransactionConnection:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class _RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetchone_results: list[dict[str, Any]] = []
        self.lastrowid = 1
        self.rowcount = 1

    def cursor(self) -> "_RecordingConnection":
        return self

    def __enter__(self) -> "_RecordingConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.fetchone_results.pop(0) if self.fetchone_results else _row()

    def fetchall(self) -> list[dict[str, Any]]:
        return []


def _row(memory_id: int = 1) -> dict[str, Any]:
    return {
        "id": memory_id,
        "user_id": 7,
        "memory_type": "technical_weakness",
        "title": "Python weakness",
        "content": "Needs practice.",
        "structured_data": "{}",
        "tokens": '["python"]',
        "confidence": 0.8,
        "status": "active",
        "index_status": "indexed",
        "source_interview_id": 100,
        "source_round_id": 10,
        "version": 1,
        "created_at": None,
        "updated_at": None,
    }


def _ddl() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[2] / "database" / "init_mysql.sql"
    ).read_text(encoding="utf-8").lower()
