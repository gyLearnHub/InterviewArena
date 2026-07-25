import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ACTIVE_INTERVIEW_DEPENDENCY_STATUSES = ("created", "in_progress", "paused")


@dataclass(frozen=True)
class ResumeRecord:
    id: int
    user_id: int
    original_file_path: str
    structured_data: dict[str, Any]
    content_hash: str | None = None
    display_name: str | None = None
    is_default: bool = False
    created_at: datetime | None = None
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class ResumeSummaryRecord:
    id: int
    name: str
    uploaded_at: datetime
    last_used_at: datetime | None
    parse_status: str
    is_default: bool = False


@dataclass(frozen=True)
class ResumeDetailRecord:
    id: int
    name: str
    uploaded_at: datetime
    last_used_at: datetime | None
    parse_status: str
    structured_data: dict[str, Any]
    is_default: bool = False


@dataclass(frozen=True)
class ResumeParseTaskRecord:
    id: int
    user_id: int
    original_file_path: str
    content_hash: str
    status: str
    resume_id: int | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processing_token: str | None = None
    heartbeat_at: datetime | None = None


@dataclass(frozen=True)
class FileCleanupTaskRecord:
    id: int
    original_file_path: str
    status: str
    attempt_count: int
    max_retries: int
    processing_token: str | None = None


class ResumeRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def commit(self) -> None:
        self.connection.commit()

    def create(
        self,
        user_id: int,
        original_file_path: str,
        structured_data: dict[str, Any],
        content_hash: str | None = None,
    ) -> ResumeRecord:
        structured_json = json.dumps(structured_data, ensure_ascii=False)
        display_name = Path(original_file_path).name
        with self.connection.cursor() as cursor:
            self._lock_user_resumes(cursor, user_id)
            is_default = not self._has_active_resume_with_cursor(cursor, user_id)
            cursor.execute(
                """
                INSERT INTO resumes (
                    user_id, original_file_path, display_name, content_hash,
                    structured_data, is_default, default_key
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    original_file_path,
                    display_name,
                    content_hash,
                    structured_json,
                    is_default,
                    _default_key(is_default),
                ),
            )
            resume_id = int(cursor.lastrowid)
        return ResumeRecord(
            id=resume_id,
            user_id=user_id,
            original_file_path=original_file_path,
            structured_data=structured_data,
            content_hash=content_hash,
            display_name=display_name,
            is_default=is_default,
        )

    def get_by_content_hash(self, user_id: int, content_hash: str) -> ResumeRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, display_name, content_hash,
                       structured_data, is_default, created_at, deleted_at
                FROM resumes
                WHERE user_id = %s AND content_hash = %s AND deleted_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, content_hash),
            )
            row = cursor.fetchone()
        return _to_resume(row) if row is not None else None

    def get_by_id_for_user(
        self,
        resume_id: int,
        user_id: int,
        *,
        include_deleted: bool = False,
    ) -> ResumeRecord | None:
        clauses = ["id = %s", "user_id = %s"]
        params: list[Any] = [resume_id, user_id]
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, original_file_path, display_name, content_hash,
                       structured_data, is_default, created_at, deleted_at
                FROM resumes
                WHERE {" AND ".join(clauses)}
                """,
                tuple(params),
            )
            row = cursor.fetchone()
        return _to_resume(row) if row is not None else None

    def get_detail_for_user(self, resume_id: int, user_id: int) -> ResumeDetailRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    r.id,
                    r.original_file_path,
                    r.display_name,
                    r.structured_data,
                    r.created_at AS uploaded_at,
                    r.is_default,
                    MAX(COALESCE(i.last_active_at, i.started_at, i.created_at)) AS last_used_at
                FROM resumes r
                LEFT JOIN interviews i ON i.resume_id = r.id AND i.user_id = r.user_id
                WHERE r.id = %s AND r.user_id = %s AND r.deleted_at IS NULL
                GROUP BY r.id, r.original_file_path, r.display_name, r.structured_data,
                         r.created_at, r.is_default
                """,
                (resume_id, user_id),
            )
            row = cursor.fetchone()
        return _to_detail(row) if row is not None else None

    def list_by_user(self, user_id: int) -> list[ResumeRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, display_name, content_hash,
                       structured_data, is_default, created_at, deleted_at
                FROM resumes
                WHERE user_id = %s AND deleted_at IS NULL
                ORDER BY id ASC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [_to_resume(row) for row in rows]

    def list_summaries_by_user(self, user_id: int) -> list[ResumeSummaryRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    r.id,
                    r.original_file_path,
                    r.display_name,
                    r.is_default,
                    r.created_at AS uploaded_at,
                    MAX(COALESCE(i.last_active_at, i.started_at, i.created_at)) AS last_used_at
                FROM resumes r
                LEFT JOIN interviews i ON i.resume_id = r.id AND i.user_id = r.user_id
                WHERE r.user_id = %s AND r.deleted_at IS NULL
                GROUP BY r.id, r.original_file_path, r.display_name, r.is_default, r.created_at
                ORDER BY r.is_default DESC, COALESCE(last_used_at, uploaded_at) DESC, r.id DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [_to_summary(row) for row in rows]

    def has_active_resume(self, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM resumes WHERE user_id = %s AND deleted_at IS NULL LIMIT 1",
                (user_id,),
            )
            return cursor.fetchone() is not None

    def rename_for_user(self, resume_id: int, user_id: int, name: str) -> ResumeDetailRecord | None:
        clean_name = name.strip()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resumes
                SET display_name = %s
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (clean_name, resume_id, user_id),
            )
        return self.get_detail_for_user(resume_id, user_id)

    def set_default_for_user(
        self,
        resume_id: int,
        user_id: int,
    ) -> ResumeDetailRecord | None:
        with self.connection.cursor() as cursor:
            self._lock_user_resumes(cursor, user_id)
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
                UPDATE resumes
                SET is_default = 0, default_key = NULL
                WHERE user_id = %s AND deleted_at IS NULL
                """,
                (user_id,),
            )
            cursor.execute(
                """
                UPDATE resumes
                SET is_default = 1, default_key = %s
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (ACTIVE_DEFAULT_KEY, resume_id, user_id),
            )
        return self.get_detail_for_user(resume_id, user_id)

    def soft_delete_for_user(self, resume_id: int, user_id: int) -> bool:
        status_placeholders = _placeholders(ACTIVE_INTERVIEW_DEPENDENCY_STATUSES)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE resumes r
                SET deleted_at = CURRENT_TIMESTAMP,
                    is_default = 0,
                    default_key = NULL,
                    original_file_path = '',
                    structured_data = JSON_OBJECT(),
                    content_hash = NULL
                WHERE r.id = %s
                  AND r.user_id = %s
                  AND r.deleted_at IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM interviews i
                      WHERE i.resume_id = r.id
                        AND i.user_id = r.user_id
                        AND (
                            i.status IN ({status_placeholders})
                            OR i.overall_status IN ({status_placeholders})
                        )
                  )
                """,
                (
                    resume_id,
                    user_id,
                    *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
                    *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
                ),
            )
            return int(cursor.rowcount) > 0

    def get_original_file_path_for_user(self, resume_id: int, user_id: int) -> str | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT original_file_path FROM resumes "
                "WHERE id = %s AND user_id = %s AND deleted_at IS NULL",
                (resume_id, user_id),
            )
            row = cursor.fetchone()
        return str(row["original_file_path"]) if row is not None else None

    def has_unfinished_interview_for_resume(self, resume_id: int, user_id: int) -> bool:
        return self.has_active_interview_dependency_for_resume(resume_id, user_id)

    def has_active_interview_dependency_for_resume(
        self,
        resume_id: int,
        user_id: int,
    ) -> bool:
        status_placeholders = _placeholders(ACTIVE_INTERVIEW_DEPENDENCY_STATUSES)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT 1
                FROM interviews
                WHERE resume_id = %s
                  AND user_id = %s
                  AND (
                      status IN ({status_placeholders})
                      OR overall_status IN ({status_placeholders})
                  )
                LIMIT 1
                """,
                (
                    resume_id,
                    user_id,
                    *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
                    *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
                ),
            )
            return cursor.fetchone() is not None

    def create_parse_task(
        self,
        *,
        user_id: int,
        original_file_path: str,
        content_hash: str,
    ) -> ResumeParseTaskRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO resume_parse_tasks (user_id, original_file_path, content_hash)
                VALUES (%s, %s, %s)
                """,
                (user_id, original_file_path, content_hash),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_parse_task_for_user(task_id, user_id)
        if task is None:
            raise RuntimeError("created resume parse task is missing")
        return task

    def get_or_create_completed_parse_task(
        self,
        *,
        user_id: int,
        original_file_path: str,
        content_hash: str,
        resume_id: int,
    ) -> ResumeParseTaskRecord:
        with self.connection.cursor() as cursor:
            self._lock_user_resumes(cursor, user_id)
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, content_hash, status, resume_id,
                       error_message, created_at, started_at, completed_at,
                       processing_token, heartbeat_at
                FROM resume_parse_tasks
                WHERE user_id = %s
                  AND content_hash = %s
                  AND resume_id = %s
                  AND status = 'completed'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (user_id, content_hash, resume_id),
            )
            row = cursor.fetchone()
            if row is not None:
                return _to_parse_task(row)

            cursor.execute(
                """
                INSERT INTO resume_parse_tasks (
                    user_id, original_file_path, content_hash, status, resume_id, completed_at
                )
                VALUES (%s, %s, %s, 'completed', %s, UTC_TIMESTAMP())
                """,
                (user_id, original_file_path, content_hash, resume_id),
            )
            task_id = int(cursor.lastrowid)

        task = self.get_parse_task_for_user(task_id, user_id)
        if task is None:
            raise RuntimeError("created completed resume parse task is missing")
        return task

    def get_parse_task_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> ResumeParseTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, content_hash, status, resume_id,
                       error_message, created_at, started_at, completed_at,
                       processing_token, heartbeat_at
                FROM resume_parse_tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user_id),
            )
            row = cursor.fetchone()
        return _to_parse_task(row) if row is not None else None

    def get_active_parse_task_by_content_hash(
        self,
        user_id: int,
        content_hash: str,
    ) -> ResumeParseTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, content_hash, status, resume_id,
                       error_message, created_at, started_at, completed_at,
                       processing_token, heartbeat_at
                FROM resume_parse_tasks
                WHERE user_id = %s
                  AND content_hash = %s
                  AND status IN ('pending', 'processing')
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (user_id, content_hash),
            )
            row = cursor.fetchone()
        return _to_parse_task(row) if row is not None else None

    def get_parse_task(self, task_id: int) -> ResumeParseTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, content_hash, status, resume_id,
                       error_message, created_at, started_at, completed_at,
                       processing_token, heartbeat_at
                FROM resume_parse_tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()
        return _to_parse_task(row) if row is not None else None

    def claim_due_parse_task(
        self,
        processing_timeout_seconds: int,
    ) -> ResumeParseTaskRecord | None:
        timeout_seconds = max(1, processing_timeout_seconds)
        processing_token = uuid4().hex
        self.fail_stale_parse_tasks(timeout_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET id = LAST_INSERT_ID(id),
                    status = 'processing',
                    started_at = UTC_TIMESTAMP(),
                    processing_token = %s,
                    heartbeat_at = UTC_TIMESTAMP(),
                    completed_at = NULL,
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
        return self.get_parse_task(task_id)

    def fail_stale_parse_tasks(self, processing_timeout_seconds: int) -> list[str]:
        timeout_seconds = max(1, processing_timeout_seconds)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT original_file_path
                FROM resume_parse_tasks
                WHERE status = 'processing'
                  AND (
                      COALESCE(heartbeat_at, started_at) IS NULL
                      OR COALESCE(heartbeat_at, started_at) <= DATE_SUB(
                          UTC_TIMESTAMP(), INTERVAL %s SECOND
                      )
                  )
                FOR UPDATE
                """,
                (timeout_seconds,),
            )
            paths = [str(row["original_file_path"]) for row in cursor.fetchall()]
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'failed',
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
        return paths

    def enqueue_file_cleanup(
        self,
        original_file_path: str,
        *,
        max_retries: int = 20,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO file_cleanup_tasks (
                    original_file_path, status, max_retries
                )
                VALUES (%s, 'pending', %s)
                ON DUPLICATE KEY UPDATE
                    status = 'pending',
                    attempt_count = 0,
                    max_retries = VALUES(max_retries),
                    processing_token = NULL,
                    next_retry_at = NULL,
                    completed_at = NULL,
                    error_message = NULL
                """,
                (original_file_path, max(1, max_retries)),
            )

    def claim_due_file_cleanup(
        self,
        processing_timeout_seconds: int = 900,
    ) -> FileCleanupTaskRecord | None:
        timeout_seconds = max(1, processing_timeout_seconds)
        processing_token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE file_cleanup_tasks
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
                (processing_token, timeout_seconds),
            )
            if int(cursor.rowcount) != 1:
                return None
            cursor.execute("SELECT LAST_INSERT_ID() AS task_id")
            row = cursor.fetchone()
            if row is None:
                return None
            task_id = int(row["task_id"])
            cursor.execute(
                """
                SELECT id, original_file_path, status, attempt_count,
                       max_retries, processing_token
                FROM file_cleanup_tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            task_row = cursor.fetchone()
        return _to_file_cleanup_task(task_row)

    def complete_file_cleanup(self, task_id: int, processing_token: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE file_cleanup_tasks
                SET status = 'completed',
                    completed_at = UTC_TIMESTAMP(),
                    processing_token = NULL,
                    next_retry_at = NULL,
                    error_message = NULL
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                """,
                (task_id, processing_token),
            )
            return int(cursor.rowcount) > 0

    def retry_file_cleanup(
        self,
        task: FileCleanupTaskRecord,
        error_message: str,
    ) -> bool:
        exhausted = task.attempt_count >= task.max_retries
        retry_delay_seconds = min(3600, (2 ** min(task.attempt_count, 10)) * 5)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE file_cleanup_tasks
                SET status = %s,
                    next_retry_at = CASE
                        WHEN %s THEN NULL
                        ELSE DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND)
                    END,
                    completed_at = CASE WHEN %s THEN UTC_TIMESTAMP() ELSE NULL END,
                    processing_token = NULL,
                    error_message = %s
                WHERE id = %s AND status = 'processing' AND processing_token = %s
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
            return int(cursor.rowcount) > 0

    def mark_parse_task_processing(self, task_id: int) -> bool:
        processing_token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'processing',
                    started_at = UTC_TIMESTAMP(),
                    processing_token = %s,
                    heartbeat_at = UTC_TIMESTAMP(),
                    completed_at = NULL,
                    error_message = NULL
                WHERE id = %s AND status = 'pending'
                """,
                (processing_token, task_id),
            )
            return int(cursor.rowcount) > 0

    def heartbeat_parse_task(self, task_id: int, processing_token: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET heartbeat_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (task_id, processing_token),
            )
            return int(cursor.rowcount) > 0

    def complete_parse_task(
        self,
        task_id: int,
        processing_token: str,
        structured_data: dict[str, Any],
    ) -> ResumeRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id, original_file_path, content_hash
                FROM resume_parse_tasks
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                FOR UPDATE
                """,
                (task_id, processing_token),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        resume = self.create(
            user_id=int(row["user_id"]),
            original_file_path=str(row["original_file_path"]),
            structured_data=structured_data,
            content_hash=str(row["content_hash"]),
        )
        if not self.mark_parse_task_completed(task_id, resume.id, processing_token):
            raise RuntimeError("resume parse task lease was lost during completion")
        return resume

    def mark_parse_task_completed(
        self,
        task_id: int,
        resume_id: int,
        processing_token: str,
    ) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'completed',
                    resume_id = %s,
                    error_message = NULL,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (resume_id, task_id, processing_token),
            )
            return int(cursor.rowcount) > 0

    def mark_parse_task_failed(
        self,
        task_id: int,
        error_message: str,
        processing_token: str,
    ) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'failed',
                    error_message = %s,
                    processing_token = NULL,
                    heartbeat_at = NULL,
                    completed_at = UTC_TIMESTAMP()
                WHERE id = %s
                  AND status = 'processing'
                  AND processing_token = %s
                """,
                (error_message[:1000], task_id, processing_token),
            )
            return int(cursor.rowcount) > 0

    def _lock_user_resumes(self, cursor: Any, user_id: int) -> None:
        cursor.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))

    def _has_active_resume_with_cursor(self, cursor: Any, user_id: int) -> bool:
        cursor.execute(
            "SELECT 1 FROM resumes WHERE user_id = %s AND deleted_at IS NULL LIMIT 1",
            (user_id,),
        )
        return cursor.fetchone() is not None


def _to_resume(row: dict[str, Any]) -> ResumeRecord:
    structured_data = row["structured_data"]
    if isinstance(structured_data, str):
        structured_data = json.loads(structured_data)
    return ResumeRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        original_file_path=str(row["original_file_path"]),
        structured_data=dict(structured_data),
        content_hash=str(row["content_hash"]) if row.get("content_hash") is not None else None,
        display_name=str(row["display_name"]) if row.get("display_name") is not None else None,
        is_default=bool(row.get("is_default")),
        created_at=row.get("created_at"),
        deleted_at=row.get("deleted_at"),
    )


def _to_summary(row: dict[str, Any]) -> ResumeSummaryRecord:
    return ResumeSummaryRecord(
        id=int(row["id"]),
        name=_resume_name(row),
        uploaded_at=row["uploaded_at"],
        last_used_at=row.get("last_used_at"),
        parse_status="parsed",
        is_default=bool(row.get("is_default")),
    )


def _to_detail(row: dict[str, Any]) -> ResumeDetailRecord:
    structured_data = row["structured_data"]
    if isinstance(structured_data, str):
        structured_data = json.loads(structured_data)
    return ResumeDetailRecord(
        id=int(row["id"]),
        name=_resume_name(row),
        uploaded_at=row["uploaded_at"],
        last_used_at=row.get("last_used_at"),
        parse_status="parsed",
        structured_data=dict(structured_data),
        is_default=bool(row.get("is_default")),
    )


def _to_parse_task(row: dict[str, Any]) -> ResumeParseTaskRecord:
    return ResumeParseTaskRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        original_file_path=str(row["original_file_path"]),
        content_hash=str(row["content_hash"]),
        status=str(row["status"]),
        resume_id=int(row["resume_id"]) if row.get("resume_id") is not None else None,
        error_message=str(row["error_message"]) if row.get("error_message") is not None else None,
        created_at=row.get("created_at"),
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        processing_token=row.get("processing_token"),
        heartbeat_at=row.get("heartbeat_at"),
    )


def _to_file_cleanup_task(
    row: dict[str, Any] | None,
) -> FileCleanupTaskRecord | None:
    if row is None:
        return None
    return FileCleanupTaskRecord(
        id=int(row["id"]),
        original_file_path=str(row["original_file_path"]),
        status=str(row["status"]),
        attempt_count=int(row.get("attempt_count") or 0),
        max_retries=int(row.get("max_retries") or 1),
        processing_token=row.get("processing_token"),
    )


def _resume_name(row: dict[str, Any]) -> str:
    display_name = str(row["display_name"]).strip() if row.get("display_name") is not None else ""
    return display_name or Path(str(row["original_file_path"])).name


ACTIVE_DEFAULT_KEY = "active"


def _default_key(is_default: bool) -> str | None:
    return ACTIVE_DEFAULT_KEY if is_default else None


def _bool_int(value: bool) -> int:
    return 1 if value else 0


def _placeholders(values: tuple[str, ...]) -> str:
    return ", ".join(["%s"] * len(values))
