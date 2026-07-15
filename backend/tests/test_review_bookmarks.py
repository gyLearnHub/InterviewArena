from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime
from typing import Any

import app.api.review_bookmarks as review_bookmarks_api
import pytest
from app.core.errors import AppError, ErrorCode
from app.deps import get_current_user
from app.repositories.interviews import InterviewRecord, InterviewRoundRecord
from app.repositories.review_bookmarks import (
    ReviewBookmarkInterviewContext,
    ReviewBookmarkQuestionContext,
    ReviewBookmarkRecord,
    ReviewBookmarkRepository,
    ReviewBookmarkRoundContext,
)
from app.repositories.users import UserRecord
from app.schemas.history import FeedbackReportSummary, HistoryDetail, ResumeSummary
from app.schemas.review_bookmark import (
    ReviewBookmarkCreate,
    ReviewBookmarkUpdate,
    review_bookmark_evaluation_to_dict,
)
from app.services.review_bookmarks import ReviewBookmarkService
from fastapi.testclient import TestClient
from main import create_app
from pydantic import ValidationError

DEFAULT_FEEDBACK_REPORT = object()


class FakeReviewBookmarkRepository:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 8, 12, 0, 0)
        self.question_contexts = {
            31: ReviewBookmarkQuestionContext(
                interview_id=10,
                target_position="后端开发实习生",
                round_id=101,
                round_type="technical",
                question_id=31,
                question="如何设计限流方案？",
                answer="我会先用令牌桶，并说明降级策略。",
            )
        }
        self.interview_contexts = {
            10: ReviewBookmarkInterviewContext(
                interview_id=10,
                target_position="后端开发实习生",
            ),
            11: ReviewBookmarkInterviewContext(
                interview_id=11,
                target_position="后端开发实习生",
            )
        }
        self.round_contexts = {
            101: ReviewBookmarkRoundContext(
                interview_id=10,
                round_id=101,
                round_type="technical",
            ),
            102: ReviewBookmarkRoundContext(
                interview_id=11,
                round_id=102,
                round_type="hr",
            ),
        }
        self.records: dict[int, ReviewBookmarkRecord] = {}
        self.created_payloads: list[dict[str, Any]] = []
        self.next_id = 1

    def list_by_user(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        round_type: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[ReviewBookmarkRecord]:
        records = [
            item
            for item in self.records.values()
            if item.user_id == user_id
        ]
        if round_type is not None:
            records = [item for item in records if item.round_type == round_type]
        if statuses:
            records = [item for item in records if item.status in statuses]
        return records[offset : offset + limit]

    def get_for_user(
        self,
        bookmark_id: int,
        user_id: int,
    ) -> ReviewBookmarkRecord | None:
        record = self.records.get(bookmark_id)
        return record if record is not None and record.user_id == user_id else None

    def upsert_bookmark(self, **payload: Any) -> ReviewBookmarkRecord:
        self.created_payloads.append(payload)
        existing = next(
            (
                item
                for item in self.records.values()
                if item.user_id == payload["user_id"]
                and item.bookmark_key == payload["bookmark_key"]
            ),
            None,
        )
        record_id = existing.id if existing is not None else self.next_id
        if existing is None:
            self.next_id += 1
        record = ReviewBookmarkRecord(
            id=record_id,
            user_id=payload["user_id"],
            bookmark_key=payload["bookmark_key"],
            source_interview_id=payload["source_interview_id"],
            target_position=payload["target_position"],
            round_id=payload["round_id"],
            round_type=payload["round_type"],
            question_id=payload["question_id"],
            title=payload["title"],
            issue=payload["issue"],
            suggestion=payload["suggestion"],
            question=payload["question"],
            answer=payload["answer"],
            evaluation=payload["evaluation"],
            source_score=payload["source_score"],
            status=existing.status if existing else "active",
            practice_interview_id=existing.practice_interview_id if existing else None,
            created_at=existing.created_at if existing else self.now,
            updated_at=self.now,
        )
        self.records[record.id] = record
        return record

    def mark_practice_created(
        self,
        *,
        bookmark_id: int,
        user_id: int,
        practice_interview_id: int,
    ) -> ReviewBookmarkRecord | None:
        record = self.get_for_user(bookmark_id, user_id)
        if record is None:
            return None
        updated = replace(
            record,
            status="practice_created",
            practice_interview_id=practice_interview_id,
            updated_at=self.now,
        )
        self.records[bookmark_id] = updated
        return updated

    def update_status(
        self,
        *,
        bookmark_id: int,
        user_id: int,
        status: str,
    ) -> ReviewBookmarkRecord | None:
        record = self.get_for_user(bookmark_id, user_id)
        if record is None:
            return None
        updated = replace(record, status=status, updated_at=self.now)
        self.records[bookmark_id] = updated
        return updated

    def delete_for_user(self, bookmark_id: int, user_id: int) -> bool:
        if self.get_for_user(bookmark_id, user_id) is None:
            return False
        del self.records[bookmark_id]
        return True

    def get_question_context(
        self,
        question_id: int,
        user_id: int,
    ) -> ReviewBookmarkQuestionContext | None:
        return self.question_contexts.get(question_id) if user_id == 1 else None

    def get_interview_context(
        self,
        interview_id: int,
        user_id: int,
    ) -> ReviewBookmarkInterviewContext | None:
        return self.interview_contexts.get(interview_id) if user_id == 1 else None

    def get_round_context(
        self,
        round_id: int,
        user_id: int,
    ) -> ReviewBookmarkRoundContext | None:
        return self.round_contexts.get(round_id) if user_id == 1 else None


class FakeInterviewRepository:
    def __init__(self) -> None:
        self.interviews: dict[int, InterviewRecord] = {}

    def get_interview_for_user(self, interview_id: int, user_id: int) -> InterviewRecord | None:
        interview = self.interviews.get(interview_id)
        return interview if interview is not None and interview.user_id == user_id else None


class FakeInterviewPracticeService:
    def __init__(self) -> None:
        self.repository = FakeInterviewRepository()
        self.calls: list[dict[str, Any]] = []
        self.rounds = [
            InterviewRoundRecord(
                id=901,
                interview_id=200,
                agent_type="technical",
                round_type="technical",
                status="pending",
                min_main_questions=1,
                max_main_questions=3,
                min_total_questions=1,
                max_total_questions=4,
                score=None,
                result=None,
                summary=None,
                is_reference_only=False,
                started_at=None,
                ended_at=None,
            )
        ]

    def create_review_bookmark_practice(self, **payload: Any) -> InterviewRecord:
        self.calls.append(payload)
        interview = _interview(200, payload["user_id"], payload["source_interview_id"])
        self.repository.interviews[interview.id] = interview
        return interview

    def list_rounds(self, interview: InterviewRecord) -> list[InterviewRoundRecord]:
        return self.rounds


class FakeHistoryService:
    def __init__(self, detail: HistoryDetail) -> None:
        self.detail = detail
        self.calls: list[tuple[int, int]] = []

    def get_detail(self, interview_id: int, current_user: UserRecord) -> HistoryDetail:
        self.calls.append((interview_id, current_user.id))
        return self.detail


@pytest.fixture()
def review_bookmark_client() -> Iterator[tuple[TestClient, FakeReviewBookmarkRepository]]:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(1)
    app.dependency_overrides[review_bookmarks_api.get_review_bookmark_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, repository
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_review_bookmark_schema_accepts_controlled_evaluation_structure() -> None:
    request = ReviewBookmarkCreate(
        question_id=31,
        evaluation={
            "evaluation_id": 9,
            "question_id": 31,
            "round_id": 101,
            "round_type": "technical",
            "status": "succeeded",
            "total_score": 68,
            "dimension_scores": [
                {
                    "dimension": "系统设计",
                    "score": 70,
                    "reason": "能说明限流思路。",
                }
            ],
            "strengths": ["能说明令牌桶。"],
            "issues": ["缺少压测数据。"],
            "evidence": "回答没有给出容量估算。",
            "should_follow_up": True,
            "follow_up_direction": "  追问容量评估和故障处理。  ",
            "prompt_version": "question-evaluation-v1",
            "model_name": "fake-model",
        },
    )

    payload = review_bookmark_evaluation_to_dict(request.evaluation)

    assert payload["evidence"] == ["回答没有给出容量估算。"]
    assert payload["follow_up_direction"] == "追问容量评估和故障处理。"
    assert payload["dimension_scores"][0]["dimension"] == "系统设计"
    assert payload["model_name"] == "fake-model"


def test_review_bookmark_schema_rejects_unknown_evaluation_keys() -> None:
    with pytest.raises(ValidationError):
        ReviewBookmarkCreate(
            question_id=31,
            evaluation={
                "issues": ["缺少压测数据。"],
                "raw_prompt": "should not be accepted",
            },
        )


def test_review_bookmark_schema_rejects_total_evaluation_size_over_limit() -> None:
    with pytest.raises(ValidationError) as error_info:
        ReviewBookmarkCreate(question_id=31, evaluation=_oversized_evaluation_payload())

    assert "复盘评价内容过大" in str(error_info.value)


def test_create_review_bookmark_api_accepts_small_evaluation_create_and_update(
    review_bookmark_client: tuple[TestClient, FakeReviewBookmarkRepository],
) -> None:
    client, repository = review_bookmark_client

    first = client.post(
        "/api/review-bookmarks",
        json={
            "question_id": 31,
            "evaluation": {
                "total_score": 68,
                "issues": ["缺少压测数据。"],
                "evidence": ["回答没有给出容量估算。"],
                "follow_up_direction": "追问容量评估和故障处理。",
                "model_name": "fake-model",
            },
        },
    )
    second = client.post(
        "/api/review-bookmarks",
        json={
            "question_id": 31,
            "evaluation": {
                "total_score": 82,
                "issues": ["已补充容量估算，但降级边界还可细化。"],
                "evidence": ["回答给出了 QPS 和压测结果。"],
                "follow_up_direction": "继续追问异常降级边界。",
                "model_name": "fake-model",
            },
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["source_score"] == 82
    assert repository.created_payloads[-1]["evaluation"]["total_score"] == 82
    assert repository.created_payloads[-1]["evaluation"]["model_name"] == "fake-model"


def test_create_review_bookmark_api_rejects_oversized_evaluation(
    review_bookmark_client: tuple[TestClient, FakeReviewBookmarkRepository],
) -> None:
    client, repository = review_bookmark_client

    response = client.post(
        "/api/review-bookmarks",
        json={"question_id": 31, "evaluation": _oversized_evaluation_payload()},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert repository.created_payloads == []


def test_create_bookmark_from_question_evaluation() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())

    response = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(
            interview_id=10,
            question_id=31,
            evaluation={
                "total_score": 68,
                "issues": ["缺少压测数据。", "降级边界还不够清楚。"],
                "follow_up_direction": "追问容量评估和故障处理。",
            },
        ),
    )

    assert response.title == "缺少压测数据。"
    assert response.issue == "缺少压测数据。"
    assert response.suggestion == "追问容量评估和故障处理。"
    assert response.source_score == 68
    assert response.question == "如何设计限流方案？"
    assert response.answer == "我会先用令牌桶，并说明降级策略。"
    assert repository.created_payloads[0]["round_type"] == "technical"


def test_create_bookmark_rejects_oversized_evaluation() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())
    request = ReviewBookmarkCreate.model_construct(
        question_id=31,
        evaluation=_oversized_evaluation_payload(),
    )

    with pytest.raises(AppError) as error_info:
        service.create_bookmark(_user(1), request)

    assert error_info.value.code == ErrorCode.VALIDATION_ERROR
    assert repository.created_payloads == []


def test_create_bookmark_persists_controlled_evaluation_payload() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())

    service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(
            question_id=31,
            evaluation={
                "total_score": 72.4,
                "issues": ["缺少容量估算。", "降级边界还不够清楚。"],
                "evidence": ["回答没有给出容量估算。"],
                "follow_up_direction": "  追问容量和降级边界。  ",
                "dimension_scores": [
                    {
                        "dimension": "系统设计",
                        "score": 70,
                        "reason": "能说明限流思路。",
                    }
                ],
                "prompt_version": "question-evaluation-v1",
            },
        ),
    )

    evaluation = repository.created_payloads[0]["evaluation"]
    assert evaluation["issues"][0] == "缺少容量估算。"
    assert evaluation["issues"][1] == "降级边界还不够清楚。"
    assert evaluation["follow_up_direction"] == "追问容量和降级边界。"
    assert evaluation["evidence"] == ["回答没有给出容量估算。"]
    assert evaluation["dimension_scores"][0]["dimension"] == "系统设计"
    assert evaluation["prompt_version"] == "question-evaluation-v1"


