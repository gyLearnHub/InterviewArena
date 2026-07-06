from datetime import datetime

from pydantic import BaseModel, Field


class NotificationTarget(BaseModel):
    exists: bool | None = None
    path: str | None = None
    message: str | None = None


class NotificationItem(BaseModel):
    id: int
    title: str
    summary: str
    notification_type: str
    is_read: bool
    related_type: str | None = None
    related_id: int | None = None
    interview_id: int | None = None
    round_id: int | None = None
    question_id: int | None = None
    created_at: datetime


class NotificationDetail(NotificationItem):
    content: str
    target: NotificationTarget = Field(default_factory=NotificationTarget)


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    next_cursor: str | None = None
    unread_count: int


class NotificationUnreadCountResponse(BaseModel):
    count: int
