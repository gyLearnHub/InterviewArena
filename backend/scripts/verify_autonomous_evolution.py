import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

from app.db.mysql import mysql_connection

REQUIRED_TABLES = {
    "harness_artifact_bundles",
    "harness_artifacts",
    "harness_evolution_runs",
    "harness_evolution_samples",
    "harness_evolution_events",
    "harness_evolution_observations",
}
REQUIRED_RUN_COLUMNS = {
    "user_id",
    "processing_token",
    "heartbeat_at",
    "trigger_cursor_ended_at",
    "trigger_cursor_interview_id",
}
REQUIRED_BUNDLE_COLUMNS = {
    "user_id",
    "active_scope_key",
}
REQUIRED_CONSTRAINTS = {
    "fk_interviews_harness_bundle_id",
    "uk_harness_artifact_bundles_one_active",
}
HARDENING_MIGRATION = "2026_07_13_harness_evolution_hardening"
USER_SCOPE_MIGRATION = "2026_07_14_harness_evolution_user_scope"


def verify(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN (
                  'harness_artifact_bundles', 'harness_artifacts',
                  'harness_evolution_runs', 'harness_evolution_samples',
                  'harness_evolution_events', 'harness_evolution_observations'
              )
            """
        )
        tables = {str(row["TABLE_NAME"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'harness_evolution_runs'
              AND COLUMN_NAME IN (
                  'user_id', 'processing_token', 'heartbeat_at',
                  'trigger_cursor_ended_at', 'trigger_cursor_interview_id'
              )
            """
        )
        columns = {str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'harness_artifact_bundles'
              AND COLUMN_NAME IN ('user_id', 'active_scope_key')
            """
        )
        bundle_columns = {str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
        cursor.execute(
            """
            SELECT CONSTRAINT_NAME
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND CONSTRAINT_NAME IN (
                  'fk_interviews_harness_bundle_id',
                  'uk_harness_artifact_bundles_one_active'
              )
            """
        )
        constraints = {str(row["CONSTRAINT_NAME"]) for row in cursor.fetchall()}
        cursor.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = %s",
            (HARDENING_MIGRATION,),
        )
        hardening_migration_count = int(cursor.fetchone()["count"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = %s",
            (USER_SCOPE_MIGRATION,),
        )
        user_scope_migration_count = int(cursor.fetchone()["count"])
        cursor.execute(
            """
            SELECT user_id, job_family_key
            FROM harness_artifact_bundles
            WHERE is_active = 1
            GROUP BY user_id, job_family_key
            HAVING COUNT(*) > 1
            """
        )
        duplicate_active_scopes = len(cursor.fetchall())
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM interviews i
            LEFT JOIN harness_artifact_bundles b ON b.id = i.harness_bundle_id
            WHERE i.harness_bundle_id IS NOT NULL AND b.id IS NULL
            """
        )
        orphan_interview_bundles = int(cursor.fetchone()["count"])
        cursor.execute(
            """
            SELECT (
                SELECT COUNT(*) FROM users WHERE username LIKE 'evolution-check-%%'
            ) + (
                SELECT COUNT(*)
                FROM harness_artifact_bundles
                WHERE job_family_key LIKE 'verification-%%'
            ) AS count
            """
        )
        verification_residue = int(cursor.fetchone()["count"])

    checks = {
        "tables": tables == REQUIRED_TABLES,
        "run_columns": columns == REQUIRED_RUN_COLUMNS,
        "bundle_columns": bundle_columns == REQUIRED_BUNDLE_COLUMNS,
        "constraints": constraints == REQUIRED_CONSTRAINTS,
        "migration": hardening_migration_count == 1 and user_scope_migration_count == 1,
        "single_active_bundle_per_user": duplicate_active_scopes == 0,
        "interview_bundle_integrity": orphan_interview_bundles == 0,
        "verification_transaction_rolled_back": verification_residue == 0,
    }
    return {
        "status": "ok" if all(checks.values()) else "failed",
        "checks": checks,
        "details": {
            "tables": sorted(tables),
            "run_columns": sorted(columns),
            "bundle_columns": sorted(bundle_columns),
            "constraints": sorted(constraints),
        },
    }


def main() -> None:
    with mysql_connection() as connection:
        result = verify(connection)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
