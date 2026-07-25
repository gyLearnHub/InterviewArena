import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

from app.db.mysql import mysql_connection

INIT_SQL_TABLES_TO_CREATE = [
    "usage_limits",
    "resume_parse_tasks",
    "interview_operation_tasks",
    "interview_answer_drafts",
    "answer_reanswer_attempts",
    "candidate_memories",
    "interviewer_memories",
    "agent_memories",
    "memory_tasks",
    "notifications",
    "rag_audit_logs",
    "harness_traces",
    "harness_trace_events",
    "harness_checkpoints",
    "harness_rule_evaluations",
    "harness_improvement_candidates",
    "skill_call_traces",
]
V1_TABLES_TO_CREATE = [
    "usage_limits",
    "resume_parse_tasks",
    "interview_operation_tasks",
    "candidate_memories",
    "interviewer_memories",
    "agent_memories",
    "memory_tasks",
    "notifications",
    "rag_audit_logs",
    "harness_traces",
    "harness_trace_events",
    "harness_checkpoints",
    "harness_rule_evaluations",
    "harness_improvement_candidates",
]
MIGRATION_VERSION = "2026_07_06_v1"
MIGRATION_DESCRIPTION = "InterviewArena v1 cumulative schema migration"
ASYNC_TASK_SCHEMA_MIGRATION_VERSION = "2026_07_07_async_task_schema"
ASYNC_TASK_SCHEMA_MIGRATION_DESCRIPTION = "Add async task payload and answer drafts"
USER_FEEDBACK_MIGRATION_VERSION = "2026_07_08_user_feedback"
USER_FEEDBACK_MIGRATION_DESCRIPTION = "Add user feedback submissions"
INTERVIEW_STRATEGY_MIGRATION_VERSION = "2026_07_08_interview_strategy"
INTERVIEW_STRATEGY_MIGRATION_DESCRIPTION = "Add interview strategy configuration"
ROUND_STRATEGY_MIGRATION_VERSION = "2026_07_14_round_strategy"
ROUND_STRATEGY_MIGRATION_DESCRIPTION = "Move difficulty and time limit to interview rounds"
WEAKNESS_PRACTICE_MIGRATION_VERSION = "2026_07_08_weakness_practice"
WEAKNESS_PRACTICE_MIGRATION_DESCRIPTION = "Add weakness practice progress tracking"
REVIEW_BOOKMARK_MIGRATION_VERSION = "2026_07_08_review_bookmarks"
REVIEW_BOOKMARK_MIGRATION_DESCRIPTION = "Add review bookmark practice list"
REVIEW_BOOKMARK_HISTORY_DETACH_MIGRATION_VERSION = "2026_07_15_review_bookmark_history_detach"
REVIEW_BOOKMARK_HISTORY_DETACH_MIGRATION_DESCRIPTION = (
    "Preserve review bookmarks after source interview deletion"
)
HARNESS_REPLAY_REMOVAL_MIGRATION_VERSION = "2026_07_15_remove_harness_replay"
HARNESS_REPLAY_REMOVAL_MIGRATION_DESCRIPTION = "Remove unused Harness replay storage"
SKILL_TRACE_MIGRATION_VERSION = "2026_07_09_skill_call_traces"
SKILL_TRACE_MIGRATION_DESCRIPTION = "Add deterministic skill call traces"
INTERVIEW_TASK_LEASE_MIGRATION_VERSION = "2026_07_10_interview_task_lease"
INTERVIEW_TASK_LEASE_MIGRATION_DESCRIPTION = "Add interview task leases and heartbeats"
RESUME_DELETE_SCRUB_MIGRATION_VERSION = "2026_07_12_resume_delete_scrub"
RESUME_DELETE_SCRUB_MIGRATION_DESCRIPTION = "Scrub deleted resume content and files"
RESUME_TASK_LEASE_MIGRATION_VERSION = "2026_07_13_resume_task_lease"
RESUME_TASK_LEASE_MIGRATION_DESCRIPTION = "Add resume parse task leases and heartbeats"
MEMORY_TASK_LEASE_MIGRATION_VERSION = "2026_07_19_memory_task_lease"
MEMORY_TASK_LEASE_MIGRATION_DESCRIPTION = "Add memory task leases and heartbeats"
HARNESS_EVOLUTION_MIGRATION_VERSION = "2026_07_13_harness_autonomous_evolution"
HARNESS_EVOLUTION_MIGRATION_DESCRIPTION = "Add autonomous Harness artifact evolution"
HARNESS_EVOLUTION_HARDENING_MIGRATION_VERSION = "2026_07_13_harness_evolution_hardening"
HARNESS_EVOLUTION_HARDENING_MIGRATION_DESCRIPTION = (
    "Harden autonomous Harness leases, cursors, and bundle integrity"
)
HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_VERSION = "2026_07_14_harness_evolution_user_scope"
HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_DESCRIPTION = (
    "Scope autonomous Harness evolution bundles and runs by user"
)
INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_VERSION = "2026_07_20_interview_experience_reanswer"
INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_DESCRIPTION = (
    "Add interview experience mode and answer reattempts"
)
MEMORY_USER_SCOPE_MIGRATION_VERSION = "2026_07_24_memory_user_scope"
MEMORY_USER_SCOPE_MIGRATION_DESCRIPTION = "Scope interviewer and agent memories by user"
INTERVIEW_RESUME_SNAPSHOT_MIGRATION_VERSION = "2026_07_24_interview_resume_snapshot"
INTERVIEW_RESUME_SNAPSHOT_MIGRATION_DESCRIPTION = (
    "Preserve immutable resume evidence for interview follow-up workflows"
)
AUTH_RATE_LIMIT_MIGRATION_VERSION = "2026_07_24_auth_rate_limit"
AUTH_RATE_LIMIT_MIGRATION_DESCRIPTION = "Add shared registration rate limiting"
FILE_CLEANUP_TASK_MIGRATION_VERSION = "2026_07_24_file_cleanup_tasks"
FILE_CLEANUP_TASK_MIGRATION_DESCRIPTION = "Add retryable uploaded file cleanup"
MIGRATION_LOCK_NAME = "interview_arena_schema_migrations"


