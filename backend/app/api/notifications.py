from typing import Any

from fastapi import APIRouter, Depends, Query
from starlette.status import HTTP_204_NO_CONTENT

from app.deps import DatabaseConnectionDep, get_current_user
from app.repositories.notifications import NotificationRepository
from app.repositories.users import UserRecord
from app.schemas.notification import (
    NotificationDetail,
    NotificationListResponse,
    NotificationUnreadCountResponse,
)
from app.services.notifications import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_repository(
    connection: Any = DatabaseConnectionDep,
) -> NotificationRepository:
    return NotificationRepository(connection)


NotificationRepositoryDep = Depends(get_notification_repository)
CurrentUserDep = Depends(get_current_user)


def get_notification_service(
    repository: NotificationRepository = NotificationRepositoryDep,
) -> NotificationService:
    return NotificationService(repository)


NotificationServiceDep = Depends(get_notification_service)


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    filter: str = Query(default="all", pattern="^(all|unread)$"),
    cursor: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: UserRecord = CurrentUserDep,
    service: NotificationService = NotificationServiceDep,
) -> NotificationListResponse:
    return service.list_notifications(
        current_user,
        unread_only=filter == "unread",
        cursor=cursor,
        limit=limit,
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def unread_count(
    current_user: UserRecord = CurrentUserDep,
    service: NotificationService = NotificationServiceDep,
) -> NotificationUnreadCountResponse:
    return service.unread_count(current_user)


@router.get("/{notification_id}", response_model=NotificationDetail)
def get_notification_detail(
    notification_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: NotificationService = NotificationServiceDep,
) -> NotificationDetail:
    return service.get_detail(notification_id, current_user)


@router.post("/{notification_id}/read", status_code=HTTP_204_NO_CONTENT)
def mark_notification_read(
    notification_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: NotificationService = NotificationServiceDep,
) -> None:
    service.mark_read(notification_id, current_user)


@router.post("/read-all", status_code=HTTP_204_NO_CONTENT)
def mark_all_notifications_read(
    current_user: UserRecord = CurrentUserDep,
    service: NotificationService = NotificationServiceDep,
) -> None:
    service.mark_all_read(current_user)
