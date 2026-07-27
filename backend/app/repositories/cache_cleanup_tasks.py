import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class CacheCleanupTaskRecord:
    id: int
    user_id: int
    interview_ids: list[int]
    status: str
    attempt_count: int
    max_retries: int
    processing_token: str | None


class CacheCleanupTaskRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def enqueue(
        self,
        *,
        user_id: int,
        interview_ids: list[int],
        max_retries: int = 20,
    ) -> int:
        normalized_ids = sorted(set(interview_ids))
        if not normalized_ids:
            raise ValueError("cache cleanup requires at least one interview id")
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cache_cleanup_tasks (
                    user_id, interview_ids_json, status, max_retries
                )
                VALUES (%s, %s, 'pending', %s)
                """,
                (
                    user_id,
                    json.dumps(normalized_ids),
                    max(1, max_retries),
                ),
            )
            return int(cursor.lastrowid)

    def claim_due(
        self,
        processing_timeout_seconds: int = 900,
    ) -> CacheCleanupTaskRecord | None:
        token = uuid4().hex
        timeout_seconds = max(1, processing_timeout_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cache_cleanup_tasks
                SET id = LAST_INSERT_ID(id),
                    status = 'processing',
                    processing_token = %s,
                    attempt_count = attempt_count + 1,
                    started_at = UTC_TIMESTAMP(),
                    error_message = NULL
                WHERE status = 'pending'
                   OR (
                       status = 'retry_wait'
                       AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP())
                   )
                   OR (
                       status = 'processing'
                       AND (
                           started_at IS NULL
                           OR started_at <= DATE_SUB(
                               UTC_TIMESTAMP(), INTERVAL %s SECOND
                           )
                       )
                   )
                ORDER BY created_at, id
                LIMIT 1
                """,
                (token, timeout_seconds),
            )
            if int(cursor.rowcount) != 1:
                return None
            cursor.execute("SELECT LAST_INSERT_ID() AS task_id")
            id_row = cursor.fetchone()
            if id_row is None:
                return None
            cursor.execute(
                """
                SELECT id, user_id, interview_ids_json, status,
                       attempt_count, max_retries, processing_token
                FROM cache_cleanup_tasks
                WHERE id = %s
                """,
                (int(id_row["task_id"]),),
            )
            row = cursor.fetchone()
        return _to_record(row)

    def complete(self, task_id: int, processing_token: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cache_cleanup_tasks
                SET status = 'completed',
                    processing_token = NULL,
                    next_retry_at = NULL,
                    error_message = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (task_id, processing_token),
            )
            return int(cursor.rowcount) == 1

    def complete_pending(self, task_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cache_cleanup_tasks
                SET status = 'completed',
                    error_message = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s AND status = 'pending'
                """,
                (task_id,),
            )
            return int(cursor.rowcount) == 1

    def retry(self, task: CacheCleanupTaskRecord, error_message: str) -> bool:
        exhausted = task.attempt_count >= task.max_retries
        retry_delay_seconds = min(3600, (2 ** min(task.attempt_count, 10)) * 5)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE cache_cleanup_tasks
                SET status = %s,
                    next_retry_at = CASE
                        WHEN %s THEN NULL
                        ELSE DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND)
                    END,
                    completed_at = CASE WHEN %s THEN UTC_TIMESTAMP() ELSE NULL END,
                    processing_token = NULL,
                    error_message = %s
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (
                    "failed" if exhausted else "retry_wait",
                    exhausted,
                    retry_delay_seconds,
                    exhausted,
                    error_message[:500],
                    task.id,
                    task.processing_token,
                ),
            )
            return int(cursor.rowcount) == 1


def _to_record(row: dict[str, Any] | None) -> CacheCleanupTaskRecord | None:
    if row is None:
        return None
    raw_ids = row.get("interview_ids_json")
    parsed_ids = json.loads(raw_ids) if isinstance(raw_ids, str) else raw_ids
    return CacheCleanupTaskRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        interview_ids=[int(value) for value in list(parsed_ids or [])],
        status=str(row["status"]),
        attempt_count=int(row["attempt_count"]),
        max_retries=int(row["max_retries"]),
        processing_token=row.get("processing_token"),
    )