def main() -> None:
    with mysql_connection() as connection:
        migrate_with_lock(connection)


def migrate_with_lock(connection: Any, timeout_seconds: int = 60) -> None:
    acquired = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT GET_LOCK(%s, %s) AS acquired",
                (MIGRATION_LOCK_NAME, max(0, timeout_seconds)),
            )
            row = cursor.fetchone() or {}
            acquired = int(row.get("acquired") or 0) == 1
        if not acquired:
            raise RuntimeError("schema_migration_lock_timeout")
        migrate(connection)
        connection.commit()
    finally:
        if acquired:
            with suppress(Exception):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT RELEASE_LOCK(%s) AS released",
                        (MIGRATION_LOCK_NAME,),
                    )


def migrate(connection: Any) -> None:
    database = _current_database(connection)
    _ensure_schema_migrations(connection)
    if not _migration_applied(connection, MIGRATION_VERSION):
        _apply_v1_migration(connection, database)

    if not _migration_applied(connection, ASYNC_TASK_SCHEMA_MIGRATION_VERSION):
        _apply_async_task_schema_migration(connection, database)
        _record_migration(
            connection,
            ASYNC_TASK_SCHEMA_MIGRATION_VERSION,
            ASYNC_TASK_SCHEMA_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, USER_FEEDBACK_MIGRATION_VERSION):
        _create_tables_from_init_sql(connection, ["user_feedback_submissions"])
        _record_migration(
            connection,
            USER_FEEDBACK_MIGRATION_VERSION,
            USER_FEEDBACK_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, INTERVIEW_STRATEGY_MIGRATION_VERSION):
        _apply_interview_strategy_migration(connection, database)
        _record_migration(
            connection,
            INTERVIEW_STRATEGY_MIGRATION_VERSION,
            INTERVIEW_STRATEGY_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, ROUND_STRATEGY_MIGRATION_VERSION):
        _apply_round_strategy_migration(connection, database)
        _record_migration(
            connection,
            ROUND_STRATEGY_MIGRATION_VERSION,
            ROUND_STRATEGY_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, WEAKNESS_PRACTICE_MIGRATION_VERSION):
        _create_tables_from_init_sql(connection, ["weakness_practice_progress"])
        _record_migration(
            connection,
            WEAKNESS_PRACTICE_MIGRATION_VERSION,
            WEAKNESS_PRACTICE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, REVIEW_BOOKMARK_MIGRATION_VERSION):
        _create_tables_from_init_sql(connection, ["review_bookmarks"])
        _record_migration(
            connection,
            REVIEW_BOOKMARK_MIGRATION_VERSION,
            REVIEW_BOOKMARK_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, REVIEW_BOOKMARK_HISTORY_DETACH_MIGRATION_VERSION):
        _apply_review_bookmark_history_detach(connection, database)
        _record_migration(
            connection,
            REVIEW_BOOKMARK_HISTORY_DETACH_MIGRATION_VERSION,
            REVIEW_BOOKMARK_HISTORY_DETACH_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, HARNESS_REPLAY_REMOVAL_MIGRATION_VERSION):
        _apply_harness_replay_removal(connection, database)
        _record_migration(
            connection,
            HARNESS_REPLAY_REMOVAL_MIGRATION_VERSION,
            HARNESS_REPLAY_REMOVAL_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, SKILL_TRACE_MIGRATION_VERSION):
        _create_tables_from_init_sql(connection, ["skill_call_traces"])
        _record_migration(
            connection,
            SKILL_TRACE_MIGRATION_VERSION,
            SKILL_TRACE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, INTERVIEW_TASK_LEASE_MIGRATION_VERSION):
        _add_column(
            connection,
            database,
            "interview_operation_tasks",
            "processing_token",
            "CHAR(32) NULL",
        )
        _add_column(
            connection,
            database,
            "interview_operation_tasks",
            "heartbeat_at",
            "DATETIME NULL",
        )
        _record_migration(
            connection,
            INTERVIEW_TASK_LEASE_MIGRATION_VERSION,
            INTERVIEW_TASK_LEASE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, RESUME_DELETE_SCRUB_MIGRATION_VERSION):
        _apply_resume_delete_scrub(connection)
        _record_migration(
            connection,
            RESUME_DELETE_SCRUB_MIGRATION_VERSION,
            RESUME_DELETE_SCRUB_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, RESUME_TASK_LEASE_MIGRATION_VERSION):
        _add_column(
            connection,
            database,
            "resume_parse_tasks",
            "processing_token",
            "CHAR(32) NULL",
        )
        _add_column(
            connection,
            database,
            "resume_parse_tasks",
            "heartbeat_at",
            "DATETIME NULL",
        )
        _record_migration(
            connection,
            RESUME_TASK_LEASE_MIGRATION_VERSION,
            RESUME_TASK_LEASE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, MEMORY_TASK_LEASE_MIGRATION_VERSION):
        _add_column(
            connection,
            database,
            "memory_tasks",
            "processing_token",
            "CHAR(32) NULL",
        )
        _add_column(
            connection,
            database,
            "memory_tasks",
            "heartbeat_at",
            "DATETIME NULL",
        )
        _record_migration(
            connection,
            MEMORY_TASK_LEASE_MIGRATION_VERSION,
            MEMORY_TASK_LEASE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, HARNESS_EVOLUTION_MIGRATION_VERSION):
        _create_tables_from_init_sql(
            connection,
            [
                "harness_artifact_bundles",
                "harness_artifacts",
                "harness_evolution_runs",
                "harness_evolution_samples",
                "harness_evolution_events",
                "harness_evolution_observations",
            ],
        )
        _add_column(
            connection,
            database,
            "interviews",
            "job_family_key",
            "VARCHAR(128) NULL",
        )
        _add_column(
            connection,
            database,
            "interviews",
            "harness_bundle_id",
            "BIGINT UNSIGNED NULL",
        )
        _add_index(
            connection,
            database,
            "interviews",
            "idx_interviews_job_family_finished",
            (
                "CREATE INDEX idx_interviews_job_family_finished "
                "ON interviews (job_family_key, overall_status, ended_at, id)"
            ),
        )
        _add_index(
            connection,
            database,
            "interviews",
            "idx_interviews_harness_bundle",
            "CREATE INDEX idx_interviews_harness_bundle ON interviews (harness_bundle_id)",
        )
        _record_migration(
            connection,
            HARNESS_EVOLUTION_MIGRATION_VERSION,
            HARNESS_EVOLUTION_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_VERSION):
        _apply_harness_evolution_user_scope(connection, database)
        _record_migration(
            connection,
            HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_VERSION,
            HARNESS_EVOLUTION_USER_SCOPE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, HARNESS_EVOLUTION_HARDENING_MIGRATION_VERSION):
        _apply_harness_evolution_hardening(connection, database)
        _record_migration(
            connection,
            HARNESS_EVOLUTION_HARDENING_MIGRATION_VERSION,
            HARNESS_EVOLUTION_HARDENING_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_VERSION):
        _add_column(
            connection,
            database,
            "interviews",
            "experience_mode",
            "VARCHAR(32) NOT NULL DEFAULT 'training'",
        )
        _create_tables_from_init_sql(connection, ["answer_reanswer_attempts"])
        _record_migration(
            connection,
            INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_VERSION,
            INTERVIEW_EXPERIENCE_REANSWER_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, MEMORY_USER_SCOPE_MIGRATION_VERSION):
        _apply_memory_user_scope(connection, database)
        _record_migration(
            connection,
            MEMORY_USER_SCOPE_MIGRATION_VERSION,
            MEMORY_USER_SCOPE_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, INTERVIEW_RESUME_SNAPSHOT_MIGRATION_VERSION):
        _apply_interview_resume_snapshot(connection, database)
        _record_migration(
            connection,
            INTERVIEW_RESUME_SNAPSHOT_MIGRATION_VERSION,
            INTERVIEW_RESUME_SNAPSHOT_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, AUTH_RATE_LIMIT_MIGRATION_VERSION):
        _create_tables_from_init_sql(connection, ["auth_rate_limits"])
        _record_migration(
            connection,
            AUTH_RATE_LIMIT_MIGRATION_VERSION,
            AUTH_RATE_LIMIT_MIGRATION_DESCRIPTION,
        )

    if not _migration_applied(connection, FILE_CLEANUP_TASK_MIGRATION_VERSION):
        _create_tables_from_init_sql(connection, ["file_cleanup_tasks"])
        _record_migration(
            connection,
            FILE_CLEANUP_TASK_MIGRATION_VERSION,
            FILE_CLEANUP_TASK_MIGRATION_DESCRIPTION,
        )


