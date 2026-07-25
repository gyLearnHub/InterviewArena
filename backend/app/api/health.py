from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.mysql import mysql_connection
from app.services.avatar_storage import resolve_avatar_upload_dir
from app.services.resume_parser import resolve_upload_dir
from app.services.runner_health import runner_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check(request: Request) -> JSONResponse:
    checks: dict[str, dict[str, Any]] = {
        "settings": {"status": "ok"},
        "database": {"status": "ok"},
        "llm": {"status": "ok"},
        "uploads": {"status": "ok"},
        "avatars": {"status": "ok"},
        "autonomous_evolution": {"status": "ok"},
        "resume_parse_runner": {"status": "ok"},
        "interview_operation_runner": {"status": "ok"},
        "memory_runner": {"status": "ok"},
    }

    try:
        settings = get_settings()
    except Exception as exc:
        checks["settings"] = _failed_check(exc)
        return _readiness_response(checks)

    if not settings.deepseek_api_key:
        checks["llm"] = {"status": "degraded", "reason": "DEEPSEEK_API_KEY is not configured"}

    try:
        with mysql_connection(settings.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ready")
                cursor.fetchone()
                if settings.evolution_enabled:
                    checks["autonomous_evolution"] = _evolution_schema_check(cursor)
                checks.update(_background_queue_checks(cursor, settings))
    except Exception as exc:
        checks["database"] = _failed_check(exc)
        if settings.evolution_enabled:
            checks["autonomous_evolution"] = {
                "status": "failed",
                "reason": "database is unavailable",
            }

    if settings.evolution_enabled:
        runner = getattr(request.app.state, "evolution_task_runner", None)
        if runner is None or runner.done():
            checks["autonomous_evolution"] = {
                "status": "failed",
                "reason": "autonomous evolution runner is not running",
            }
    else:
        checks["autonomous_evolution"] = {
            "status": "degraded",
            "reason": "autonomous evolution is disabled",
        }

    for check_name, state_name, app_state_name in (
        ("resume_parse_runner", "resume_parse", "resume_parse_task_runner"),
        (
            "interview_operation_runner",
            "interview_operation",
            "interview_operation_task_runner",
        ),
        ("memory_runner", "memory", "memory_task_runner"),
    ):
        task = getattr(request.app.state, app_state_name, None)
        if task is None or task.done():
            checks[check_name] = {
                "status": "failed",
                "reason": "runner is not running",
            }
            continue
        runtime_health = runner_health(state_name)
        queue_health = checks.get(check_name, {})
        combined_status = (
            "failed"
            if "failed" in {queue_health.get("status"), runtime_health.get("status")}
            else "degraded"
            if "degraded" in {queue_health.get("status"), runtime_health.get("status")}
            else "ok"
        )
        checks[check_name] = {
            **queue_health,
            **runtime_health,
            "status": combined_status,
        }

    upload_dir = resolve_upload_dir(settings)
    avatar_upload_dir = resolve_avatar_upload_dir(settings)
    checks["uploads"] = _directory_check(upload_dir)
    checks["avatars"] = _directory_check(avatar_upload_dir)

    return _readiness_response(checks)


def _readiness_response(checks: dict[str, dict[str, Any]]) -> JSONResponse:
    has_failed = any(item["status"] == "failed" for item in checks.values())
    overall_status = "failed" if has_failed else "ok"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE if has_failed else status.HTTP_200_OK
    return JSONResponse(
        status_code=status_code,
        content={"status": overall_status, "checks": checks},
    )


def _directory_check(path: Path) -> dict[str, Any]:
    target = path if path.exists() else path.parent
    if target.exists() and target.is_dir():
        return {"status": "ok"}
    return {"status": "failed", "reason": "directory is not available"}


def _failed_check(exc: Exception) -> dict[str, str]:
    return {"status": "failed", "reason": exc.__class__.__name__}


def _evolution_schema_check(cursor: Any) -> dict[str, str]:
    required_tables = {
        "harness_artifact_bundles",
        "harness_artifacts",
        "harness_evolution_runs",
        "harness_evolution_samples",
        "harness_evolution_events",
        "harness_evolution_observations",
    }
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
    existing_tables = {str(row["TABLE_NAME"]) for row in cursor.fetchall()}
    if existing_tables != required_tables:
        return {"status": "failed", "reason": "autonomous evolution tables are missing"}
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND (
              (TABLE_NAME = 'interviews' AND COLUMN_NAME IN ('job_family_key', 'harness_bundle_id'))
              OR (
                  TABLE_NAME = 'harness_evolution_runs'
                  AND COLUMN_NAME IN (
                      'user_id', 'processing_token', 'heartbeat_at',
                      'trigger_cursor_ended_at', 'trigger_cursor_interview_id'
                  )
              )
              OR (
                  TABLE_NAME = 'harness_artifact_bundles'
                  AND COLUMN_NAME IN ('user_id', 'active_scope_key')
              )
          )
        """
    )
    required_columns = {
        "job_family_key",
        "harness_bundle_id",
        "user_id",
        "active_scope_key",
        "processing_token",
        "heartbeat_at",
        "trigger_cursor_ended_at",
        "trigger_cursor_interview_id",
    }
    if {str(row["COLUMN_NAME"]) for row in cursor.fetchall()} != required_columns:
        return {"status": "failed", "reason": "autonomous evolution columns are missing"}
    cursor.execute(
        """
        SELECT COUNT(*) AS count
        FROM schema_migrations
        WHERE version IN (
            '2026_07_13_harness_evolution_hardening',
            '2026_07_14_harness_evolution_user_scope'
        )
        """
    )
    if int(cursor.fetchone()["count"]) != 2:
        return {"status": "failed", "reason": "autonomous evolution migration is missing"}
    return {"status": "ok"}


def _background_queue_checks(
    cursor: Any,
    settings: Any,
) -> dict[str, dict[str, Any]]:
    definitions = {
        "resume_parse_runner": (
            (
                ("resume_parse_tasks", "status = 'pending'"),
                (
                    "file_cleanup_tasks",
                    (
                        "status = 'pending' OR (status = 'retry_wait' "
                        "AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP()))"
                    ),
                ),
            ),
            settings.usage_limit_active_timeout_seconds,
        ),
        "interview_operation_runner": (
            (
                (
                    "interview_operation_tasks",
                    (
                        "status = 'pending' OR (status = 'retry_wait' "
                        "AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP()))"
                    ),
                ),
            ),
            settings.interview_task_processing_timeout_seconds,
        ),
        "memory_runner": (
            (
                (
                    "memory_tasks",
                    (
                        "status = 'pending' OR (status = 'retry_wait' "
                        "AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP()))"
                    ),
                ),
            ),
            settings.memory_task_processing_timeout_seconds,
        ),
    }
    checks: dict[str, dict[str, Any]] = {}
    for name, (queues, threshold) in definitions.items():
        pending_count = 0
        lag = 0
        for table, due_predicate in queues:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS pending_count,
                       COALESCE(
                           TIMESTAMPDIFF(SECOND, MIN(created_at), UTC_TIMESTAMP()),
                           0
                       ) AS oldest_pending_seconds
                FROM {table}
                WHERE {due_predicate}
                """
            )
            row = cursor.fetchone() or {}
            pending_count += int(row.get("pending_count") or 0)
            lag = max(lag, int(row.get("oldest_pending_seconds") or 0))
        checks[name] = {
            "status": "failed" if lag > max(1, int(threshold)) else "ok",
            "pending_count": pending_count,
            "oldest_pending_seconds": lag,
        }
        if checks[name]["status"] == "failed":
            checks[name]["reason"] = "queue lag exceeds processing timeout"
    return checks
