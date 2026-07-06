from datetime import datetime
from typing import Protocol

from fastapi import status

from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.repositories.notifications import NotificationRecord
from app.repositories.users import UserRecord
from app.schemas.notification import (
    NotificationDetail,
    NotificationItem,
    NotificationListResponse,
    NotificationTarget,
    NotificationUnreadCountResponse,
)

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


class NotificationRepositoryProtocol(Protocol):
    def list_by_user(
        self,
        user_id: int,
        *,
        unread_only: bool,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: int | None = None,
    ) -> list[NotificationRecord]:
        ...

    def count_unread(self, user_id: int) -> int:
        ...

    def get_by_id_for_user(self, notification_id: int, user_id: int) -> NotificationRecord | None:
        ...

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        ...

    def mark_all_read(self, user_id: int) -> int:
        ...

    def get_interview_owner_id(self, interview_id: int) -> int | None:
        ...

    def get_interview_id_by_round(self, round_id: int, user_id: int) -> int | None:
        ...

    def get_interview_id_by_question(self, question_id: int, user_id: int) -> int | None:
        ...

    def feedback_report_exists(self, interview_id: int, user_id: int) -> bool:
        ...


class NotificationService:
    def __init__(self, repository: NotificationRepositoryProtocol) -> None:
        self.repository = repository

    def list_notifications(
        self,
        current_user: UserRecord,
        *,
        unread_only: bool = False,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> NotificationListResponse:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        page_size = max(1, min(limit, MAX_PAGE_SIZE))
        records = self.repository.list_by_user(
            current_user.id,
            unread_only=unread_only,
            limit=page_size + 1,
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
        )
        visible_records = records[:page_size]
        next_cursor = _encode_cursor(visible_records[-1]) if len(records) > page_size else None
        return NotificationListResponse(
            items=[_to_item(record) for record in visible_records],
            next_cursor=next_cursor,
            unread_count=self.repository.count_unread(current_user.id),
        )

    def unread_count(self, current_user: UserRecord) -> NotificationUnreadCountResponse:
        return NotificationUnreadCountResponse(count=self.repository.count_unread(current_user.id))

    def get_detail(self, notification_id: int, current_user: UserRecord) -> NotificationDetail:
        record = self.repository.get_by_id_for_user(notification_id, current_user.id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        return NotificationDetail(
            **_to_item(record).model_dump(),
            content=record.content,
            target=self.resolve_target(record),
        )

    def mark_read(self, notification_id: int, current_user: UserRecord) -> None:
        if not self.repository.mark_read(notification_id, current_user.id):
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)

    def mark_all_read(self, current_user: UserRecord) -> None:
        self.repository.mark_all_read(current_user.id)

    def resolve_target(self, record: NotificationRecord) -> NotificationTarget:
        interview_id = self._resolve_interview_id(record)
        if interview_id is None:
            if _has_related_reference(record):
                return NotificationTarget(
                    exists=False,
                    message="关联内容不存在或已被删除。",
                )
            return NotificationTarget(exists=None)

        target_kind = (record.related_type or record.notification_type).lower()
        report_target_kinds = {
            "report",
            "score_report",
            "scoring_report",
            "feedback_report",
            "评分报告",
        }
        if target_kind in report_target_kinds:
            if not self.repository.feedback_report_exists(interview_id, record.user_id):
                return NotificationTarget(exists=False, message="关联内容不存在或已被删除。")
            return NotificationTarget(exists=True, path=f"/reports/{interview_id}")
        if target_kind in {"harness", "harness_exception", "harness_error", "异常"}:
            return NotificationTarget(exists=True, path=f"/harness?interview_id={interview_id}")
        return NotificationTarget(exists=True, path=f"/history/{interview_id}")

    def _resolve_interview_id(self, record: NotificationRecord) -> int | None:
        if record.question_id is not None:
            return self.repository.get_interview_id_by_question(record.question_id, record.user_id)
        if record.round_id is not None:
            return self.repository.get_interview_id_by_round(record.round_id, record.user_id)
        if record.interview_id is not None:
            owner_id = self.repository.get_interview_owner_id(record.interview_id)
            return record.interview_id if owner_id == record.user_id else None
        if record.related_type and record.related_id is not None:
            related_type = record.related_type.lower()
            if related_type in {"interview", "report", "feedback_report", "harness"}:
                owner_id = self.repository.get_interview_owner_id(record.related_id)
                return record.related_id if owner_id == record.user_id else None
            if related_type == "round":
                return self.repository.get_interview_id_by_round(record.related_id, record.user_id)
            if related_type in {"question", "qa"}:
                return self.repository.get_interview_id_by_question(
                    record.related_id,
                    record.user_id,
                )
        return None


def _to_item(record: NotificationRecord) -> NotificationItem:
    return NotificationItem(
        id=record.id,
        title=record.title,
        summary=record.summary,
        notification_type=record.notification_type,
        is_read=record.is_read,
        related_type=record.related_type,
        related_id=record.related_id,
        interview_id=record.interview_id,
        round_id=record.round_id,
        question_id=record.question_id,
        created_at=record.created_at,
    )


def _has_related_reference(record: NotificationRecord) -> bool:
    return any(
        value is not None
        for value in (
            record.related_id,
            record.interview_id,
            record.round_id,
            record.question_id,
        )
    )


def _encode_cursor(record: NotificationRecord) -> str:
    return f"{record.created_at.isoformat()}|{record.id}"


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
    if not cursor:
        return None, None
    created_at_text, separator, id_text = cursor.partition("|")
    if not separator:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    try:
        return datetime.fromisoformat(created_at_text), int(id_text)
    except ValueError as exc:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT) from exc
