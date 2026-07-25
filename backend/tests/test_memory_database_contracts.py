from typing import Any

import pytest
from app.db import mysql
from app.repositories.memories import MemoryRepository
from scripts.migrate_v1 import (
    ASYNC_TASK_SCHEMA_MIGRATION_VERSION,
    HARNESS_EVOLUTION_HARDENING_MIGRATION_VERSION,
    HARNESS_EVOLUTION_MIGRATION_VERSION,
    HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_VERSION,
    INIT_SQL_TABLES_TO_CREATE,
    INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_VERSION,
    INTERVIEW_TASK_LEASE_MIGRATION_VERSION,
    MEMORY_TASK_LEASE_MIGRATION_VERSION,
    MIGRATION_VERSION,
    RESUME_TASK_LEASE_MIGRATION_VERSION,
)


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


def test_system_memory_tables_are_user_scoped() -> None:
    ddl = _ddl()
    interviewer_ddl = ddl.split(
        "create table if not exists interviewer_memories",
        1,
    )[1].split(") engine=innodb", 1)[0]
    agent_ddl = ddl.split(
        "create table if not exists agent_memories",
        1,
    )[1].split(") engine=innodb", 1)[0]

    for table_ddl in (interviewer_ddl, agent_ddl):
        assert "user_id bigint unsigned not null" in table_ddl
        assert "foreign key (user_id) references users (id)" in table_ddl
    normalized_interviewer = " ".join(interviewer_ddl.split()).replace("( ", "(")
    normalized_agent = " ".join(agent_ddl.split()).replace("( ", "(")
    assert "uk_interviewer_memory_summary (user_id, agent_type" in normalized_interviewer
    assert "uk_agent_memory_summary (user_id, agent_type" in normalized_agent


def test_autonomous_evolution_verification_uses_resume_snapshot() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "verify_autonomous_evolution_flow.py"
    ).read_text(encoding="utf-8")

    assert "user_id, resume_id, resume_snapshot, target_position" in source


def test_harness_tables_are_in_init_sql_and_migration_table_list() -> None:
    ddl = _ddl()
    required_tables = {
        "harness_traces",
        "harness_trace_events",
        "harness_checkpoints",
        "harness_rule_evaluations",
        "harness_improvement_candidates",
    }

    for table_name in required_tables:
        assert f"create table if not exists {table_name}" in ddl
        assert table_name in INIT_SQL_TABLES_TO_CREATE

    assert "constraint fk_harness_checkpoints_trace_id" in ddl
    assert "constraint fk_harness_rule_evaluations_trace_id" in ddl
    assert "key idx_harness_traces_interview_created" in ddl


def test_autonomous_evolution_schema_is_versioned_and_auditable() -> None:
    ddl = _ddl()
    required_tables = {
        "harness_artifact_bundles",
        "harness_artifacts",
        "harness_evolution_runs",
        "harness_evolution_samples",
        "harness_evolution_events",
        "harness_evolution_observations",
    }

    for table_name in required_tables:
        assert f"create table if not exists {table_name}" in ddl
    assert "unique key uk_harness_evolution_runs_trigger" in ddl
    assert "unique key uk_harness_evolution_observations_interview" in ddl
    assert "job_family_key varchar(128) null" in ddl
    assert "harness_bundle_id bigint unsigned null" in ddl
    assert "heartbeat_at datetime null" in ddl
    assert "trigger_cursor_ended_at datetime null" in ddl
    assert "trigger_cursor_interview_id bigint unsigned null" in ddl
    assert "active_scope_key varchar(255)" in ddl
    bundle_ddl = ddl.split("create table if not exists harness_artifact_bundles", 1)[1].split(
        ") engine=innodb",
        1,
    )[0]
    assert ") virtual," in bundle_ddl
    assert (
        "unique key uk_harness_evolution_runs_trigger "
        "(user_id, job_family_key, trigger_sequence)"
    ) in ddl
    assert "unique key uk_harness_artifact_bundles_one_active" in ddl
    assert HARNESS_EVOLUTION_MIGRATION_VERSION == ("2026_07_13_harness_autonomous_evolution")
    assert HARNESS_EVOLUTION_HARDENING_MIGRATION_VERSION == (
        "2026_07_13_harness_evolution_hardening"
    )
    assert HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_VERSION == (
        "2026_07_14_harness_evolution_user_scope"
    )