def _apply_interview_resume_snapshot(connection: Any, database: str) -> None:
    _add_column(
        connection,
        database,
        "interviews",
        "resume_snapshot",
        "JSON NULL AFTER resume_id",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interviews interview
            JOIN resumes resume ON resume.id = interview.resume_id
            SET interview.resume_snapshot = resume.structured_data
            WHERE interview.resume_snapshot IS NULL
            """
        )
        cursor.execute(
            """
            ALTER TABLE interviews
            MODIFY COLUMN resume_snapshot JSON NOT NULL
            """
        )


def _apply_memory_user_scope(connection: Any, database: str) -> None:
    for table_name in ("interviewer_memories", "agent_memories"):
        _add_column(
            connection,
            database,
            table_name,
            "user_id",
            "BIGINT UNSIGNED NULL AFTER id",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {table_name} memory
                JOIN interviews interview ON interview.id = memory.source_interview_id
                SET memory.user_id = interview.user_id
                WHERE memory.user_id IS NULL
                """
            )
            cursor.execute(
                f"""
                UPDATE {table_name} memory
                JOIN interview_rounds round_record ON round_record.id = memory.source_round_id
                JOIN interviews interview ON interview.id = round_record.interview_id
                SET memory.user_id = interview.user_id
                WHERE memory.user_id IS NULL
                """
            )

    _drop_index(
        connection,
        database,
        "interviewer_memories",
        "idx_interviewer_memories_agent_position_status",
    )
    _drop_index(
        connection,
        database,
        "interviewer_memories",
        "idx_interviewer_memories_type_status",
    )
    _drop_index(
        connection,
        database,
        "interviewer_memories",
        "uk_interviewer_memory_summary",
    )
    _add_index(
        connection,
        database,
        "interviewer_memories",
        "idx_interviewer_memories_user_agent_position_status",
        (
            "CREATE INDEX idx_interviewer_memories_user_agent_position_status "
            "ON interviewer_memories (user_id, agent_type, position_key, status)"
        ),
    )
    _add_index(
        connection,
        database,
        "interviewer_memories",
        "idx_interviewer_memories_user_type_status",
        (
            "CREATE INDEX idx_interviewer_memories_user_type_status "
            "ON interviewer_memories (user_id, memory_type, status)"
        ),
    )
    _add_index(
        connection,
        database,
        "interviewer_memories",
        "uk_interviewer_memory_summary",
        (
            "CREATE UNIQUE INDEX uk_interviewer_memory_summary ON interviewer_memories "
            "(user_id, agent_type, position_key, memory_type, title, "
            "source_interview_id, source_round_id, version)"
        ),
    )
    _add_foreign_key(
        connection,
        database,
        "interviewer_memories",
        "fk_interviewer_memories_user_id",
        (
            "ALTER TABLE interviewer_memories ADD CONSTRAINT "
            "fk_interviewer_memories_user_id FOREIGN KEY (user_id) "
            "REFERENCES users (id) ON DELETE RESTRICT ON UPDATE CASCADE"
        ),
    )

    _drop_index(
        connection,
        database,
        "agent_memories",
        "idx_agent_memories_agent_scenario_status",
    )
    _drop_index(
        connection,
        database,
        "agent_memories",
        "idx_agent_memories_type_status",
    )
    _drop_index(
        connection,
        database,
        "agent_memories",
        "uk_agent_memory_summary",
    )
    _add_index(
        connection,
        database,
        "agent_memories",
        "idx_agent_memories_user_agent_scenario_status",
        (
            "CREATE INDEX idx_agent_memories_user_agent_scenario_status "
            "ON agent_memories (user_id, agent_type, scenario, status)"
        ),
    )
    _add_index(
        connection,
        database,
        "agent_memories",
        "idx_agent_memories_user_type_status",
        (
            "CREATE INDEX idx_agent_memories_user_type_status "
            "ON agent_memories (user_id, memory_type, status)"
        ),
    )
    _add_index(
        connection,
        database,
        "agent_memories",
        "uk_agent_memory_summary",
        (
            "CREATE UNIQUE INDEX uk_agent_memory_summary ON agent_memories "
            "(user_id, agent_type, scenario, memory_type, title, "
            "source_interview_id, source_round_id, version)"
        ),
    )
    _add_foreign_key(
        connection,
        database,
        "agent_memories",
        "fk_agent_memories_user_id",
        (
            "ALTER TABLE agent_memories ADD CONSTRAINT "
            "fk_agent_memories_user_id FOREIGN KEY (user_id) "
            "REFERENCES users (id) ON DELETE RESTRICT ON UPDATE CASCADE"
        ),
    )


