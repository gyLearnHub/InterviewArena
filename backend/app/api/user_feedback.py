from collections.abc import Iterator

from fastapi import APIRouter, Depends, status

from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.user_feedback import UserFeedbackRepository
from app.repositories.users import UserRecord
from app.schemas.user_feedback import (
    UserFeedbackSubmissionCreate,
    UserFeedbackSubmissionResponse,
)
from app.services.user_feedback import UserFeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


def get_user_feedback_repository() -> Iterator[UserFeedbackRepository]:
    with mysql_connection() as connection:
        yield UserFeedbackRepository(connection)


UserFeedbackRepositoryDep = Depends(get_user_feedback_repository)
CurrentUserDep = Depends(get_current_user)


def get_user_feedback_service(
    repository: UserFeedbackRepository = UserFeedbackRepositoryDep,
) -> UserFeedbackService:
    return UserFeedbackService(repository)


UserFeedbackServiceDep = Depends(get_user_feedback_service)


@router.post(
    "",
    response_model=UserFeedbackSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    payload: UserFeedbackSubmissionCreate,
    current_user: UserRecord = CurrentUserDep,
    service: UserFeedbackService = UserFeedbackServiceDep,
) -> UserFeedbackSubmissionResponse:
    return service.submit_feedback(current_user, payload)
