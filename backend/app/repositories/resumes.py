import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


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


class ResumeRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

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
                WHERE user_id = %s AND content_hash = %s
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
            updated = int(cursor.rowcount) > 0
        if not updated:
            return None
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
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resumes
                SET deleted_at = CURRENT_TIMESTAMP, is_default = 0, default_key = NULL
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (resume_id, user_id),
            )
            return int(cursor.rowcount) > 0

    def restore_for_user(self, resume_id: int, user_id: int) -> ResumeRecord | None:
        with self.connection.cursor() as cursor:
            self._lock_user_resumes(cursor, user_id)
            is_default = not self._has_active_resume_with_cursor(cursor, user_id)
            cursor.execute(
                """
                UPDATE resumes
                SET deleted_at = NULL, is_default = %s, default_key = %s
                WHERE id = %s AND user_id = %s
                """,
                (_bool_int(is_default), _default_key(is_default), resume_id, user_id),
            )
            updated = int(cursor.rowcount) > 0
        if not updated:
            return None
        return self.get_by_id_for_user(resume_id, user_id)

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

    def get_parse_task_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> ResumeParseTaskRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, original_file_path, content_hash, status, resume_id,
                       error_message, created_at, started_at, completed_at
                FROM resume_parse_tasks
                WHERE id = %s AND user_id = %s
                """,
                (task_id, user_id),
            )
            row = cursor.fetchone()
        return _to_parse_task(row) if row is not None else None

    def mark_parse_task_processing(self, task_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'pending'
                """,
                (task_id,),
            )
            return int(cursor.rowcount) > 0

    def mark_parse_task_completed(self, task_id: int, resume_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'completed', resume_id = %s, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (resume_id, task_id),
            )

    def mark_parse_task_failed(self, task_id: int, error_message: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE resume_parse_tasks
                SET status = 'failed', error_message = %s, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (error_message[:1000], task_id),
            )

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
    )


def _resume_name(row: dict[str, Any]) -> str:
    display_name = str(row["display_name"]).strip() if row.get("display_name") is not None else ""
    return display_name or Path(str(row["original_file_path"])).name


ACTIVE_DEFAULT_KEY = "active"


def _default_key(is_default: bool) -> str | None:
    return ACTIVE_DEFAULT_KEY if is_default else None


def _bool_int(value: bool) -> int:
    return 1 if value else 0
