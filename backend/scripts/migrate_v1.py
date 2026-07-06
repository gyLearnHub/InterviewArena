import sys
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
    "candidate_memories",
    "interviewer_memories",
    "agent_memories",
    "memory_tasks",
    "notifications",
    "rag_audit_logs",
    "harness_traces",
    "harness_trace_events",
    "harness_checkpoints",
    "harness_replay_runs",
    "harness_rule_evaluations",
    "harness_improvement_candidates",
]
MIGRATION_VERSION = "2026_07_06_v1"
MIGRATION_DESCRIPTION = "InterviewArena v1 cumulative schema migration"


def main() -> None:
    with mysql_connection() as connection:
        migrate(connection)


def migrate(connection: Any) -> None:
    database = _current_database(connection)
    _ensure_schema_migrations(connection)
    if _migration_applied(connection, MIGRATION_VERSION):
        return

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
    _create_tables_from_init_sql(connection, INIT_SQL_TABLES_TO_CREATE)
    _migrate_memory_task_dedupe_key(connection, database)
    _record_migration(connection, MIGRATION_VERSION, MIGRATION_DESCRIPTION)


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
