import hashlib
from collections.abc import Mapping
from typing import Any, Protocol, cast

from fastapi import status
from pydantic import ValidationError

from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.repositories.interviews import InterviewRecord, InterviewRoundRecord
from app.repositories.review_bookmarks import (
    ReviewBookmarkInterviewContext,
    ReviewBookmarkQuestionContext,
    ReviewBookmarkRecord,
    ReviewBookmarkRoundContext,
)
from app.repositories.users import UserRecord
from app.schemas.history import HistoryDetail
from app.schemas.interview import (
    InterviewDifficulty,
    InterviewGoal,
    InterviewRoundResponse,
    TimeLimitMinutes,
)
from app.schemas.review_bookmark import (
    ReviewBookmarkBatchResponse,
    ReviewBookmarkCreate,
    ReviewBookmarkItem,
    ReviewBookmarkPracticeResponse,
    ReviewBookmarkRoundType,
    ReviewBookmarkUpdate,
    review_bookmark_evaluation_to_dict,
)

OPEN_BOOKMARK_STATUSES = ["active", "practice_created"]


class ReviewBookmarkRepositoryProtocol(Protocol):
    def list_by_user(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        round_type: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[ReviewBookmarkRecord]:
        ...

    def get_for_user(
        self,
        bookmark_id: int,
        user_id: int,
    ) -> ReviewBookmarkRecord | None:
        ...

    def lock_for_practice(
        self,
        bookmark_id: int,
        user_id: int,
    ) -> ReviewBookmarkRecord | None:
        ...

    def upsert_bookmark(
        self,
        *,
        user_id: int,
        bookmark_key: str,
        source_interview_id: int,
        target_position: str,
        round_id: int | None,
        round_type: str | None,
        question_id: int | None,
        title: str,
        issue: str,
        suggestion: str | None,
        question: str | None,
        answer: str | None,
        evaluation: dict[str, Any] | None,
        source_score: int | None,
    ) -> ReviewBookmarkRecord:
        ...

    def mark_practice_created(
        self,
        *,
        bookmark_id: int,
        user_id: int,
        practice_interview_id: int,
    ) -> ReviewBookmarkRecord | None:
        ...

    def update_status(
        self,
        *,
        bookmark_id: int,
        user_id: int,
        status: str,
    ) -> ReviewBookmarkRecord | None:
        ...

    def delete_for_user(self, bookmark_id: int, user_id: int) -> bool:
        ...

    def get_question_context(
        self,
        question_id: int,
        user_id: int,
    ) -> ReviewBookmarkQuestionContext | None:
        ...

    def get_interview_context(
        self,
        interview_id: int,
        user_id: int,
    ) -> ReviewBookmarkInterviewContext | None:
        ...

    def get_round_context(
        self,
        round_id: int,
        user_id: int,
    ) -> ReviewBookmarkRoundContext | None:
        ...


class InterviewPracticeServiceProtocol(Protocol):
    repository: Any

    def create_review_bookmark_practice(
        self,
        *,
        user_id: int,
        source_interview_id: int,
        weakness: str,
        suggestion: str | None = None,
        round_type: str | None = None,
        source_score: int | None = None,
    ) -> InterviewRecord:
        ...

    def list_rounds(self, interview: InterviewRecord) -> list[InterviewRoundRecord]:
        ...


class HistoryDetailServiceProtocol(Protocol):
    def get_detail(self, interview_id: int, current_user: UserRecord) -> HistoryDetail:
        ...


class ReviewBookmarkService:
    def __init__(
        self,
        repository: ReviewBookmarkRepositoryProtocol,
        interview_service: InterviewPracticeServiceProtocol,
        history_service: HistoryDetailServiceProtocol | None = None,
    ) -> None:
        self.repository = repository
        self.interview_service = interview_service
        self.history_service = history_service

    def list_bookmarks(
        self,
        current_user: UserRecord,
        *,
        limit: int,
        offset: int,
        round_type: str | None = None,
        status_filter: str = "all",
    ) -> list[ReviewBookmarkItem]:
        return [
            _to_item(record)
            for record in self.repository.list_by_user(
                current_user.id,
                limit=max(1, min(limit, 100)),
                offset=max(offset, 0),
                round_type=_normalize_round_type(round_type),
                statuses=_statuses_for_filter(status_filter),
            )
        ]

    def create_bookmark(
        self,
        current_user: UserRecord,
        request: ReviewBookmarkCreate,
    ) -> ReviewBookmarkItem:
        context = self._resolve_context(current_user.id, request)
        evaluation = _normalize_evaluation(request.evaluation)
        issue = _clip(
            _first_text(
                request.issue,
                _first_string(evaluation.get("issues")),
                request.title,
                _first_string(evaluation.get("strengths")),
                "这道回答需要复盘。",
            ),
            1000,
        )
        title = _clip(request.title or issue, 500)
        suggestion = _clip(
            _first_text(
                request.suggestion,
                _string_value(evaluation.get("follow_up_direction")),
                _first_string(evaluation.get("evidence")),
            ),
            1000,
        )
        round_id = request.round_id
        round_type = request.round_type
        question_id = request.question_id
        question: str | None = None
        answer: str | None = None

        if isinstance(context, ReviewBookmarkQuestionContext):
            round_id = context.round_id
            round_type = cast(ReviewBookmarkRoundType | None, context.round_type or round_type)
            question_id = context.question_id
            question = context.question
            answer = context.answer
        elif round_id is not None:
            round_context = self.repository.get_round_context(round_id, current_user.id)
            if round_context is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
            if round_context.interview_id != context.interview_id:
                raise _context_error()
            round_type = cast(
                ReviewBookmarkRoundType | None,
                round_context.round_type or round_type,
            )

        bookmark_key = _bookmark_key(
            source_interview_id=context.interview_id,
            question_id=question_id,
            round_type=round_type,
            title=title,
        )
        source_score = request.source_score
        if source_score is None:
            source_score = _score_from_evaluation(evaluation)
        record = self.repository.upsert_bookmark(
            user_id=current_user.id,
            bookmark_key=bookmark_key,
            source_interview_id=context.interview_id,
            target_position=context.target_position,
            round_id=round_id,
            round_type=round_type,
            question_id=question_id,
            title=title,
            issue=issue,
            suggestion=suggestion,
            question=question,
            answer=answer,
            evaluation=evaluation or None,
            source_score=source_score,
        )
        return _to_item(record)

    def create_from_report(
        self,
        current_user: UserRecord,
        interview_id: int,
    ) -> ReviewBookmarkBatchResponse:
        if self.history_service is None:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="复盘收藏服务未配置报告读取能力。",
            )
        detail = self.history_service.get_detail(interview_id, current_user)
        report = detail.feedback_report
        if report is None:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="需要先生成面试报告，才能生成复盘收藏。",
            )
        candidates = _report_bookmark_candidates(detail)
        if not candidates:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="报告中暂未找到可生成复盘收藏的问题。",
            )
        records = [
            self.repository.upsert_bookmark(
                user_id=current_user.id,
                bookmark_key=_bookmark_key(
                    source_interview_id=detail.interview_id,
                    question_id=None,
                    round_type=candidate["round_type"],
                    title=candidate["title"],
                ),
                source_interview_id=detail.interview_id,
                target_position=detail.target_position,
                round_id=None,
                round_type=candidate["round_type"],
                question_id=None,
                title=candidate["title"],
                issue=candidate["issue"],
                suggestion=candidate["suggestion"],
                question=None,
                answer=None,
                evaluation=_normalize_evaluation(candidate["evaluation"]),
                source_score=report.score,
            )
            for candidate in candidates
        ]
        return ReviewBookmarkBatchResponse(
            source_interview_id=detail.interview_id,
            items=[_to_item(record) for record in records],
            created_count=len(records),
        )

    def create_practice(
        self,
        current_user: UserRecord,
        bookmark_id: int,
    ) -> ReviewBookmarkPracticeResponse:
        lock_for_practice = getattr(self.repository, "lock_for_practice", None)
        bookmark = (
            lock_for_practice(bookmark_id, current_user.id)
            if callable(lock_for_practice)
            else self.repository.get_for_user(bookmark_id, current_user.id)
        )
        if bookmark is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if bookmark.practice_interview_id is not None:
            existing = self.interview_service.repository.get_interview_for_user(
                bookmark.practice_interview_id,
                current_user.id,
            )
            if existing is not None:
                return _practice_response(
                    bookmark,
                    existing,
                    self.interview_service.list_rounds(existing),
                )
        if bookmark.source_interview_id is None:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="原面试已删除，收藏内容仍可复盘，但不能新建专项练习。",
            )
        interview = self.interview_service.create_review_bookmark_practice(
            user_id=current_user.id,
            source_interview_id=bookmark.source_interview_id,
            weakness=bookmark.title,
            suggestion=bookmark.suggestion or bookmark.issue,
            round_type=bookmark.round_type,
            source_score=bookmark.source_score,
        )
        bookmark = (
            self.repository.mark_practice_created(
                bookmark_id=bookmark.id,
                user_id=current_user.id,
                practice_interview_id=interview.id,
            )
            or bookmark
        )
        return _practice_response(
            bookmark,
            interview,
            self.interview_service.list_rounds(interview),
        )

    def update_bookmark(
        self,
        current_user: UserRecord,
        bookmark_id: int,
        request: ReviewBookmarkUpdate,
    ) -> ReviewBookmarkItem:
        bookmark = self.repository.get_for_user(bookmark_id, current_user.id)
        if bookmark is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        next_status = (
            "mastered"
            if request.status == "mastered"
            else "practice_created"
            if bookmark.practice_interview_id is not None
            else "active"
        )
        updated = self.repository.update_status(
            bookmark_id=bookmark.id,
            user_id=current_user.id,
            status=next_status,
        )
        if updated is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        return _to_item(updated)

    def delete_bookmark(self, current_user: UserRecord, bookmark_id: int) -> None:
        if not self.repository.delete_for_user(bookmark_id, current_user.id):
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)

    def _resolve_context(
        self,
        user_id: int,
        request: ReviewBookmarkCreate,
    ) -> ReviewBookmarkQuestionContext | ReviewBookmarkInterviewContext:
        if request.question_id is not None:
            question_context = self.repository.get_question_context(request.question_id, user_id)
            if question_context is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
            if (
                request.interview_id is not None
                and request.interview_id != question_context.interview_id
            ):
                raise _context_error()
            if request.round_id is not None and question_context.round_id != request.round_id:
                raise _context_error()
            return question_context
        if request.interview_id is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                HTTP_422_UNPROCESSABLE_CONTENT,
                message="复盘收藏需要关联面试或题目。",
            )
        interview_context = self.repository.get_interview_context(request.interview_id, user_id)
        if interview_context is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        return interview_context