def _apply_harness_evolution_user_scope(connection: Any, database: str) -> None:
    _add_column(
        connection,
        database,
        "harness_artifact_bundles",
        "user_id",
        "BIGINT UNSIGNED NULL",
    )
    _add_column(
        connection,
        database,
        "harness_evolution_runs",
        "user_id",
        "BIGINT UNSIGNED NULL",
    )
    _backfill_harness_evolution_user_scope(connection)
    _normalize_active_harness_bundles_by_scope(connection)
    _drop_index(
        connection,
        database,
        "harness_artifact_bundles",
        "uk_harness_artifact_bundles_one_active",
    )
    _ensure_virtual_generated_column(
        connection,
        database,
        "harness_artifact_bundles",
        "active_scope_key",
        (
            "VARCHAR(255) GENERATED ALWAYS AS "
            "(CASE WHEN is_active = 1 THEN CONCAT(COALESCE(user_id, 0), ':', job_family_key) "
            "ELSE NULL END) VIRTUAL"
        ),
    )
    _add_index(
        connection,
        database,
        "harness_artifact_bundles",
        "uk_harness_artifact_bundles_one_active",
        (
            "CREATE UNIQUE INDEX uk_harness_artifact_bundles_one_active "
            "ON harness_artifact_bundles (active_scope_key)"
        ),
    )
    _drop_index(
        connection,
        database,
        "harness_artifact_bundles",
        "idx_harness_artifact_bundles_active",
    )
    _add_index(
        connection,
        database,
        "harness_artifact_bundles",
        "idx_harness_artifact_bundles_active",
        (
            "CREATE INDEX idx_harness_artifact_bundles_active "
            "ON harness_artifact_bundles (user_id, job_family_key, is_active, activated_at)"
        ),
    )
    _drop_index(
        connection,
        database,
        "harness_evolution_runs",
        "uk_harness_evolution_runs_trigger",
    )
    _add_index(
        connection,
        database,
        "harness_evolution_runs",
        "uk_harness_evolution_runs_trigger",
        (
            "CREATE UNIQUE INDEX uk_harness_evolution_runs_trigger "
            "ON harness_evolution_runs (user_id, job_family_key, trigger_sequence)"
        ),
    )
    _add_index(
        connection,
        database,
        "harness_evolution_runs",
        "idx_harness_evolution_runs_user_family",
        (
            "CREATE INDEX idx_harness_evolution_runs_user_family "
            "ON harness_evolution_runs (user_id, job_family_key, created_at)"
        ),
    )
    _add_foreign_key(
        connection,
        database,
        "harness_artifact_bundles",
        "fk_harness_artifact_bundles_user_id",
        (
            "ALTER TABLE harness_artifact_bundles ADD CONSTRAINT "
            "fk_harness_artifact_bundles_user_id FOREIGN KEY (user_id) "
            "REFERENCES users (id) ON DELETE SET NULL ON UPDATE CASCADE"
        ),
    )
    _add_foreign_key(
        connection,
        database,
        "harness_evolution_runs",
        "fk_harness_evolution_runs_user_id",
        (
            "ALTER TABLE harness_evolution_runs ADD CONSTRAINT "
            "fk_harness_evolution_runs_user_id FOREIGN KEY (user_id) "
            "REFERENCES users (id) ON DELETE SET NULL ON UPDATE CASCADE"
        ),
    )


