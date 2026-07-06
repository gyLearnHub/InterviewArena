import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

DEFAULT_PROCESSING_TIMEOUT_SECONDS = 15 * 60


@dataclass(frozen=True)
class MemoryTaskRecord:
    id: int
    task_type: str
    user_id: int | None
    interview_id: int | None
    memory_collection: str | None
    memory_id: int | None
    status: str
    retry_count: int
    max_retries: int
    next_retry_at: datetime | None
    error_message: str | None
    result: dict[str, Any] | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    dedupe_key: str | None = None


class MemoryTaskRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_summary_task(
        self,
        *,
        user_id: int,
        interview_id: int,
        max_retries: int,
    ) -> MemoryTaskRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memory_tasks (task_type, user_id, interview_id, status, max_retries)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
                """,
                ("memory_summary", user_id, interview_id, "pending", max_retries),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_by_id(task_id)
        if task is None:
            raise RuntimeError("memory summary task was not saved")
        return task

    def create_or_get_clear_task(self, *, user_id: int, max_retries: int) -> MemoryTaskRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO memory_tasks (task_type, user_id, status, max_retries, dedupe_key)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)
                """,
                ("memory_clear", user_id, "pending", max_retries, _clear_dedupe_key(user_id)),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_by_id(task_id)
        if task is None:
            raise RuntimeError("memory clear task was not saved")
        return task

    def latest_clear_task(self, user_id: int) -> MemoryTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM memory_tasks
                WHERE user_id = %s AND task_type = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, "memory_clear"),
            )
            row = cursor.fetchone()
        return _to_task(row)

    def count_summary_tasks_by_status(self, user_id: int) -> dict[str, int]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM memory_tasks
                WHERE user_id = %s
                  AND task_type = 'memory_summary'
                GROUP BY status
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return {str(row["status"]): int(row.get("count") or 0) for row in rows}

    def get_by_id(self, task_id: int) -> MemoryTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM memory_tasks WHERE id = %s", (task_id,))
            row = cursor.fetchone()
        return _to_task(row)

    def claim_due_task(
        self,
        processing_timeout_seconds: int = DEFAULT_PROCESSING_TIMEOUT_SECONDS,
    ) -> MemoryTaskRecord | None:
        timeout_seconds = max(1, processing_timeout_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE memory_tasks
                SET status = 'failed',
                    completed_at = UTC_TIMESTAMP(),
                    error_message = 'processing_timeout',
                    dedupe_key = NULL
                WHERE status = 'processing'
                  AND retry_count >= max_retries
                  AND (
                      started_at IS NULL
                      OR started_at <= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s SECOND)
                  )
                """,
                (timeout_seconds,),
            )
            cursor.execute(
                """
                UPDATE memory_tasks
                SET id = LAST_INSERT_ID(id),
                    retry_count = CASE
                        WHEN status = 'processing' THEN retry_count + 1
                        ELSE retry_count
                    END,
                    next_retry_at = NULL,
                    error_message = CASE
                        WHEN status = 'processing' THEN 'processing_timeout'
                        ELSE NULL
                    END,
                    status = 'processing',
                    started_at = UTC_TIMESTAMP(),
                    completed_at = NULL
                WHERE status = 'pending'
                   OR (
                       status = 'retry_wait'
                       AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP())
                   )
                   OR (
                       status = 'processing'
                       AND retry_count < max_retries
                       AND (
                           started_at IS NULL
                           OR started_at <= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s SECOND)
                       )
                   )
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (timeout_seconds,),
            )
            if cursor.rowcount != 1:
                return None
            cursor.execute("SELECT LAST_INSERT_ID() AS task_id")
            row = cursor.fetchone()
            if row is None:
                return None
            task_id = int(row["task_id"])
        return self.get_by_id(task_id)

    def mark_completed(self, task_id: int, result: dict[str, Any] | None = None) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE memory_tasks
                SET status = 'completed',
                    completed_at = UTC_TIMESTAMP(),
                    result = %s,
                    error_message = NULL,
                    dedupe_key = NULL
                WHERE id = %s
                """,
                (json.dumps(result or {}, ensure_ascii=False), task_id),
            )

    def mark_failed_or_retry(self, task: MemoryTaskRecord, error_message: str) -> None:
        retry_count = task.retry_count + 1
        if retry_count < task.max_retries:
            status = "retry_wait"
            retry_delay_seconds = min(300, 2**retry_count * 5)
        else:
            status = "failed"
            retry_count = min(retry_count, task.max_retries)
            retry_delay_seconds = None
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE memory_tasks
                SET status = %s,
                    retry_count = %s,
                    next_retry_at = CASE
                        WHEN %s IS NULL THEN NULL
                        ELSE DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND)
                    END,
                    error_message = %s,
                    dedupe_key = CASE
                        WHEN %s = 'failed' THEN NULL
                        ELSE dedupe_key
                    END
                WHERE id = %s
                """,
                (
                    status,
                    retry_count,
                    retry_delay_seconds,
                    retry_delay_seconds,
                    error_message[:1000],
                    status,
                    task.id,
                ),
            )


def _to_task(row: dict[str, Any] | None) -> MemoryTaskRecord | None:
    if row is None:
        return None
    return MemoryTaskRecord(
        id=int(row["id"]),
        task_type=str(row["task_type"]),
        user_id=int(row["user_id"]) if row.get("user_id") is not None else None,
        interview_id=int(row["interview_id"]) if row.get("interview_id") is not None else None,
        memory_collection=row.get("memory_collection"),
        memory_id=int(row["memory_id"]) if row.get("memory_id") is not None else None,
        status=str(row["status"]),
        retry_count=int(row.get("retry_count") or 0),
        max_retries=int(row.get("max_retries") or 0),
        next_retry_at=row.get("next_retry_at"),
        error_message=row.get("error_message"),
        result=_json_dict(row.get("result")),
        created_at=row.get("created_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        dedupe_key=row.get("dedupe_key"),
    )


def _json_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return None


def _clear_dedupe_key(user_id: int) -> str:
    return f"memory_clear:{user_id}"