def test_create_bookmark_is_idempotent_for_same_question() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())
    request = ReviewBookmarkCreate(question_id=31, issue="缺少压测数据。")

    first = service.create_bookmark(_user(1), request)
    second = service.create_bookmark(_user(1), request)

    assert first.id == second.id
    assert len(repository.records) == 1


def test_create_bookmark_rejects_mismatched_interview() -> None:
    service = ReviewBookmarkService(
        FakeReviewBookmarkRepository(),
        FakeInterviewPracticeService(),
    )

    with pytest.raises(AppError) as error_info:
        service.create_bookmark(
            _user(1),
            ReviewBookmarkCreate(interview_id=99, question_id=31, issue="上下文错误。"),
        )

    assert error_info.value.code == ErrorCode.VALIDATION_ERROR


def test_create_bookmark_from_interview_round_uses_owned_round_context() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())

    response = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(
            interview_id=10,
            round_id=101,
            round_type="hr",
            issue="系统设计细节不够完整。",
        ),
    )

    assert response.round_id == 101
    assert response.round_type == "technical"
    assert repository.created_payloads[0]["round_id"] == 101
    assert repository.created_payloads[0]["round_type"] == "technical"


def test_create_bookmark_rejects_round_from_other_interview() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())

    with pytest.raises(AppError) as error_info:
        service.create_bookmark(
            _user(1),
            ReviewBookmarkCreate(
                interview_id=10,
                round_id=102,
                issue="上下文错误。",
            ),
        )

    assert error_info.value.code == ErrorCode.VALIDATION_ERROR
    assert repository.created_payloads == []


