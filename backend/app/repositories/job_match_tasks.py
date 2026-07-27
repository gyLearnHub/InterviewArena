import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class JobMatchAnalysisTaskRecord:
    id: int
    user_id: int
    resume_id: int
    target_position: str
    job_description: str
    request_hash: str
    status: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_token: str | None = None
    heartbeat_at: datetime | None = None


class JobMatchAnalysisTaskRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_or_get_active_task(
        self,
        *,
        user_id: int,
        resume_id: int,
        target_position: str,
        job_description: str,
        request_hash: str,
    ) -> JobMatchAnalysisTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM resumes
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                FOR UPDATE
                """,
                (resume_id, user_id),
            )
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                """
                SELECT id
                FROM job_match_analysis_tasks
                WHERE user_id = %s
                  AND resume_id = %s
                  AND request_hash = %s
                  AND status IN ('pending', 'processing')
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, resume_id, request_hash),
            )
            active = cursor.fetchone()
            if active is not None:
                return self.get_task(int(active["id"]))
            cursor.execute(
                """
                INSERT INTO job_match_analysis_tasks (
                    user_id, resume_id, target_position, job_description, request_hash
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    resume_id,
                    target_position,
                    job_description,
                    request_hash,
                ),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError("created job match analysis task is missing")
        return task

    def get_task(self, task_id: int) -> JobMatchAnalysisTaskRecord | None:
        return self._select_task("id = %s", (task_id,))

    def get_task_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> JobMatchAnalysisTaskRecord | None:
        return self._select_task("id = %s AND user_id = %s", (task_id, user_id))

    def claim_due_task(
        self,
        processing_timeout_seconds: int,
    ) -> JobMatchAnalysisTaskRecord | None:
        self.fail_stale_tasks(processing_timeout_seconds)
        processing_token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE job_match_analysis_tasks
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
        return self.get_task(int(row["task_id"]))

    def mark_processing(self, task_id: int) -> bool:
        processing_token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE job_match_analysis_tasks
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
            return int(cursor.rowcount) == 1

    def heartbeat(self, task_id: int, processing_token: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE job_match_analysis_tasks
                SET heartbeat_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (task_id, processing_token),
            )
            return int(cursor.rowcount) == 1

    def mark_completed(
        self,
        task_id: int,
        processing_token: str,
        result: dict[str, Any],
    ) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE job_match_analysis_tasks
                SET status = 'completed',
                    result_json = %s,
                    error_code = NULL,
                    error_message = NULL,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (json.dumps(result, ensure_ascii=False), task_id, processing_token),
            )
            return int(cursor.rowcount) == 1

    def mark_failed(
        self,
        task_id: int,
        processing_token: str,
        *,
        error_code: str,
        error_message: str,
    ) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE job_match_analysis_tasks
                SET status = 'failed',
                    error_code = %s,
                    error_message = %s,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (error_code, error_message, task_id, processing_token),
            )
            return int(cursor.rowcount) == 1

    def fail_stale_tasks(self, processing_timeout_seconds: int) -> int:
        timeout_seconds = max(1, processing_timeout_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE job_match_analysis_tasks
                SET status = 'failed',
                    error_code = 'NETWORK_TIMEOUT',
                    error_message = '任务处理超时，请重新发起。',
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
            return int(cursor.rowcount)

    def _select_task(
        self,
        where_clause: str,
        params: tuple[Any, ...],
    ) -> JobMatchAnalysisTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, resume_id, target_position, job_description,
                       request_hash, status, result_json, error_code, error_message,
                       created_at, started_at, completed_at, processing_token, heartbeat_at
                FROM job_match_analysis_tasks
                WHERE {where_clause}
                """,
                params,
            )
            row = cursor.fetchone()
        return _to_task(row)


def _to_task(row: dict[str, Any] | None) -> JobMatchAnalysisTaskRecord | None:
    if row is None:
        return None
    result_raw = row.get("result_json")
    return JobMatchAnalysisTaskRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        resume_id=int(row["resume_id"]),
        target_position=str(row["target_position"]),
        job_description=str(row["job_description"]),
        request_hash=str(row["request_hash"]),
        status=str(row["status"]),
        result=json.loads(result_raw) if result_raw else None,
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        created_at=row.get("created_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        processing_token=row.get("processing_token"),
        heartbeat_at=row.get("heartbeat_at"),
    )
