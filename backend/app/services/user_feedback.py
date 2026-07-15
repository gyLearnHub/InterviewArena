from typing import Protocol, cast

from fastapi import status

from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.repositories.user_feedback import (
    QuestionFeedbackContext,
    UserFeedbackSubmissionRecord,
)
from app.repositories.users import UserRecord
from app.schemas.user_feedback import (
    FeedbackType,
    UserFeedbackSubmissionCreate,
    UserFeedbackSubmissionResponse,
)


class UserFeedbackRepositoryProtocol(Protocol):
    def create_submission(
        self,
        *,
        user_id: int,
        feedback_type: str,
        content: str,
        rating: int | None,
        interview_id: int | None,
        round_id: int | None,
        question_id: int | None,
    ) -> UserFeedbackSubmissionRecord:
        ...

    def get_interview_owner_id(self, interview_id: int) -> int | None:
        ...

    def get_interview_id_by_round(self, round_id: int, user_id: int) -> int | None:
        ...

    def get_question_context(
        self,
        question_id: int,
        user_id: int,
    ) -> QuestionFeedbackContext | None:
        ...


class UserFeedbackService:
    def __init__(self, repository: UserFeedbackRepositoryProtocol) -> None:
        self.repository = repository

    def submit_feedback(
        self,
        current_user: UserRecord,
        request: UserFeedbackSubmissionCreate,
    ) -> UserFeedbackSubmissionResponse:
        interview_id, round_id, question_id = self._resolve_related_context(
            current_user.id,
            request,
        )
        record = self.repository.create_submission(
            user_id=current_user.id,
            feedback_type=request.feedback_type,
            content=request.content,
            rating=request.rating,
            interview_id=interview_id,
            round_id=round_id,
            question_id=question_id,
        )
        return _to_response(record)

    def _resolve_related_context(
        self,
        user_id: int,
        request: UserFeedbackSubmissionCreate,
    ) -> tuple[int | None, int | None, int | None]:
        interview_id = request.interview_id
        round_id = request.round_id
        question_id = request.question_id

        if (
            interview_id is not None
            and self.repository.get_interview_owner_id(interview_id) != user_id
        ):
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)

        if round_id is not None:
            round_interview_id = self.repository.get_interview_id_by_round(round_id, user_id)
            if round_interview_id is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
            interview_id = _merge_interview_id(interview_id, round_interview_id)

        if question_id is not None:
            question_context = self.repository.get_question_context(question_id, user_id)
            if question_context is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
            interview_id = _merge_interview_id(interview_id, question_context.interview_id)
            if round_id is None:
                round_id = question_context.round_id
            elif question_context.round_id is not None and round_id != question_context.round_id:
                raise _related_context_error()

        return interview_id, round_id, question_id


def _merge_interview_id(current_id: int | None, resolved_id: int) -> int:
    if current_id is not None and current_id != resolved_id:
        raise _related_context_error()
    return resolved_id


def _related_context_error() -> AppError:
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        HTTP_422_UNPROCESSABLE_CONTENT,
        message="关联的面试、轮次和题目不一致。",
    )


def _to_response(record: UserFeedbackSubmissionRecord) -> UserFeedbackSubmissionResponse:
    return UserFeedbackSubmissionResponse(
        id=record.id,
        feedback_type=cast(FeedbackType, record.feedback_type),
        content=record.content,
        rating=record.rating,
        interview_id=record.interview_id,
        round_id=record.round_id,
        question_id=record.question_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