def test_create_bookmark_rejects_unknown_round_context() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())

    with pytest.raises(AppError) as error_info:
        service.create_bookmark(
            _user(1),
            ReviewBookmarkCreate(
                interview_id=10,
                round_id=999,
                issue="上下文错误。",
            ),
        )

    assert error_info.value.code == ErrorCode.NOT_FOUND
    assert repository.created_payloads == []


def test_create_practice_from_review_bookmark() -> None:
    repository = FakeReviewBookmarkRepository()
    interview_service = FakeInterviewPracticeService()
    service = ReviewBookmarkService(repository, interview_service)
    bookmark = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(
            question_id=31,
            issue="缺少容量估算。",
            suggestion="补充 QPS 和降级。",
        ),
    )

    response = service.create_practice(_user(1), bookmark.id)

    assert response.id == 200
    assert response.bookmark_id == bookmark.id
    assert response.practice_focus == "缺少容量估算。"
    assert response.rounds[0].round_type == "technical"
    assert repository.records[bookmark.id].practice_interview_id == 200
    assert interview_service.calls[0]["source_interview_id"] == 10
    assert interview_service.calls[0]["suggestion"] == "补充 QPS 和降级。"


def test_create_practice_reuses_existing_practice_interview() -> None:
    repository = FakeReviewBookmarkRepository()
    interview_service = FakeInterviewPracticeService()
    service = ReviewBookmarkService(repository, interview_service)
    bookmark = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(question_id=31, issue="缺少容量估算。"),
    )
    existing = _interview(300, 1, 10)
    interview_service.repository.interviews[existing.id] = existing
    repository.records[bookmark.id] = replace(
        repository.records[bookmark.id],
        status="practice_created",
        practice_interview_id=300,
    )

    response = service.create_practice(_user(1), bookmark.id)

    assert response.id == 300
    assert interview_service.calls == []


