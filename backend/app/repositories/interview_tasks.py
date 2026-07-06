import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class InterviewOperationTaskRecord:
    id: int
    user_id: int
    interview_id: int
    operation: str
    status: str
    round_id: int | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


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
    ) -> InterviewOperationTaskRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO interview_operation_tasks (
                    user_id, interview_id, round_id, operation
                )
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, interview_id, round_id, operation),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError("created interview operation task is missing")
        return task

    def get_task(self, task_id: int) -> InterviewOperationTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, interview_id, round_id, operation, status, result_json,
                       error_code, error_message, created_at, started_at, completed_at
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
                SELECT id, user_id, interview_id, round_id, operation, status, result_json,
                       error_code, error_message, created_at, started_at, completed_at
                FROM interview_operation_tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user_id),
            )
            row = cursor.fetchone()
        return _to_task(row)

    def mark_processing(self, task_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'pending'
                """,
                (task_id,),
            )

    def mark_completed(self, task_id: int, result: dict[str, Any]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET status = 'completed',
                    result_json = %s,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (json.dumps(result, ensure_ascii=False), task_id),
            )

    def mark_failed(
        self,
        task_id: int,
        *,
        error_code: str | None,
        error_message: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_operation_tasks
                SET status = 'failed',
                    error_code = %s,
                    error_message = %s,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (error_code, error_message, task_id),
            )


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
        result=json.loads(result_raw) if result_raw else None,
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        created_at=row.get("created_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
    )
