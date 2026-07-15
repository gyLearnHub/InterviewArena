from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, status
from starlette.status import HTTP_204_NO_CONTENT

from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.evaluations import EvaluationRepository
from app.repositories.history import HistoryRepository
from app.repositories.interviews import InterviewRepository
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.rag_audit import RagAuditRepository
from app.repositories.review_bookmarks import ReviewBookmarkRepository
from app.repositories.users import UserRecord
from app.schemas.review_bookmark import (
    ReviewBookmarkBatchResponse,
    ReviewBookmarkCreate,
    ReviewBookmarkItem,
    ReviewBookmarkPracticeResponse,
    ReviewBookmarkUpdate,
)
from app.services.evaluations import EvaluationSchedulerService
from app.services.history import HistoryService
from app.services.interviews import InterviewService
from app.services.llm import LLMClient, get_llm_client
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.memory_tasks import MemoryTaskService
from app.services.review_bookmarks import ReviewBookmarkService

router = APIRouter(prefix="/review-bookmarks", tags=["review-bookmarks"])
LLMClientDep = Depends(get_llm_client)
CurrentUserDep = Depends(get_current_user)


def get_review_bookmark_service(
    llm_client: LLMClient = LLMClientDep,
) -> Iterator[ReviewBookmarkService]:
    with mysql_connection() as connection:
        interview_repository = InterviewRepository(connection)
        preferences = PreferencesRepository(connection)
        interview_service = InterviewService(
            interview_repository,
            llm_client,
            EvaluationSchedulerService(EvaluationRepository(connection), llm_client),
            MemoryTaskService(MemoryTaskRepository(connection), preferences),
            MemoryRetrievalService(
                memory_repository=MemoryRepository(connection),
                audit_repository=RagAuditRepository(connection),
            ),
            preferences,
        )
        yield ReviewBookmarkService(
            ReviewBookmarkRepository(connection),
            interview_service,
            HistoryService(HistoryRepository(connection)),
        )


ReviewBookmarkServiceDep = Depends(get_review_bookmark_service)


@router.get("", response_model=list[ReviewBookmarkItem])
def list_review_bookmarks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    round_type: str | None = Query(
        default=None,
        pattern="^(all|resume|technical|manager|hr)$",
    ),
    status_filter: str = Query(
        default="all",
        alias="status",
        pattern="^(all|open|active|practice_created|mastered)$",
    ),
    current_user: UserRecord = CurrentUserDep,
    service: ReviewBookmarkService = ReviewBookmarkServiceDep,
) -> list[ReviewBookmarkItem]:
    return service.list_bookmarks(
        current_user,
        limit=limit,
        offset=offset,
        round_type=round_type,
        status_filter=status_filter,
    )


@router.post(
    "",
    response_model=ReviewBookmarkItem,
    status_code=status.HTTP_201_CREATED,
)
def create_review_bookmark(
    payload: ReviewBookmarkCreate,
    current_user: UserRecord = CurrentUserDep,
    service: ReviewBookmarkService = ReviewBookmarkServiceDep,
) -> ReviewBookmarkItem:
    return service.create_bookmark(current_user, payload)


@router.post("/from-report/{interview_id}", response_model=ReviewBookmarkBatchResponse)
def create_review_bookmarks_from_report(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: ReviewBookmarkService = ReviewBookmarkServiceDep,
) -> ReviewBookmarkBatchResponse:
    return service.create_from_report(current_user, interview_id)


@router.post("/{bookmark_id}/practice", response_model=ReviewBookmarkPracticeResponse)
def create_review_bookmark_practice(
    bookmark_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: ReviewBookmarkService = ReviewBookmarkServiceDep,
) -> ReviewBookmarkPracticeResponse:
    return service.create_practice(current_user, bookmark_id)


@router.patch("/{bookmark_id}", response_model=ReviewBookmarkItem)
def update_review_bookmark(
    bookmark_id: int,
    payload: ReviewBookmarkUpdate,
    current_user: UserRecord = CurrentUserDep,
    service: ReviewBookmarkService = ReviewBookmarkServiceDep,
) -> ReviewBookmarkItem:
    return service.update_bookmark(current_user, bookmark_id, payload)


@router.delete("/{bookmark_id}", status_code=HTTP_204_NO_CONTENT)
def delete_review_bookmark(
    bookmark_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: ReviewBookmarkService = ReviewBookmarkServiceDep,
) -> None:
    service.delete_bookmark(current_user, bookmark_id)