def test_create_practice_rejects_detached_source_but_keeps_bookmark() -> None:
    repository = FakeReviewBookmarkRepository()
    interview_service = FakeInterviewPracticeService()
    service = ReviewBookmarkService(repository, interview_service)
    bookmark = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(question_id=31, issue="缺少容量估算。"),
    )
    repository.records[bookmark.id] = replace(
        repository.records[bookmark.id],
        source_interview_id=None,
    )

    with pytest.raises(AppError) as error_info:
        service.create_practice(_user(1), bookmark.id)

    assert error_info.value.status_code == 409
    assert repository.get_for_user(bookmark.id, 1) is not None
    assert interview_service.calls == []


def test_list_bookmarks_filters_open_and_round_type() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())
    technical = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(question_id=31, issue="缺少容量估算。"),
    )
    repository.records[technical.id] = replace(
        repository.records[technical.id],
        status="mastered",
    )
    repository.question_contexts[32] = replace(
        repository.question_contexts[31],
        question_id=32,
        round_type="hr",
    )
    service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(question_id=32, issue="表达略散。"),
    )

    open_items = service.list_bookmarks(_user(1), limit=20, offset=0, status_filter="open")
    hr_items = service.list_bookmarks(
        _user(1),
        limit=20,
        offset=0,
        round_type="hr",
        status_filter="open",
    )

    assert [item.title for item in open_items] == ["表达略散。"]
    assert [item.round_type for item in hr_items] == ["hr"]