def _backfill_harness_evolution_user_scope(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE harness_artifact_bundles b
            JOIN (
                SELECT harness_bundle_id AS bundle_id, MIN(user_id) AS user_id
                FROM interviews
                WHERE harness_bundle_id IS NOT NULL
                GROUP BY harness_bundle_id
            ) owner ON owner.bundle_id = b.id
            SET b.user_id = owner.user_id
            WHERE b.user_id IS NULL
            """
        )
        while True:
            cursor.execute(
                """
                UPDATE harness_artifact_bundles child
                JOIN harness_artifact_bundles parent ON parent.id = child.parent_bundle_id
                SET child.user_id = parent.user_id
                WHERE child.user_id IS NULL AND parent.user_id IS NOT NULL
                """
            )
            if int(getattr(cursor, "rowcount", 0) or 0) == 0:
                break
        cursor.execute(
            """
            UPDATE harness_evolution_runs r
            JOIN harness_artifact_bundles b ON b.id = r.baseline_bundle_id
            SET r.user_id = b.user_id
            WHERE r.user_id IS NULL AND b.user_id IS NOT NULL
            """
        )
        cursor.execute(
            """
            SELECT id, source_interview_ids
            FROM harness_evolution_runs
            WHERE user_id IS NULL
            ORDER BY id
            """
        )
        run_rows = list(cursor.fetchall())
        for row in run_rows:
            source_ids = row.get("source_interview_ids")
            if isinstance(source_ids, str):
                try:
                    source_ids = json.loads(source_ids)
                except json.JSONDecodeError:
                    source_ids = []
            source_ids = [int(item) for item in source_ids or [] if str(item).isdigit()]
            if not source_ids:
                continue
            placeholders = ", ".join(["%s"] * len(source_ids))
            cursor.execute(
                f"""
                SELECT user_id
                FROM interviews
                WHERE id IN ({placeholders})
                GROUP BY user_id
                ORDER BY COUNT(*) DESC, user_id
                LIMIT 1
                """,
                tuple(source_ids),
            )
            owner = cursor.fetchone()
            if owner is None or owner.get("user_id") is None:
                continue
            cursor.execute(
                "UPDATE harness_evolution_runs SET user_id = %s WHERE id = %s",
                (owner["user_id"], row["id"]),
            )


def _normalize_active_harness_bundles_by_scope(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, user_id, job_family_key
            FROM harness_artifact_bundles
            WHERE is_active = 1
            ORDER BY COALESCE(user_id, 0), job_family_key, activated_at DESC, id DESC
            """
        )
        seen: set[tuple[int, str]] = set()
        duplicate_ids: list[int] = []
        for row in cursor.fetchall():
            key = (int(row.get("user_id") or 0), str(row["job_family_key"]))
            if key in seen:
                duplicate_ids.append(int(row["id"]))
            else:
                seen.add(key)
        for bundle_id in duplicate_ids:
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 0, status = 'superseded',
                    activation_reason = 'deduplicated by user-scope migration'
                WHERE id = %s
                """,
                (bundle_id,),
            )


def _apply_harness_evolution_hardening(connection: Any, database: str) -> None:
    _add_column(
        connection,
        database,
        "harness_evolution_runs",
        "heartbeat_at",
        "DATETIME NULL",
    )
    _add_column(
        connection,
        database,
        "harness_evolution_runs",
        "trigger_cursor_ended_at",
        "DATETIME NULL",
    )
    _add_column(
        connection,
        database,
        "harness_evolution_runs",
        "trigger_cursor_interview_id",
        "BIGINT UNSIGNED NULL",
    )
    _backfill_harness_evolution_cursors(connection)
    _normalize_active_harness_bundles(connection)
    _add_column(
        connection,
        database,
        "harness_artifact_bundles",
        "active_job_family_key",
        (
            "VARCHAR(128) GENERATED ALWAYS AS "
            "(CASE WHEN is_active = 1 THEN job_family_key ELSE NULL END) STORED"
        ),
    )
    _add_index(
        connection,
        database,
        "harness_artifact_bundles",
        "uk_harness_artifact_bundles_one_active",
        (
            "CREATE UNIQUE INDEX uk_harness_artifact_bundles_one_active "
            "ON harness_artifact_bundles (active_job_family_key)"
        ),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interviews i
            LEFT JOIN harness_artifact_bundles b ON b.id = i.harness_bundle_id
            SET i.harness_bundle_id = NULL
            WHERE i.harness_bundle_id IS NOT NULL AND b.id IS NULL
            """
        )
    _add_foreign_key(
        connection,
        database,
        "interviews",
        "fk_interviews_harness_bundle_id",
        (
            "ALTER TABLE interviews ADD CONSTRAINT fk_interviews_harness_bundle_id "
            "FOREIGN KEY (harness_bundle_id) REFERENCES harness_artifact_bundles (id) "
            "ON DELETE SET NULL ON UPDATE CASCADE"
        ),
    )


def _backfill_harness_evolution_cursors(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE harness_evolution_runs
            SET heartbeat_at = started_at
            WHERE heartbeat_at IS NULL AND started_at IS NOT NULL
            """
        )
        cursor.execute(
            """
            SELECT id, source_interview_ids, created_at
            FROM harness_evolution_runs
            WHERE trigger_cursor_ended_at IS NULL
               OR trigger_cursor_interview_id IS NULL
            ORDER BY id
            """
        )
        run_rows = list(cursor.fetchall())
        for row in run_rows:
            source_ids = row.get("source_interview_ids")
            if isinstance(source_ids, str):
                try:
                    source_ids = json.loads(source_ids)
                except json.JSONDecodeError:
                    source_ids = []
            last_id = int(source_ids[-1]) if source_ids else 0
            cursor_at = row.get("created_at")
            if last_id:
                cursor.execute(
                    """
                    SELECT COALESCE(ended_at, created_at) AS cursor_at
                    FROM interviews WHERE id = %s
                    """,
                    (last_id,),
                )
                interview = cursor.fetchone()
                if interview is not None:
                    cursor_at = interview["cursor_at"]
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET trigger_cursor_ended_at = %s, trigger_cursor_interview_id = %s
                WHERE id = %s
                """,
                (cursor_at, last_id, row["id"]),
            )


def _normalize_active_harness_bundles(connection: Any) -> None:
    _normalize_active_harness_bundles_by_scope(connection)