def test_init_sql_uses_mysql_compatible_current_table_definitions() -> None:
    ddl = _ddl()

    assert "add column if not exists" not in ddl
    interviews_ddl = ddl.split("create table if not exists interviews", 1)[1].split(
        ") engine=innodb",
        1,
    )[0]
    rounds_ddl = ddl.split("create table if not exists interview_rounds", 1)[1].split(
        ") engine=innodb",
        1,
    )[0]
    reports_ddl = ddl.split("create table if not exists feedback_reports", 1)[1].split(
        ") engine=innodb",
        1,
    )[0]

    assert "harness_status varchar(32) not null default 'pending'" in interviews_ddl
    assert "last_checkpoint_id bigint unsigned null" in interviews_ddl
    assert "execution_status varchar(32) not null default 'pending'" in rounds_ddl
    assert "retry_count int not null default 0" in rounds_ddl
    assert (
        "report_reliability_status varchar(32) not null default 'normal'" in reports_ddl
    )


def test_answer_draft_table_is_in_init_sql_and_migration_table_list() -> None:
    ddl = _ddl()

    assert "create table if not exists interview_answer_drafts" in ddl
    assert "interview_answer_drafts" in INIT_SQL_TABLES_TO_CREATE
    assert "primary key (user_id, question_id)" in ddl
    assert "constraint fk_interview_answer_drafts_question_id" in ddl
    assert "foreign key (question_id) references interview_qa (id)" in ddl


def test_interview_operation_tasks_define_recoverable_processing_lease() -> None:
    ddl = _ddl()

    assert "processing_token char(32) null" in ddl
    assert "heartbeat_at datetime null" in ddl
    assert INTERVIEW_TASK_LEASE_MIGRATION_VERSION == "2026_07_10_interview_task_lease"


def test_resume_parse_tasks_define_recoverable_processing_lease() -> None:
    ddl = _ddl()
    table_ddl = ddl.split("create table if not exists resume_parse_tasks", 1)[1].split(
        ") engine=innodb",
        1,
    )[0]

    assert "processing_token char(32) null" in table_ddl
    assert "heartbeat_at datetime null" in table_ddl
    assert RESUME_TASK_LEASE_MIGRATION_VERSION == "2026_07_13_resume_task_lease"


def test_memory_tasks_define_recoverable_processing_lease() -> None:
    ddl = _ddl()
    table_ddl = ddl.split("create table if not exists memory_tasks", 1)[1].split(
        ") engine=innodb",
        1,
    )[0]

    assert "processing_token char(32) null" in table_ddl
    assert "heartbeat_at datetime null" in table_ddl
    assert MEMORY_TASK_LEASE_MIGRATION_VERSION == "2026_07_19_memory_task_lease"


def test_published_baseline_version_remains_stable() -> None:
    assert MIGRATION_VERSION == "2026_07_06_v1"
    assert ASYNC_TASK_SCHEMA_MIGRATION_VERSION == "2026_07_07_async_task_schema"


def test_interview_experience_and_reanswer_schema_contract() -> None:
    ddl = _ddl()

    assert "experience_mode varchar(32) not null default 'training'" in ddl
    assert "create table if not exists answer_reanswer_attempts" in ddl
    assert "unique key uk_answer_reanswer_question_attempt (question_id, attempt_number)" in ddl
    assert "evaluation json null" in ddl
    assert "answer_reanswer_attempts" in INIT_SQL_TABLES_TO_CREATE
    assert (
        INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_VERSION
        == "2026_07_20_interview_experience_reanswer"
    )