def test_update_bookmark_marks_mastered_and_restores_open_status() -> None:
    repository = FakeReviewBookmarkRepository()
    interview_service = FakeInterviewPracticeService()
    service = ReviewBookmarkService(repository, interview_service)
    bookmark = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(question_id=31, issue="缺少容量估算。"),
    )

    mastered = service.update_bookmark(
        _user(1),
        bookmark.id,
        ReviewBookmarkUpdate(status="mastered"),
    )
    restored = service.update_bookmark(
        _user(1),
        bookmark.id,
        ReviewBookmarkUpdate(status="active"),
    )

    assert mastered.status == "mastered"
    assert restored.status == "active"


def test_update_bookmark_restores_practice_created_when_practice_exists() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(repository, FakeInterviewPracticeService())
    bookmark = service.create_bookmark(
        _user(1),
        ReviewBookmarkCreate(question_id=31, issue="缺少容量估算。"),
    )
    repository.records[bookmark.id] = replace(
        repository.records[bookmark.id],
        practice_interview_id=300,
        status="mastered",
    )

    restored = service.update_bookmark(
        _user(1),
        bookmark.id,
        ReviewBookmarkUpdate(status="active"),
    )

    assert restored.status == "practice_created"


def test_create_from_report_generates_high_priority_review_bookmarks() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(
        repository,
        FakeInterviewPracticeService(),
        FakeHistoryService(_history_detail()),
    )

    response = service.create_from_report(_user(1), 10)

    assert response.source_interview_id == 10
    assert response.created_count == 1
    assert [item.title for item in response.items] == ["技术面：缺少压测数据。"]
    assert response.items[0].round_type == "technical"
    assert response.items[0].source_score == 58
    assert repository.created_payloads[-1]["evaluation"]["severity"] == "high"


def test_create_from_report_preserves_mastered_bookmark_status() -> None:
    repository = FakeReviewBookmarkRepository()
    service = ReviewBookmarkService(
        repository,
        FakeInterviewPracticeService(),
        FakeHistoryService(_history_detail()),
    )
    created = service.create_from_report(_user(1), 10).items[0]
    repository.records[created.id] = replace(repository.records[created.id], status="mastered")

    refreshed = service.create_from_report(_user(1), 10).items[0]

    assert refreshed.id == created.id
    assert refreshed.status == "mastered"


def test_repository_upsert_does_not_reset_bookmark_status() -> None:
    source = __import__("inspect").getsource(ReviewBookmarkRepository.upsert_bookmark)
    duplicate_clause = source.split("ON DUPLICATE KEY UPDATE", 1)[1]

    assert "status = 'active'" not in duplicate_clause


def test_create_from_report_falls_back_to_report_weaknesses() -> None:
    detail = _history_detail(
        detailed_feedback={},
        weaknesses=["表达略散", "项目结果不够量化"],
        suggestions=["按 STAR 结构组织。", "补充指标。"],
    )
    service = ReviewBookmarkService(
        FakeReviewBookmarkRepository(),
        FakeInterviewPracticeService(),
        FakeHistoryService(detail),
    )

    response = service.create_from_report(_user(1), 10)

    assert [item.title for item in response.items] == ["表达略散", "项目结果不够量化"]
    assert response.items[0].suggestion == "按 STAR 结构组织。"