def _apply_v1_migration(connection: Any, database: str) -> None:
    _add_column(connection, database, "users", "display_name", "VARCHAR(64) NULL")
    _add_column(connection, database, "users", "avatar_url", "VARCHAR(512) NULL")
    _add_column(
        connection,
        database,
        "users",
        "memory_enabled",
        "TINYINT(1) NOT NULL DEFAULT 1",
    )
    _add_column(connection, database, "users", "memory_updated_at", "DATETIME NULL")

    _add_column(connection, database, "resumes", "content_hash", "CHAR(64) NULL")
    _add_column(connection, database, "resumes", "display_name", "VARCHAR(128) NULL")
    _add_column(
        connection,
        database,
        "resumes",
        "is_default",
        "TINYINT(1) NOT NULL DEFAULT 0",
    )
    _add_column(connection, database, "resumes", "deleted_at", "DATETIME NULL")
    _add_column(connection, database, "resumes", "default_key", "VARCHAR(16) NULL")
    _add_index(
        connection,
        database,
        "resumes",
        "uk_resumes_user_content_hash",
        "CREATE UNIQUE INDEX uk_resumes_user_content_hash ON resumes (user_id, content_hash)",
    )
    _add_index(
        connection,
        database,
        "resumes",
        "idx_resumes_user_deleted_default",
        (
            "CREATE INDEX idx_resumes_user_deleted_default "
            "ON resumes (user_id, deleted_at, is_default)"
        ),
    )
    _migrate_resume_default_key(connection, database)

    _add_column(
        connection,
        database,
        "interviews",
        "mode",
        "VARCHAR(32) NOT NULL DEFAULT 'multi_round'",
    )
    _add_column(connection, database, "interviews", "job_description", "TEXT NULL")
    _add_column(connection, database, "interviews", "selected_rounds", "JSON NULL")
    _add_column(connection, database, "interviews", "current_round", "VARCHAR(32) NULL")
    _add_column(
        connection,
        database,
        "interviews",
        "overall_status",
        "VARCHAR(32) NOT NULL DEFAULT 'created'",
    )
    _add_column(connection, database, "interviews", "last_active_at", "DATETIME NULL")
    _add_column(
        connection,
        database,
        "interviews",
        "elapsed_seconds",
        "INT NOT NULL DEFAULT 0",
    )
    _add_column(
        connection,
        database,
        "interviews",
        "harness_status",
        "VARCHAR(32) NOT NULL DEFAULT 'pending'",
    )
    _add_column(
        connection,
        database,
        "interviews",
        "last_checkpoint_id",
        "BIGINT UNSIGNED NULL",
    )
    _add_column(
        connection,
        database,
        "interviews",
        "recovery_count",
        "INT NOT NULL DEFAULT 0",
    )
    _add_column(connection, database, "interviews", "last_recovered_at", "DATETIME NULL")
    _add_column(
        connection,
        database,
        "interviews",
        "last_harness_error",
        "VARCHAR(1000) NULL",
    )
    _add_column(
        connection,
        database,
        "interviews",
        "had_degradation",
        "TINYINT(1) NOT NULL DEFAULT 0",
    )
    _add_index(
        connection,
        database,
        "interviews",
        "idx_interviews_mode_overall_status",
        "CREATE INDEX idx_interviews_mode_overall_status ON interviews (mode, overall_status)",
    )

    _create_interview_rounds(connection)
    _add_column(
        connection,
        database,
        "interview_rounds",
        "execution_status",
        "VARCHAR(32) NOT NULL DEFAULT 'pending'",
    )
    _add_column(
        connection,
        database,
        "interview_rounds",
        "retry_count",
        "INT NOT NULL DEFAULT 0",
    )
    _add_column(connection, database, "interview_qa", "round_id", "BIGINT UNSIGNED NULL")
    _add_column(
        connection,
        database,
        "interview_qa",
        "question_kind",
        "VARCHAR(32) NOT NULL DEFAULT 'main'",
    )
    _add_column(
        connection,
        database,
        "interview_qa",
        "parent_question_id",
        "BIGINT UNSIGNED NULL",
    )
    _add_column(
        connection,
        database,
        "interview_qa",
        "question_status",
        "VARCHAR(32) NOT NULL DEFAULT 'active'",
    )
    _add_column(
        connection,
        database,
        "interview_qa",
        "regenerated_from_question_id",
        "BIGINT UNSIGNED NULL",
    )
    _drop_index(connection, database, "interview_qa", "uk_interview_qa_interview_sequence")
    _add_index(
        connection,
        database,
        "interview_qa",
        "uk_interview_qa_round_sequence",
        "CREATE UNIQUE INDEX uk_interview_qa_round_sequence ON interview_qa (round_id, sequence)",
    )
    _add_index(
        connection,
        database,
        "interview_qa",
        "idx_interview_qa_round_sequence",
        "CREATE INDEX idx_interview_qa_round_sequence ON interview_qa (round_id, sequence)",
    )
    _add_index(
        connection,
        database,
        "interview_qa",
        "idx_interview_qa_round_status",
        "CREATE INDEX idx_interview_qa_round_status ON interview_qa (round_id, question_status)",
    )
    _add_index(
        connection,
        database,
        "interview_qa",
        "idx_interview_qa_parent_question_id",
        "CREATE INDEX idx_interview_qa_parent_question_id ON interview_qa (parent_question_id)",
    )
    _add_index(
        connection,
        database,
        "interview_qa",
        "idx_interview_qa_regenerated_from",
        (
            "CREATE INDEX idx_interview_qa_regenerated_from "
            "ON interview_qa (regenerated_from_question_id)"
        ),
    )
    _add_foreign_key(
        connection,
        database,
        "interview_qa",
        "fk_interview_qa_round_id",
        """
        ALTER TABLE interview_qa
        ADD CONSTRAINT fk_interview_qa_round_id
        FOREIGN KEY (round_id) REFERENCES interview_rounds (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
        """,
    )
    _add_foreign_key(
        connection,
        database,
        "interview_qa",
        "fk_interview_qa_parent_question_id",
        """
        ALTER TABLE interview_qa
        ADD CONSTRAINT fk_interview_qa_parent_question_id
        FOREIGN KEY (parent_question_id) REFERENCES interview_qa (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
        """,
    )
    _add_foreign_key(
        connection,
        database,
        "interview_qa",
        "fk_interview_qa_regenerated_from_question_id",
        """
        ALTER TABLE interview_qa
        ADD CONSTRAINT fk_interview_qa_regenerated_from_question_id
        FOREIGN KEY (regenerated_from_question_id) REFERENCES interview_qa (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
        """,
    )

    _add_column(connection, database, "feedback_reports", "recommendation", "VARCHAR(32) NULL")
    _add_column(connection, database, "feedback_reports", "round_scores", "JSON NULL")
    _add_column(connection, database, "feedback_reports", "strengths", "JSON NULL")
    _add_column(connection, database, "feedback_reports", "ability_analysis", "JSON NULL")
    _add_column(connection, database, "feedback_reports", "job_match", "TEXT NULL")
    _add_column(connection, database, "feedback_reports", "final_conclusion", "TEXT NULL")
    _add_column(connection, database, "feedback_reports", "confidence", "VARCHAR(16) NULL")
    _add_column(connection, database, "feedback_reports", "reference_note", "VARCHAR(255) NULL")
    _add_column(
        connection,
        database,
        "feedback_reports",
        "used_candidate_memory",
        "TINYINT(1) NOT NULL DEFAULT 0",
    )
    _add_column(
        connection,
        database,
        "feedback_reports",
        "report_reliability_status",
        "VARCHAR(32) NOT NULL DEFAULT 'normal'",
    )
    _create_evaluation_records(connection)
    _create_tables_from_init_sql(connection, V1_TABLES_TO_CREATE)
    _migrate_memory_task_dedupe_key(connection, database)
    _record_migration(connection, MIGRATION_VERSION, MIGRATION_DESCRIPTION)


