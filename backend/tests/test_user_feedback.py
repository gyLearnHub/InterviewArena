from datetime import datetime

import pytest
from app.api.user_feedback import submit_feedback as api_submit_feedback
from app.core.errors import AppError, ErrorCode
from app.repositories.user_feedback import (
    QuestionFeedbackContext,
    UserFeedbackSubmissionRecord,
)
from app.repositories.users import UserRecord
from app.schemas.user_feedback import UserFeedbackSubmissionCreate
from app.services.user_feedback import UserFeedbackService


class FakeUserFeedbackRepository:
    def __init__(self) -> None:
        self.created: list[UserFeedbackSubmissionRecord] = []
        self.interview_owners = {10: 1, 20: 2}
        self.round_interviews = {101: 10, 102: 10, 202: 20}
        self.question_contexts = {
            301: QuestionFeedbackContext(interview_id=10, round_id=101),
            302: QuestionFeedbackContext(interview_id=20, round_id=202),
        }

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
        record = UserFeedbackSubmissionRecord(
            id=len(self.created) + 1,
            user_id=user_id,
            feedback_type=feedback_type,
            content=content,
            rating=rating,
            interview_id=interview_id,
            round_id=round_id,
            question_id=question_id,
            status="new",
            created_at=datetime(2026, 7, 8, 10, 0, 0),
            updated_at=datetime(2026, 7, 8, 10, 0, 0),
        )
        self.created.append(record)
        return record

    def get_interview_owner_id(self, interview_id: int) -> int | None:
        return self.interview_owners.get(interview_id)

    def get_interview_id_by_round(self, round_id: int, user_id: int) -> int | None:
        interview_id = self.round_interviews.get(round_id)
        if interview_id is None or self.interview_owners.get(interview_id) != user_id:
            return None
        return interview_id

    def get_question_context(
        self,
        question_id: int,
        user_id: int,
    ) -> QuestionFeedbackContext | None:
        context = self.question_contexts.get(question_id)
        if context is None or self.interview_owners.get(context.interview_id) != user_id:
            return None
        return context


def test_submit_feedback_creates_general_submission() -> None:
    repository = FakeUserFeedbackRepository()
    service = UserFeedbackService(repository)

    response = service.submit_feedback(
        _user(1),
        UserFeedbackSubmissionCreate(
            feedback_type="scoring",
            content="评分结果和我的预期差异较大。",
            rating=2,
            interview_id=10,
        ),
    )

    assert response.id == 1
    assert response.feedback_type == "scoring"
    assert response.interview_id == 10
    assert repository.created[0].user_id == 1


def test_submit_feedback_derives_context_from_question() -> None:
    repository = FakeUserFeedbackRepository()
    service = UserFeedbackService(repository)

    response = service.submit_feedback(
        _user(1),
        UserFeedbackSubmissionCreate(
            feedback_type="question",
            content="这道追问和前面的回答关联不强。",
            question_id=301,
        ),
    )

    assert response.interview_id == 10
    assert response.round_id == 101
    assert response.question_id == 301


def test_submit_feedback_rejects_other_users_interview() -> None:
    service = UserFeedbackService(FakeUserFeedbackRepository())

    with pytest.raises(AppError) as error_info:
        service.submit_feedback(
            _user(1),
            UserFeedbackSubmissionCreate(content="这场面试不是当前用户的。", interview_id=20),
        )

    assert error_info.value.code == ErrorCode.NOT_FOUND
    assert error_info.value.status_code == 404


def test_submit_feedback_rejects_mismatched_round_and_question() -> None:
    service = UserFeedbackService(FakeUserFeedbackRepository())

    with pytest.raises(AppError) as error_info:
        service.submit_feedback(
            _user(1),
            UserFeedbackSubmissionCreate(
                content="题目和轮次关联不一致。",
                round_id=102,
                question_id=301,
            ),
        )

    assert error_info.value.code == ErrorCode.VALIDATION_ERROR


def test_api_submit_feedback_passes_current_user_and_payload() -> None:
    class FakeUserFeedbackService:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        def submit_feedback(
            self,
            current_user: UserRecord,
            request: UserFeedbackSubmissionCreate,
        ) -> object:
            self.calls.append((current_user.id, request.content))
            return {
                "id": 1,
                "feedback_type": "general",
                "content": request.content,
                "rating": None,
                "interview_id": None,
                "round_id": None,
                "question_id": None,
                "status": "new",
                "created_at": datetime(2026, 7, 8, 10, 0, 0),
                "updated_at": datetime(2026, 7, 8, 10, 0, 0),
            }

    service = FakeUserFeedbackService()
    payload = UserFeedbackSubmissionCreate(content="希望报告能给更多行动建议。")

    response = api_submit_feedback(
        payload=payload,
        current_user=_user(7),
        service=service,  # type: ignore[arg-type]
    )

    assert response["id"] == 1  # type: ignore[index]
    assert service.calls == [(7, "希望报告能给更多行动建议。")]


def _user(user_id: int) -> UserRecord:
    return UserRecord(id=user_id, username=f"user-{user_id}", password_hash="hash")