def test_create_from_report_rejects_diagnosis_without_high_priority_issue() -> None:
    detail = _history_detail(
        detailed_feedback={
            "problem_diagnosis": [
                {
                    "title": "主管面：项目复盘不够量化。",
                    "severity": "medium",
                    "impact": "影响结果意识判断。",
                    "suggestion": "补充业务指标和对比数据。",
                    "evidence": ["只描述了过程。"],
                }
            ]
        }
    )
    service = ReviewBookmarkService(
        FakeReviewBookmarkRepository(),
        FakeInterviewPracticeService(),
        FakeHistoryService(detail),
    )

    with pytest.raises(AppError) as error_info:
        service.create_from_report(_user(1), 10)

    assert error_info.value.code == ErrorCode.BUSINESS_ERROR


def test_create_from_report_rejects_missing_report() -> None:
    detail = _history_detail(feedback_report=None)
    service = ReviewBookmarkService(
        FakeReviewBookmarkRepository(),
        FakeInterviewPracticeService(),
        FakeHistoryService(detail),
    )

    with pytest.raises(AppError) as error_info:
        service.create_from_report(_user(1), 10)

    assert error_info.value.code == ErrorCode.BUSINESS_ERROR


def _oversized_evaluation_payload() -> dict[str, Any]:
    chunk = "x" * 900
    return {
        "issues": [chunk] * 8,
        "evidence": [chunk] * 8,
        "strengths": [chunk] * 4,
    }


def _user(user_id: int) -> UserRecord:
    return UserRecord(id=user_id, username=f"user-{user_id}", password_hash="hash")


def _interview(interview_id: int, user_id: int, source_interview_id: int) -> InterviewRecord:
    return InterviewRecord(
        id=interview_id,
        user_id=user_id,
        resume_id=source_interview_id,
        target_position="后端开发实习生",
        status="created",
        question_count=0,
        started_at=None,
        ended_at=None,
        mode="multi_round",
        job_description=None,
        selected_rounds=["technical"],
        interview_goal="internship",
        difficulty="normal",
        time_limit_minutes=45,
        overall_status="created",
    )


def _history_detail(
    *,
    feedback_report: FeedbackReportSummary | None | object = DEFAULT_FEEDBACK_REPORT,
    detailed_feedback: dict[str, Any] | None = None,
    weaknesses: list[str] | None = None,
    suggestions: list[str] | None = None,
) -> HistoryDetail:
    resolved_report: FeedbackReportSummary | None
    if feedback_report is None:
        resolved_report = None
    elif isinstance(feedback_report, FeedbackReportSummary):
        resolved_report = feedback_report
    else:
        resolved_report = FeedbackReportSummary(
            score=58,
            weaknesses=weaknesses or ["缺少压测数据。"],
            suggestions=suggestions or ["补充容量评估和指标。"],
            detailed_feedback=detailed_feedback
            if detailed_feedback is not None
            else {
                "problem_diagnosis": [
                    {
                        "title": "技术面：缺少压测数据。",
                        "severity": "high",
                        "impact": "影响系统设计可信度。",
                        "suggestion": "补充 QPS、压测结果和降级边界。",
                        "evidence": ["回答没有给出容量估算。"],
                    },
                    {
                        "title": "主管面：项目复盘不够量化。",
                        "severity": "medium",
                        "impact": "影响结果意识判断。",
                        "suggestion": "补充业务指标和对比数据。",
                        "evidence": ["只描述了过程。"],
                    },
                    {
                        "title": "HR 面：表达仍可更聚焦。",
                        "severity": "low",
                        "impact": "轻微影响沟通效率。",
                        "suggestion": "缩短背景铺垫。",
                        "evidence": ["回答略长。"],
                    },
                ]
            },
        )
    return HistoryDetail(
        interview_id=10,
        target_position="后端开发实习生",
        status="finished",
        resume=ResumeSummary(
            id=1,
            created_at=datetime(2026, 7, 8, 10, 0, 0),
            structured_data={},
        ),
        feedback_report=resolved_report,
    )