def _apply_async_task_schema_migration(connection: Any, database: str) -> None:
    _create_tables_from_init_sql(connection, ["interview_answer_drafts"])
    _add_column(connection, database, "interview_operation_tasks", "payload_json", "JSON NULL")
    _add_index(
        connection,
        database,
        "interview_operation_tasks",
        "idx_interview_operation_tasks_status_created",
        (
            "CREATE INDEX idx_interview_operation_tasks_status_created "
            "ON interview_operation_tasks (status, created_at, id)"
        ),
    )


def _apply_interview_strategy_migration(connection: Any, database: str) -> None:
    _add_column(
        connection,
        database,
        "interviews",
        "interview_goal",
        "VARCHAR(32) NOT NULL DEFAULT 'campus'",
    )
    _add_column(
        connection,
        database,
        "interviews",
        "difficulty",
        "VARCHAR(32) NOT NULL DEFAULT 'normal'",
    )
    _add_column(
        connection,
        database,
        "interviews",
        "time_limit_minutes",
        "INT NOT NULL DEFAULT 45",
    )


def _apply_round_strategy_migration(connection: Any, database: str) -> None:
    _add_column(
        connection,
        database,
        "interview_rounds",
        "difficulty",
        "VARCHAR(32) NOT NULL DEFAULT 'normal'",
    )
    _add_column(
        connection,
        database,
        "interview_rounds",
        "time_limit_minutes",
        "INT NOT NULL DEFAULT 45",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE interview_rounds r
            JOIN interviews i ON i.id = r.interview_id
            SET r.difficulty = COALESCE(i.difficulty, 'normal'),
                r.time_limit_minutes = COALESCE(i.time_limit_minutes, 45)
            """
        )


def _apply_review_bookmark_history_detach(connection: Any, database: str) -> None:
    _add_column(
        connection,
        database,
        "review_bookmarks",
        "target_position",
        "VARCHAR(255) NOT NULL DEFAULT ''",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE review_bookmarks rb
            JOIN interviews i ON i.id = rb.source_interview_id
            SET rb.target_position = i.target_position
            WHERE rb.target_position = ''
            """
        )
    _drop_foreign_key(
        connection,
        database,
        "review_bookmarks",
        "fk_review_bookmarks_source_interview_id",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE review_bookmarks "
            "MODIFY COLUMN source_interview_id BIGINT UNSIGNED NULL"
        )
    _add_foreign_key(
        connection,
        database,
        "review_bookmarks",
        "fk_review_bookmarks_source_interview_id",
        (
            "ALTER TABLE review_bookmarks ADD CONSTRAINT "
            "fk_review_bookmarks_source_interview_id FOREIGN KEY (source_interview_id) "
            "REFERENCES interviews (id) ON DELETE SET NULL ON UPDATE CASCADE"
        ),
    )


def _apply_harness_replay_removal(connection: Any, database: str) -> None:
    _drop_foreign_key(
        connection,
        database,
        "harness_rule_evaluations",
        "fk_harness_rule_evaluations_replay_run_id",
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'harness_rule_evaluations'
              AND COLUMN_NAME = 'replay_run_id'
            """,
            (database,),
        )
        if int(cursor.fetchone()["count"]) > 0:
            cursor.execute(
                "ALTER TABLE harness_rule_evaluations DROP COLUMN replay_run_id"
            )
        cursor.execute("DROP TABLE IF EXISTS harness_replay_runs")


def _apply_resume_delete_scrub(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT original_file_path FROM resumes "
            "WHERE deleted_at IS NOT NULL AND original_file_path <> ''"
        )
        file_paths = [str(row["original_file_path"]) for row in cursor.fetchall()]
        cursor.execute(
            "UPDATE resumes SET original_file_path = '', structured_data = JSON_OBJECT(), "
            "content_hash = NULL WHERE deleted_at IS NOT NULL"
        )

    project_root = Path(__file__).resolve().parents[2]
    upload_root = Path(_resume_upload_dir()).resolve()
    for value in file_paths:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        with suppress(OSError):
            resolved = candidate.resolve()
            if resolved.is_relative_to(upload_root):
                resolved.unlink(missing_ok=True)


def _resume_upload_dir() -> Path:
    from app.core.config import get_settings

    configured = Path(get_settings().upload_dir)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[2] / configured


def _current_database(connection: Any) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS db_name")
        row = cursor.fetchone()
    return str(row["db_name"])


def _ensure_schema_migrations(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(64) NOT NULL,
                description VARCHAR(255) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (version)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


def _migration_applied(connection: Any, version: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM schema_migrations WHERE version = %s LIMIT 1",
            (version,),
        )
        return cursor.fetchone() is not None


def _record_migration(connection: Any, version: str, description: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO schema_migrations (version, description)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE description = VALUES(description)
            """,
            (version, description),
        )


def _add_column(
    connection: Any,
    database: str,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (database, table_name, column_name),
        )
        exists = int(cursor.fetchone()["count"]) > 0
        if not exists:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_virtual_generated_column(
    connection: Any,
    database: str,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXTRA
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (database, table_name, column_name),
        )
        row = cursor.fetchone()
        if row is not None:
            extra = str(row.get("EXTRA") or "").upper()
            if "VIRTUAL GENERATED" in extra:
                return
            if "STORED GENERATED" not in extra:
                raise RuntimeError(
                    f"{table_name}.{column_name} must be a generated column"
                )
            cursor.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")

    _add_column(connection, database, table_name, column_name, definition)


