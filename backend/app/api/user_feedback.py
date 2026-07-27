from typing import Any

from fastapi import APIRouter, Depends, status

from app.deps import DatabaseConnectionDep, get_current_user
from app.repositories.user_feedback import UserFeedbackRepository
from app.repositories.users import UserRecord
from app.schemas.user_feedback import (
    UserFeedbackSubmissionCreate,
    UserFeedbackSubmissionResponse,
)
from app.services.user_feedback import UserFeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


def get_user_feedback_repository(
    connection: Any = DatabaseConnectionDep,
) -> UserFeedbackRepository:
    return UserFeedbackRepository(connection)


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
