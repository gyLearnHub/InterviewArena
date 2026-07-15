import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class InterviewOperationTaskRecord:
    id: int
    user_id: int
    interview_id: int
    operation: str
    status: str
    round_id: int | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_token: str | None = None
    heartbeat_at: datetime | None = None


class InterviewOperationTaskRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_task(
        self,
        *,
        user_id: int,
        interview_id: int,
        operation: str,
        round_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> InterviewOperationTaskRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO interview_operation_tasks (
                    user_id, interview_id, round_id, operation, payload_json
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, interview_id, round_id, operation, _json_dump(payload)),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError("created interview operation task is missing")
        return task

    def create_task_for_owned_interview(
        self,
        *,
        user_id: int,
        interview_id: int,
        operation: str,
        round_id: int | None = None,
        payload: dict[str, Any] | None = None,
        exclusive_operations: tuple[str, ...] = (),
    ) -> InterviewOperationTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM interviews WHERE id = %s AND user_id = %s FOR UPDATE",
                (interview_id, user_id),
            )
            if cursor.fetchone() is None:
                return None
            if round_id is not None:
                cursor.execute(
                    "SELECT 1 FROM interview_rounds WHERE id = %s AND interview_id = %s",
                    (round_id, interview_id),
                )
                if cursor.fetchone() is None:
                    return None
            if exclusive_operations:
                placeholders = ", ".join(["%s"] * len(exclusive_operations))
                cursor.execute(
                    f"""
                    SELECT 1
                    FROM interview_operation_tasks
                    WHERE user_id = %s
                      AND interview_id = %s
                      AND operation IN ({placeholders})
                      AND status IN ('pending', 'processing')
                    LIMIT 1
                    """,
                    (user_id, interview_id, *exclusive_operations),
                )
                if cursor.fetchone() is not None:
                    return None
            cursor.execute(
                """
                INSERT INTO interview_operation_tasks (
                    user_id, interview_id, round_id, operation, payload_json
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, interview_id, round_id, operation, _json_dump(payload)),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError("created interview operation task is missing")
        return task

    def has_active_task_for_scope(
        self,
        *,
        user_id: int,
        interview_id: int,
        operations: tuple[str, ...],
    ) -> bool:
        if not operations:
            return False
        placeholders = ", ".join(["%s"] * len(operations))
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT 1
                FROM interview_operation_tasks
                WHERE user_id = %s
                  AND interview_id = %s
                  AND operation IN ({placeholders})
                  AND status IN ('pending', 'processing')
                LIMIT 1
                """,
                (user_id, interview_id, *operations),
            )
            return cursor.fetchone() is not None

    def get_task(self, task_id: int) -> InterviewOperationTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, interview_id, round_id, operation, payload_json,
                       status, result_json, error_code, error_message,
                       created_at, started_at, completed_at, processing_token, heartbeat_at
                FROM interview_operation_tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()
        return _to_task(row)

    def get_task_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> InterviewOperationTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, interview_id, round_id, operation, payload_json,
                       status, result_json, error_code, error_message,
                       created_at, started_at, completed_at, processing_token, heartbeat_at
                FROM interview_operation_tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user_id),
            )
            row = cursor.fetchone()
        return _to_task(row)

    def claim_due_task(
        self,
        processing_timeout_seconds: int,
    ) -> InterviewOperationTaskRecord | None:
        timeout_seconds = max(1, processing_timeout_seconds)
        processing_token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET status = 'failed',
                    error_code = 'NETWORK_TIMEOUT',
                    error_message = 'processing_timeout',
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE status = 'processing'
                  AND (
                      COALESCE(heartbeat_at, started_at) IS NULL
                      OR COALESCE(heartbeat_at, started_at) <= DATE_SUB(
                          UTC_TIMESTAMP(), INTERVAL %s SECOND
                      )
                  )
                """,
                (timeout_seconds,),
            )
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET id = LAST_INSERT_ID(id),
                    status = 'processing',
                    started_at = UTC_TIMESTAMP(),
                    processing_token = %s,
                    heartbeat_at = UTC_TIMESTAMP(),
                    completed_at = NULL,
                    error_code = NULL,
                    error_message = NULL
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (processing_token,),
            )
            if int(cursor.rowcount) != 1:
                return None
            cursor.execute("SELECT LAST_INSERT_ID() AS task_id")
            row = cursor.fetchone()
            if row is None:
                return None
            task_id = int(row["task_id"])
        return self.get_task(task_id)

    def mark_processing(self, task_id: int) -> bool:
        processing_token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET status = 'processing',
                    started_at = UTC_TIMESTAMP(),
                    processing_token = %s,
                    heartbeat_at = UTC_TIMESTAMP(),
                    completed_at = NULL,
                    error_code = NULL,
                    error_message = NULL
                WHERE id = %s AND status = 'pending'
                """,
                (processing_token, task_id),
            )
            return int(cursor.rowcount) > 0

    def heartbeat(self, task_id: int, processing_token: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET heartbeat_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (task_id, processing_token),
            )
            return int(cursor.rowcount) > 0

    def mark_completed(
        self,
        task_id: int,
        result: dict[str, Any],
        *,
        processing_token: str | None = None,
    ) -> bool:
        token_filter = "" if processing_token is None else "AND processing_token = %s"
        params: tuple[Any, ...] = (
            (json.dumps(result, ensure_ascii=False), task_id)
            if processing_token is None
            else (json.dumps(result, ensure_ascii=False), task_id, processing_token)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE interview_operation_tasks
                SET status = 'completed',
                    result_json = %s,
                    error_code = NULL,
                    error_message = NULL,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s AND status = 'processing' {token_filter}
                """,
                params,
            )
            return int(cursor.rowcount) > 0

    def mark_completed_after_processing_timeout(
        self,
        task_id: int,
        result: dict[str, Any],
    ) -> bool:
        """Restore consistency when business data committed after the task lease expired."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET status = 'completed',
                    result_json = %s,
                    error_code = NULL,
                    error_message = NULL,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'failed'
                  AND error_message = 'processing_timeout'
                """,
                (json.dumps(result, ensure_ascii=False), task_id),
            )
            return int(cursor.rowcount) > 0

    def mark_failed(
        self,
        task_id: int,
        *,
        error_code: str | None,
        error_message: str,
        processing_token: str | None = None,
    ) -> bool:
        token_filter = "" if processing_token is None else "AND processing_token = %s"
        params: tuple[Any, ...] = (
            (error_code, error_message, task_id)
            if processing_token is None
            else (error_code, error_message, task_id, processing_token)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE interview_operation_tasks
                SET status = 'failed',
                    error_code = %s,
                    error_message = %s,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s AND status = 'processing' {token_filter}
                """,
                params,
            )
            return int(cursor.rowcount) > 0


def _to_task(row: dict[str, Any] | None) -> InterviewOperationTaskRecord | None:
    if row is None:
        return None
    result_raw = row.get("result_json")
    return InterviewOperationTaskRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        interview_id=int(row["interview_id"]),
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        operation=str(row["operation"]),
        status=str(row["status"]),
        payload=_json_dict(row.get("payload_json")),
        result=json.loads(result_raw) if result_raw else None,
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        created_at=row.get("created_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        processing_token=row.get("processing_token"),
        heartbeat_at=row.get("heartbeat_at"),
    )


def _json_dump(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


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