def _add_index(
    connection: Any,
    database: str,
    table_name: str,
    index_name: str,
    statement: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s
            """,
            (database, table_name, index_name),
        )
        exists = int(cursor.fetchone()["count"]) > 0
        if not exists:
            cursor.execute(statement)


def _drop_index(connection: Any, database: str, table_name: str, index_name: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s
            """,
            (database, table_name, index_name),
        )
        exists = int(cursor.fetchone()["count"]) > 0
        if exists:
            cursor.execute(f"DROP INDEX {index_name} ON {table_name}")


def _add_foreign_key(
    connection: Any,
    database: str,
    table_name: str,
    constraint_name: str,
    statement: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = %s
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            """,
            (database, table_name, constraint_name),
        )
        exists = int(cursor.fetchone()["count"]) > 0
        if not exists:
            cursor.execute(statement)


def _drop_foreign_key(
    connection: Any,
    database: str,
    table_name: str,
    constraint_name: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = %s
              AND CONSTRAINT_TYPE = 'FOREIGN KEY'
            """,
            (database, table_name, constraint_name),
        )
        if int(cursor.fetchone()["count"]) > 0:
            cursor.execute(f"ALTER TABLE {table_name} DROP FOREIGN KEY {constraint_name}")


def _create_interview_rounds(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS interview_rounds (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                interview_id BIGINT UNSIGNED NOT NULL,
                agent_type VARCHAR(64) NOT NULL,
                round_type VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                min_main_questions INT NOT NULL,
                max_main_questions INT NOT NULL,
                min_total_questions INT NOT NULL,
                max_total_questions INT NOT NULL,
                score INT NULL,
                result VARCHAR(32) NULL,
                summary JSON NULL,
                is_reference_only TINYINT(1) NOT NULL DEFAULT 0,
                difficulty VARCHAR(32) NOT NULL DEFAULT 'normal',
                time_limit_minutes INT NOT NULL DEFAULT 45,
                started_at DATETIME NULL,
                ended_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uk_interview_rounds_interview_round (interview_id, round_type),
                KEY idx_interview_rounds_interview_id (interview_id),
                CONSTRAINT fk_interview_rounds_interview_id
                    FOREIGN KEY (interview_id) REFERENCES interviews (id)
                    ON DELETE RESTRICT ON UPDATE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


def _create_evaluation_records(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_records (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                evaluation_type VARCHAR(32) NOT NULL,
                evaluation_key VARCHAR(128) NOT NULL,
                interview_id BIGINT UNSIGNED NOT NULL,
                round_id BIGINT UNSIGNED NULL,
                question_id BIGINT UNSIGNED NULL,
                status VARCHAR(32) NOT NULL,
                dimension_scores JSON NOT NULL,
                total_score INT NULL,
                evidence JSON NOT NULL,
                result JSON NULL,
                error_message VARCHAR(1000) NULL,
                prompt_version VARCHAR(64) NOT NULL,
                model_name VARCHAR(128) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uk_evaluation_records_type_key (evaluation_type, evaluation_key),
                KEY idx_evaluation_records_interview_type (interview_id, evaluation_type),
                KEY idx_evaluation_records_round_question (round_id, question_id),
                CONSTRAINT fk_evaluation_records_interview_id
                    FOREIGN KEY (interview_id) REFERENCES interviews (id)
                    ON DELETE RESTRICT ON UPDATE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


def _migrate_memory_task_dedupe_key(connection: Any, database: str) -> None:
    _add_column(connection, database, "memory_tasks", "dedupe_key", "VARCHAR(128) NULL")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE memory_tasks mt
            JOIN (
                SELECT user_id, MAX(id) AS task_id
                FROM memory_tasks
                WHERE task_type = 'memory_clear'
                  AND user_id IS NOT NULL
                  AND status IN ('pending', 'processing', 'retry_wait')
                GROUP BY user_id
            ) active_task ON active_task.task_id = mt.id
            SET mt.dedupe_key = CONCAT('memory_clear:', mt.user_id)
            WHERE mt.dedupe_key IS NULL
            """
        )
    _add_index(
        connection,
        database,
        "memory_tasks",
        "uk_memory_tasks_dedupe_key",
        "CREATE UNIQUE INDEX uk_memory_tasks_dedupe_key ON memory_tasks (dedupe_key)",
    )


def _migrate_resume_default_key(connection: Any, database: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE resumes r
            LEFT JOIN (
                SELECT user_id, MIN(id) AS default_id
                FROM resumes
                WHERE deleted_at IS NULL AND is_default = 1
                GROUP BY user_id
            ) chosen ON chosen.user_id = r.user_id
            SET r.default_key = CASE
                    WHEN chosen.default_id = r.id THEN 'active'
                    ELSE NULL
                END,
                r.is_default = CASE
                    WHEN chosen.default_id = r.id THEN 1
                    ELSE 0
                END
            WHERE r.deleted_at IS NULL
              AND (r.is_default = 1 OR r.default_key IS NOT NULL)
            """
        )
        cursor.execute(
            """
            UPDATE resumes
            SET default_key = NULL
            WHERE deleted_at IS NOT NULL OR is_default = 0
            """
        )
    _add_index(
        connection,
        database,
        "resumes",
        "uk_resumes_user_default_key",
        "CREATE UNIQUE INDEX uk_resumes_user_default_key ON resumes (user_id, default_key)",
    )


def _create_tables_from_init_sql(connection: Any, table_names: list[str]) -> None:
    sql_path = Path(__file__).resolve().parents[2] / "database" / "init_mysql.sql"
    statements = [item.strip() for item in sql_path.read_text(encoding="utf-8").split(";")]
    with connection.cursor() as cursor:
        for table_name in table_names:
            prefix = f"CREATE TABLE IF NOT EXISTS {table_name}"
            statement = next(
                (item for item in statements if item.upper().startswith(prefix.upper())),
                None,
            )
            if statement is None:
                raise RuntimeError(f"Missing init SQL for table {table_name}")
            cursor.execute(statement)


if __name__ == "__main__":
    main()