def _normalize_evaluation(evaluation: Any | None) -> dict[str, Any]:
    if evaluation is None:
        return {}
    try:
        return review_bookmark_evaluation_to_dict(evaluation)
    except (ValidationError, ValueError) as exc:
        message = (
            "复盘评价内容过大。"
            if "review_bookmark_evaluation_too_large" in str(exc) or "过大" in str(exc)
            else "复盘评价内容格式不正确。"
        )
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT,
            message=message,
        ) from exc


def _to_item(record: ReviewBookmarkRecord) -> ReviewBookmarkItem:
    return ReviewBookmarkItem(
        id=record.id,
        title=record.title,
        issue=record.issue,
        suggestion=record.suggestion,
        status=record.status,
        source_score=record.source_score,
        source_interview_id=record.source_interview_id,
        target_position=record.target_position,
        round_id=record.round_id,
        round_type=record.round_type,
        question_id=record.question_id,
        question=record.question,
        answer=record.answer,
        practice_interview_id=record.practice_interview_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _practice_response(
    bookmark: ReviewBookmarkRecord,
    interview: InterviewRecord,
    rounds: list[InterviewRoundRecord],
) -> ReviewBookmarkPracticeResponse:
    return ReviewBookmarkPracticeResponse(
        id=interview.id,
        status=interview.status,
        mode=interview.mode,
        interview_goal=cast(InterviewGoal, interview.interview_goal),
        difficulty=cast(InterviewDifficulty, interview.difficulty),
        time_limit_minutes=cast(TimeLimitMinutes, interview.time_limit_minutes),
        rounds=[
            InterviewRoundResponse(
                id=item.id,
                round_type=item.round_type,
                status=item.status,
                score=item.score,
                result=item.result,
                summary=item.summary,
                started_at=item.started_at,
                ended_at=item.ended_at,
            )
            for item in rounds
        ],
        bookmark_id=bookmark.id,
        source_interview_id=bookmark.source_interview_id,
        practice_focus=bookmark.title,
    )


def _report_bookmark_candidates(detail: HistoryDetail) -> list[dict[str, Any]]:
    report = detail.feedback_report
    if report is None:
        return []
    detailed_feedback = report.detailed_feedback or {}
    diagnosis = _dict_list(detailed_feedback.get("problem_diagnosis"))
    if diagnosis:
        diagnosis = sorted(diagnosis, key=lambda item: _severity_rank(str(item.get("severity"))))
        selected = [
            item for item in diagnosis if str(item.get("severity") or "").lower() == "high"
        ]
        return _dedupe_candidates([
            _candidate_from_diagnosis(item)
            for item in selected[:6]
        ])
    weaknesses = report.weaknesses or []
    suggestions = report.suggestions or []
    return _dedupe_candidates([
        {
            "title": _clip(weakness, 500),
            "issue": "来自最终总评的主要不足。",
            "suggestion": _clip(suggestions[index], 1000) if index < len(suggestions) else None,
            "round_type": _round_type_from_text(weakness),
            "evaluation": {
                "source": "final_report",
                "severity": "medium",
                "evidence": ["来自最终总评的主要不足。"],
            },
        }
        for index, weakness in enumerate(weaknesses[:6])
        if weakness.strip()
    ])


def _candidate_from_diagnosis(item: dict[str, Any]) -> dict[str, Any]:
    title = _clip(_first_text(_string_value(item.get("title")), "报告问题复盘"), 500)
    evidence = _string_list(item.get("evidence"))
    impact = _string_value(item.get("impact"))
    suggestion = _clip(_first_text(_string_value(item.get("suggestion"))), 1000) or None
    return {
        "title": title,
        "issue": _clip(_first_text(impact, title), 1000),
        "suggestion": suggestion,
        "round_type": _round_type_from_text(title),
        "evaluation": {
            "source": "final_report",
            "severity": _string_value(item.get("severity")) or "medium",
            "impact": impact,
            "evidence": evidence,
        },
    }


def _dedupe_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = f"{item.get('round_type') or 'all'}:{_compact(str(item.get('title') or ''))}"
        if not str(item.get("title") or "").strip() or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _severity_rank(value: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(value.lower(), 3)


def _round_type_from_text(value: str) -> str | None:
    if "简历面" in value:
        return "resume"
    if "技术面" in value:
        return "technical"
    if "主管面" in value:
        return "manager"
    if "HR" in value or "hr" in value.lower():
        return "hr"
    return None


def _context_error() -> AppError:
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        HTTP_422_UNPROCESSABLE_CONTENT,
        message="关联的面试、轮次和题目不一致。",
    )


def _normalize_round_type(value: str | None) -> str | None:
    if value in {"resume", "technical", "manager", "hr"}:
        return value
    if value in {None, "", "all"}:
        return None
    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        HTTP_422_UNPROCESSABLE_CONTENT,
        message="复盘筛选轮次不正确。",
    )


def _statuses_for_filter(value: str) -> list[str] | None:
    if value in {"", "all"}:
        return None
    if value == "open":
        return OPEN_BOOKMARK_STATUSES
    if value in {"active", "practice_created", "mastered"}:
        return [value]
    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        HTTP_422_UNPROCESSABLE_CONTENT,
        message="复盘筛选状态不正确。",
    )


def _bookmark_key(
    *,
    source_interview_id: int,
    question_id: int | None,
    round_type: str | None,
    title: str,
) -> str:
    if question_id is not None:
        raw = f"question:{question_id}"
    else:
        raw = f"interview:{source_interview_id}:{round_type or 'all'}:{_compact(title)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_text(*values: str | None) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _first_string(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = str(item).strip()
            if text:
                return text
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _score_from_evaluation(evaluation: dict[str, Any]) -> int | None:
    score = evaluation.get("total_score")
    if isinstance(score, (int, float)):
        return max(0, min(100, int(round(score))))
    return None


def _clip(value: str, limit: int) -> str:
    text = value.strip()
    return text[:limit]


def _compact(value: str) -> str:
    return "".join(value.strip().lower().split())
