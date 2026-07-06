from datetime import datetime, timedelta

import pytest
from app.api.notifications import list_notifications as api_list_notifications
from app.core.errors import AppError, ErrorCode
from app.repositories.notifications import NotificationRecord
from app.repositories.users import UserRecord
from app.schemas.notification import NotificationListResponse
from app.services.notifications import NotificationService


class FakeNotificationRepository:
    def __init__(self, records: list[NotificationRecord]) -> None:
        self.records = records
        self.interview_owners = {10: 1, 20: 2}
        self.round_interviews = {101: 10}
        self.question_interviews = {201: 10}
        self.feedback_reports = {10}

    def list_by_user(
        self,
        user_id: int,
        *,
        unread_only: bool,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: int | None = None,
    ) -> list[NotificationRecord]:
        records = [record for record in self.records if record.user_id == user_id]
        if unread_only:
            records = [record for record in records if not record.is_read]
        if cursor_created_at is not None and cursor_id is not None:
            records = [
                record
                for record in records
                if (record.created_at, record.id) < (cursor_created_at, cursor_id)
            ]
        return sorted(
            records,
            key=lambda record: (record.created_at, record.id),
            reverse=True,
        )[:limit]

    def count_unread(self, user_id: int) -> int:
        return len(
            [
                record
                for record in self.records
                if record.user_id == user_id and not record.is_read
            ]
        )

    def get_by_id_for_user(self, notification_id: int, user_id: int) -> NotificationRecord | None:
        return next(
            (
                record
                for record in self.records
                if record.id == notification_id and record.user_id == user_id
            ),
            None,
        )

    def mark_read(self, notification_id: int, user_id: int) -> bool:
        for index, record in enumerate(self.records):
            if record.id == notification_id and record.user_id == user_id:
                self.records[index] = NotificationRecord(
                    **{
                        **record.__dict__,
                        "is_read": True,
                        "read_at": record.read_at or datetime(2026, 6, 22, 12, 0, 0),
                    }
                )
                return True
        return False

    def mark_all_read(self, user_id: int) -> int:
        changed = 0
        for index, record in enumerate(self.records):
            if record.user_id == user_id and not record.is_read:
                self.records[index] = NotificationRecord(**{**record.__dict__, "is_read": True})
                changed += 1
        return changed

    def get_interview_owner_id(self, interview_id: int) -> int | None:
        return self.interview_owners.get(interview_id)

    def get_interview_id_by_round(self, round_id: int, user_id: int) -> int | None:
        interview_id = self.round_interviews.get(round_id)
        if interview_id is None or self.interview_owners.get(interview_id) != user_id:
            return None
        return interview_id

    def get_interview_id_by_question(self, question_id: int, user_id: int) -> int | None:
        interview_id = self.question_interviews.get(question_id)
        if interview_id is None or self.interview_owners.get(interview_id) != user_id:
            return None
        return interview_id

    def feedback_report_exists(self, interview_id: int, user_id: int) -> bool:
        return (
            interview_id in self.feedback_reports
            and self.interview_owners.get(interview_id) == user_id
        )


def test_list_notifications_filters_current_user_and_returns_cursor() -> None:
    service = NotificationService(
        FakeNotificationRepository(
            [
                _record(1, 1, minutes=3),
                _record(2, 1, minutes=2),
                _record(3, 1, minutes=1),
                _record(4, 2, minutes=4),
            ]
        )
    )

    response = service.list_notifications(_user(1), limit=2)

    assert [item.id for item in response.items] == [1, 2]
    assert response.next_cursor is not None
    assert response.unread_count == 3


def test_unread_filter_only_returns_unread_items() -> None:
    service = NotificationService(
        FakeNotificationRepository([_record(1, 1, is_read=True), _record(2, 1)])
    )

    response = service.list_notifications(_user(1), unread_only=True)

    assert [item.id for item in response.items] == [2]


def test_mark_read_rejects_other_users_notification() -> None:
    service = NotificationService(FakeNotificationRepository([_record(1, 2)]))

    with pytest.raises(AppError) as error_info:
        service.mark_read(1, _user(1))

    assert error_info.value.code == ErrorCode.NOT_FOUND
    assert error_info.value.status_code == 404


def test_mark_all_read_only_updates_current_user() -> None:
    repository = FakeNotificationRepository([_record(1, 1), _record(2, 2)])
    service = NotificationService(repository)

    service.mark_all_read(_user(1))

    assert repository.get_by_id_for_user(1, 1).is_read is True  # type: ignore[union-attr]
    assert repository.get_by_id_for_user(2, 2).is_read is False  # type: ignore[union-attr]


def test_detail_resolves_report_target() -> None:
    service = NotificationService(
        FakeNotificationRepository(
            [_record(1, 1, notification_type="score_report", interview_id=10)]
        )
    )

    response = service.get_detail(1, _user(1))

    assert response.target.exists is True
    assert response.target.path == "/reports/10"


def test_detail_reports_deleted_related_content() -> None:
    service = NotificationService(
        FakeNotificationRepository([_record(1, 1, interview_id=99)])
    )

    response = service.get_detail(1, _user(1))

    assert response.target.exists is False
    assert response.target.message == "关联内容不存在或已被删除。"


def test_api_list_notifications_passes_filter_and_current_user() -> None:
    class FakeNotificationService:
        def __init__(self) -> None:
            self.calls: list[tuple[int, bool, str | None, int]] = []

        def list_notifications(
            self,
            current_user: UserRecord,
            *,
            unread_only: bool = False,
            cursor: str | None = None,
            limit: int = 10,
        ) -> NotificationListResponse:
            self.calls.append((current_user.id, unread_only, cursor, limit))
            return NotificationListResponse(items=[], next_cursor=None, unread_count=0)

    service = FakeNotificationService()

    response = api_list_notifications(
        filter="unread",
        cursor="2026-06-22T10:00:00|1",
        limit=10,
        current_user=_user(7),
        service=service,  # type: ignore[arg-type]
    )

    assert response.unread_count == 0
    assert service.calls == [(7, True, "2026-06-22T10:00:00|1", 10)]


def _user(user_id: int) -> UserRecord:
    return UserRecord(id=user_id, username=f"user-{user_id}", password_hash="hash")


def _record(
    notification_id: int,
    user_id: int,
    *,
    minutes: int = 0,
    is_read: bool = False,
    notification_type: str = "system",
    interview_id: int | None = None,
) -> NotificationRecord:
    return NotificationRecord(
        id=notification_id,
        user_id=user_id,
        title=f"通知 {notification_id}",
        content=f"完整内容 {notification_id}",
        summary=f"摘要 {notification_id}",
        notification_type=notification_type,
        is_read=is_read,
        related_type=None,
        related_id=None,
        interview_id=interview_id,
        round_id=None,
        question_id=None,
        created_at=datetime(2026, 6, 22, 10, 0, 0) + timedelta(minutes=minutes),
        read_at=None,
    )