def test_old_baseline_skips_v1_and_runs_later_migrations(monkeypatch) -> None:
    from scripts import migrate_v1

    applied_versions = {MIGRATION_VERSION}
    calls: list[str] = []

    monkeypatch.setattr(migrate_v1, "_current_database", lambda _connection: "test_db")
    monkeypatch.setattr(migrate_v1, "_ensure_schema_migrations", lambda _connection: None)
    monkeypatch.setattr(
        migrate_v1,
        "_migration_applied",
        lambda _connection, version: version in applied_versions,
    )
    monkeypatch.setattr(
        migrate_v1,
        "_record_migration",
        lambda _connection, version, _description: applied_versions.add(version),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_v1_migration",
        lambda _connection, _database: calls.append("v1"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_async_task_schema_migration",
        lambda _connection, _database: calls.append("async_task_schema"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_interview_strategy_migration",
        lambda _connection, _database: calls.append("interview_strategy"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_round_strategy_migration",
        lambda _connection, _database: calls.append("round_strategy"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_create_tables_from_init_sql",
        lambda _connection, table_names: calls.extend(table_names),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_add_column",
        lambda *_args: calls.append("add_column"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_add_index",
        lambda *_args: calls.append("add_index"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_resume_delete_scrub",
        lambda _connection: calls.append("resume_delete_scrub"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_harness_evolution_hardening",
        lambda _connection, _database: calls.append("harness_evolution_hardening"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_harness_evolution_user_scope",
        lambda _connection, _database: calls.append("harness_evolution_user_scope"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_harness_replay_removal",
        lambda _connection, _database: calls.append("harness_replay_removal"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_review_bookmark_history_detach",
        lambda _connection, _database: calls.append("review_bookmark_history_detach"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_memory_user_scope",
        lambda _connection, _database: calls.append("memory_user_scope"),
    )
    monkeypatch.setattr(
        migrate_v1,
        "_apply_interview_resume_snapshot",
        lambda _connection, _database: calls.append("interview_resume_snapshot"),
    )

    migrate_v1.migrate(object())

    assert "v1" not in calls
    assert "async_task_schema" in calls
    assert "round_strategy" in calls
    assert "resume_delete_scrub" in calls
    assert "harness_evolution_user_scope" in calls
    assert "harness_evolution_hardening" in calls
    assert "harness_replay_removal" in calls
    assert "review_bookmark_history_detach" in calls
    assert ASYNC_TASK_SCHEMA_MIGRATION_VERSION in applied_versions
    assert MEMORY_TASK_LEASE_MIGRATION_VERSION in applied_versions


def test_schema_migration_uses_database_lock_and_commits_before_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import migrate_v1

    events: list[str] = []

    class LockConnection:
        def cursor(self) -> "LockConnection":
            return self

        def __enter__(self) -> "LockConnection":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, _params: tuple[Any, ...] = ()) -> None:
            if "GET_LOCK" in sql:
                events.append("lock")
            elif "RELEASE_LOCK" in sql:
                events.append("release")

        def fetchone(self) -> dict[str, int]:
            return {"acquired": 1}

        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(
        migrate_v1,
        "migrate",
        lambda _connection: events.append("migrate"),
    )

    migrate_v1.migrate_with_lock(LockConnection())

    assert events == ["lock", "migrate", "commit", "release"]


def test_resume_snapshot_migration_backfills_and_enforces_not_null() -> None:
    from scripts import migrate_v1

    connection = _RecordingConnection()
    connection.fetchone_results.append({"count": 0})

    migrate_v1._apply_interview_resume_snapshot(connection, "test_db")

    statements = [" ".join(sql.lower().split()) for sql, _params in connection.executed]
    assert any(
        statement.startswith("update interviews interview join resumes resume")
        for statement in statements
    )
    assert (
        "alter table interviews modify column resume_snapshot json not null"
        in statements
    )


def test_stored_generated_column_is_rebuilt_as_virtual() -> None:
    from scripts import migrate_v1

    connection = _RecordingConnection()
    connection.fetchone_results.extend(
        [
            {"EXTRA": "STORED GENERATED"},
            {"count": 0},
        ]
    )

    migrate_v1._ensure_virtual_generated_column(
        connection,
        "test_db",
        "harness_artifact_bundles",
        "active_scope_key",
        "VARCHAR(255) GENERATED ALWAYS AS ('scope') VIRTUAL",
    )

    statements = [" ".join(sql.lower().split()) for sql, _params in connection.executed]
    assert "alter table harness_artifact_bundles drop column active_scope_key" in statements
    assert any(
        statement.startswith(
            "alter table harness_artifact_bundles add column active_scope_key"
        )
        and statement.endswith("virtual")
        for statement in statements
    )


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
        (Path(__file__).resolve().parents[2] / "database" / "init_mysql.sql")
        .read_text(encoding="utf-8")
        .lower()
    )
