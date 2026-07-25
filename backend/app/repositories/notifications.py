from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NotificationRecord:
    id: int
    user_id: int
    title: str
    content: str
    summary: str
    notification_type: str
    is_read: bool
    related_type: str | None
    related_id: int | None
    interview_id: int | None
    round_id: int | None
    question_id: int | None
    created_at: datetime
    read_at: datetime | None


class NotificationRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def list_by_user(
        self,
        user_id: int,
        *,
        unread_only: bool,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: int | None = None,
    ) -> list[NotificationRecord]:
        clauses = ["user_id = %s"]
        params: list[Any] = [user_id]
        if unread_only:
            clauses.append("is_read = 0")
        if cursor_created_at is not None and cursor_id is not None:
            clauses.append("(created_at < %s OR (created_at = %s AND id < %s))")
            params.extend([cursor_created_at, cursor_created_at, cursor_id])
        params.append(limit)

        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_id, title, content, summary, notification_type, is_read,
                       related_type, related_id, interview_id, round_id, question_id,
                       created_at, read_at
                FROM notifications
                WHERE {" AND ".join(clauses)}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_record(row) for row in rows]

    def count_unread(self, user_id: int) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM notifications WHERE user_id = %s AND is_read = 0",
                (user_id,),
            )
            row = cursor.fetchone()
        return int(row["count"])

    def get_by_id_for_user(self, notification_id: int, user_id: int) -> NotificationRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, title, content, summary, notification_type, is_read,
                       related_type, related_id, interview_id, round_id, question_id,
                       created_at, read_at
                FROM notifications
                WHERE id = %s AND user_id = %s
                """,
                (notification_id, user_id),
            )
            row = cursor.fetchone()
        return _to_record(row) if row is not None else None

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notifications
                SET is_read = 1, read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
                WHERE id = %s AND user_id = %s
                """,
                (notification_id, user_id),
            )
            if int(cursor.rowcount) > 0:
                return True
            cursor.execute(
                "SELECT 1 FROM notifications WHERE id = %s AND user_id = %s",
                (notification_id, user_id),
            )
            return cursor.fetchone() is not None

    def mark_all_read(self, user_id: int) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notifications
                SET is_read = 1, read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
                WHERE user_id = %s AND is_read = 0
                """,
                (user_id,),
            )
            return int(cursor.rowcount)

    def get_interview_owner_id(self, interview_id: int) -> int | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM interviews WHERE id = %s", (interview_id,))
            row = cursor.fetchone()
        return int(row["user_id"]) if row is not None else None

    def get_interview_id_by_round(self, round_id: int, user_id: int) -> int | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ir.interview_id
                FROM interview_rounds ir
                JOIN interviews i ON i.id = ir.interview_id
                WHERE ir.id = %s AND i.user_id = %s
                """,
                (round_id, user_id),
            )
            row = cursor.fetchone()
        return int(row["interview_id"]) if row is not None else None

    def get_interview_id_by_question(self, question_id: int, user_id: int) -> int | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT qa.interview_id
                FROM interview_qa qa
                JOIN interviews i ON i.id = qa.interview_id
                WHERE qa.id = %s AND i.user_id = %s
                """,
                (question_id, user_id),
            )
            row = cursor.fetchone()
        return int(row["interview_id"]) if row is not None else None

    def feedback_report_exists(self, interview_id: int, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fr.id
                FROM feedback_reports fr
                JOIN interviews i ON i.id = fr.interview_id
                WHERE fr.interview_id = %s AND i.user_id = %s
                """,
                (interview_id, user_id),
            )
            row = cursor.fetchone()
        return row is not None


def _to_record(row: dict[str, Any]) -> NotificationRecord:
    return NotificationRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        title=str(row["title"]),
        content=str(row["content"]),
        summary=str(row["summary"]),
        notification_type=str(row["notification_type"]),
        is_read=bool(row["is_read"]),
        related_type=str(row["related_type"]) if row.get("related_type") is not None else None,
        related_id=int(row["related_id"]) if row.get("related_id") is not None else None,
        interview_id=int(row["interview_id"]) if row.get("interview_id") is not None else None,
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        question_id=int(row["question_id"]) if row.get("question_id") is not None else None,
        created_at=row["created_at"],
        read_at=row.get("read_at"),
    )
