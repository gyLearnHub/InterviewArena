from collections.abc import Iterator
from typing import Any, TypeVar

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query
from starlette.status import HTTP_204_NO_CONTENT

from app.core.errors import AppError, ErrorCode
from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.evaluations import EvaluationRepository
from app.repositories.harness import HarnessRepository
from app.repositories.history import HistoryRepository
from app.repositories.interview_tasks import (
    InterviewOperationTaskRecord,
    InterviewOperationTaskRepository,
)
from app.repositories.interviews import InterviewRepository
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.rag_audit import RagAuditRepository
from app.repositories.users import UserRecord
from app.schemas.harness import (
    HarnessCheckpointSummaryResponse,
    HarnessRuleEvaluationSummaryResponse,
    HarnessTraceSummaryResponse,
    InterviewHarnessStatusResponse,
)
from app.schemas.history import (
    HistoryDetail,
    HistoryListItem,
    HistoryListResponse,
    ReportListItem,
    ReportListResponse,
)
from app.schemas.interview import (
    FeedbackReportResponse,
    InterviewCreateRequest,
    InterviewCreateResponse,
    InterviewFinishRequest,
    InterviewOperationTaskResponse,
    InterviewRoundResponse,
    InterviewStateResponse,
    RoundAnswerRequest,
    RoundAnswerResponse,
    RoundFinishRequest,
)
from app.services.evaluations import EvaluationSchedulerService
from app.services.history import HistoryService
from app.services.interviews import InterviewService
from app.services.llm import LLMClient, get_llm_client
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.memory_tasks import MemoryTaskService
from app.services.usage_limits import usage_limiter

router = APIRouter(prefix="/interviews", tags=["interviews"])
LLMClientDep = Depends(get_llm_client)
OptionalRoundFinishBody = Body(default=None)
OptionalInterviewFinishBody = Body(default=None)
T = TypeVar("T")


def get_interview_repository() -> Iterator[InterviewRepository]:
    with mysql_connection() as connection:
        yield InterviewRepository(connection)


def get_history_repository() -> Iterator[HistoryRepository]:
    with mysql_connection() as connection:
        yield HistoryRepository(connection)


def get_harness_repository() -> Iterator[HarnessRepository]:
    with mysql_connection() as connection:
        yield HarnessRepository(connection)


def get_interview_operation_task_repository() -> Iterator[InterviewOperationTaskRepository]:
    with mysql_connection() as connection:
        yield InterviewOperationTaskRepository(connection)


InterviewRepositoryDep = Depends(get_interview_repository)
HistoryRepositoryDep = Depends(get_history_repository)
HarnessRepositoryDep = Depends(get_harness_repository)
InterviewTaskRepositoryDep = Depends(get_interview_operation_task_repository)


def get_interview_service(
    repository: InterviewRepository = InterviewRepositoryDep,
    llm_client: LLMClient = LLMClientDep,
) -> InterviewService:
    evaluation_service = EvaluationSchedulerService(
        EvaluationRepository(repository.connection),
        llm_client,
    )
    memory_task_service = MemoryTaskService(
        MemoryTaskRepository(repository.connection),
        PreferencesRepository(repository.connection),
    )
    preferences = PreferencesRepository(repository.connection)
    memory_retrieval_service = MemoryRetrievalService(
        memory_repository=MemoryRepository(repository.connection),
        audit_repository=RagAuditRepository(repository.connection),
    )
    return InterviewService(
        repository,
        llm_client,
        evaluation_service,
        memory_task_service,
        memory_retrieval_service,
        preferences,
    )


def get_history_service(
    repository: HistoryRepository = HistoryRepositoryDep,
) -> HistoryService:
    return HistoryService(repository)


CurrentUserDep = Depends(get_current_user)
InterviewServiceDep = Depends(get_interview_service)
HistoryServiceDep = Depends(get_history_service)


@router.post("", response_model=InterviewCreateResponse)
def create_interview(
    request: InterviewCreateRequest,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> InterviewCreateResponse:
    interview = service.create_interview(
        user_id=current_user.id,
        resume_id=request.resume_id,
        target_position=request.target_position,
        job_description=request.job_description,
        selected_rounds=request.selected_rounds,
    )
    rounds = service.list_rounds(interview)
    return InterviewCreateResponse(
        id=interview.id,
        status=interview.status,
        mode=interview.mode,
        rounds=[
            InterviewRoundResponse(
                id=item.id,
                round_type=item.round_type,
                status=item.status,
                score=item.score,
                result=item.result,
            )
            for item in rounds
        ],
    )


@router.get("/history", response_model=list[HistoryListItem])
def list_history(
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> list[HistoryListItem]:
    return service.list_history(current_user)


@router.get("/history/page", response_model=HistoryListResponse)
def list_history_page(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> HistoryListResponse:
    return service.list_history_page(current_user, limit=limit, offset=offset)


@router.get("/reports", response_model=list[ReportListItem])
def list_reports(
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> list[ReportListItem]:
    return service.list_reports(current_user)


@router.get("/reports/page", response_model=ReportListResponse)
def list_reports_page(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> ReportListResponse:
    return service.list_reports_page(current_user, limit=limit, offset=offset)


@router.delete("/history", status_code=HTTP_204_NO_CONTENT)
def clear_history(
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> None:
    service.clear_history(current_user)


@router.delete("/history/{interview_id}", status_code=HTTP_204_NO_CONTENT)
def delete_history_item(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> None:
    service.delete_history_item(interview_id, current_user)


@router.get("/tasks/{task_id}", response_model=InterviewOperationTaskResponse)
def get_interview_operation_task(
    task_id: int,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    task = task_repository.get_task_for_user(task_id, current_user.id)
    if task is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return _operation_task_response(task)


@router.get("/{interview_id}", response_model=HistoryDetail)
def get_history_detail(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> HistoryDetail:
    return service.get_detail(interview_id, current_user)


@router.get("/{interview_id}/state", response_model=InterviewStateResponse)
def get_interview_state(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> InterviewStateResponse:
    return service.get_state(current_user.id, interview_id)


@router.get("/{interview_id}/harness", response_model=InterviewHarnessStatusResponse)
def get_interview_harness_status(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    harness_repository: HarnessRepository = HarnessRepositoryDep,
) -> InterviewHarnessStatusResponse:
    interview = interview_repository.get_interview_for_user(interview_id, current_user.id)
    if interview is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    return InterviewHarnessStatusResponse(
        interview_id=interview.id,
        harness_status=interview.harness_status,
        recovery_count=interview.recovery_count,
        had_degradation=interview.had_degradation,
        traces=_records_to_models(
            harness_repository.list_traces(interview.id, user_id=current_user.id),
            HarnessTraceSummaryResponse,
        ),
        evaluations=_records_to_models(
            harness_repository.list_rule_evaluations(interview.id, user_id=current_user.id),
            HarnessRuleEvaluationSummaryResponse,
        ),
        checkpoints=_records_to_models(
            harness_repository.list_checkpoints(interview.id, user_id=current_user.id),
            HarnessCheckpointSummaryResponse,
        ),
    )


def _records_to_models(records: list[Any], model_type: type[T]) -> list[T]:
    return [
        model_type(**(dict(item) if isinstance(item, dict) else dict(item.__dict__)))
        for item in records
    ]


@router.post("/{interview_id}/pause", response_model=InterviewStateResponse)
def pause_interview(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> InterviewStateResponse:
    return service.pause_interview(current_user.id, interview_id)


@router.post("/{interview_id}/resume", response_model=InterviewStateResponse)
def resume_interview(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> InterviewStateResponse:
    return service.resume_interview(current_user.id, interview_id)


@router.post("/{interview_id}/rounds/{round_id}/start", response_model=RoundAnswerResponse)
def start_round(
    interview_id: int,
    round_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> RoundAnswerResponse:
    with usage_limiter.guard(current_user.id, "interview_question"):
        question = service.start_round(current_user.id, interview_id, round_id)
    return RoundAnswerResponse(action="next_question", question=question)


@router.post(
    "/{interview_id}/rounds/{round_id}/start-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def start_round_task(
    interview_id: int,
    round_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    with usage_limiter.guard(current_user.id, "interview_question"):
        task = _enqueue_interview_operation(
            task_repository,
            background_tasks,
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=round_id,
            operation="start_round",
            payload={"round_id": round_id},
        )
    return _operation_task_response(task)


@router.post("/{interview_id}/rounds/{round_id}/answers", response_model=RoundAnswerResponse)
def answer_round_question(
    interview_id: int,
    round_id: int,
    request: RoundAnswerRequest,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> RoundAnswerResponse:
    with usage_limiter.guard(current_user.id, "interview_answer"):
        return service.answer_round_question(
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=round_id,
            question_id=request.question_id,
            answer=request.answer,
            finish_after_answer=request.finish_after_answer,
        )


@router.post(
    "/{interview_id}/rounds/{round_id}/answers-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def answer_round_question_task(
    interview_id: int,
    round_id: int,
    request: RoundAnswerRequest,
    background_tasks: BackgroundTasks,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    with usage_limiter.guard(current_user.id, "interview_answer"):
        task = _enqueue_interview_operation(
            task_repository,
            background_tasks,
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=round_id,
            operation="answer_round_question",
            payload={
                "round_id": round_id,
                "question_id": request.question_id,
                "answer": request.answer,
                "finish_after_answer": request.finish_after_answer,
            },
        )
    return _operation_task_response(task)


@router.post(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/regenerate",
    response_model=RoundAnswerResponse,
)
def regenerate_round_question(
    interview_id: int,
    round_id: int,
    question_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> RoundAnswerResponse:
    with usage_limiter.guard(current_user.id, "interview_question"):
        return service.regenerate_round_question(
            current_user.id,
            interview_id,
            round_id,
            question_id,
        )


@router.post(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/regenerate-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def regenerate_round_question_task(
    interview_id: int,
    round_id: int,
    question_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    with usage_limiter.guard(current_user.id, "interview_question"):
        task = _enqueue_interview_operation(
            task_repository,
            background_tasks,
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=round_id,
            operation="regenerate_round_question",
            payload={"round_id": round_id, "question_id": question_id},
        )
    return _operation_task_response(task)


@router.post(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/skip",
    response_model=RoundAnswerResponse,
)
def skip_round_question(
    interview_id: int,
    round_id: int,
    question_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> RoundAnswerResponse:
    with usage_limiter.guard(current_user.id, "interview_question"):
        return service.skip_round_question(
            current_user.id,
            interview_id,
            round_id,
            question_id,
        )


@router.post(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/skip-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def skip_round_question_task(
    interview_id: int,
    round_id: int,
    question_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    with usage_limiter.guard(current_user.id, "interview_question"):
        task = _enqueue_interview_operation(
            task_repository,
            background_tasks,
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=round_id,
            operation="skip_round_question",
            payload={"round_id": round_id, "question_id": question_id},
        )
    return _operation_task_response(task)


@router.post("/{interview_id}/rounds/{round_id}/finish", response_model=RoundAnswerResponse)
def finish_round(
    interview_id: int,
    round_id: int,
    request: RoundFinishRequest | None = OptionalRoundFinishBody,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> RoundAnswerResponse:
    finish_type = request.finish_type if request is not None else "normal"
    with usage_limiter.guard(current_user.id, "interview_round_finish"):
        return service.finish_round(current_user.id, interview_id, round_id, finish_type)


@router.post(
    "/{interview_id}/rounds/{round_id}/finish-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def finish_round_task(
    interview_id: int,
    round_id: int,
    background_tasks: BackgroundTasks,
    request: RoundFinishRequest | None = OptionalRoundFinishBody,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    finish_type = request.finish_type if request is not None else "normal"
    with usage_limiter.guard(current_user.id, "interview_round_finish"):
        task = _enqueue_interview_operation(
            task_repository,
            background_tasks,
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=round_id,
            operation="finish_round",
            payload={"round_id": round_id, "finish_type": finish_type},
        )
    return _operation_task_response(task)


@router.post("/{interview_id}/finish", response_model=FeedbackReportResponse)
def finish_interview(
    interview_id: int,
    request: InterviewFinishRequest | None = OptionalInterviewFinishBody,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> FeedbackReportResponse:
    finish_type = request.finish_type if request is not None else "normal"
    with usage_limiter.guard(current_user.id, "interview_report_finish"):
        return service.finish_interview(current_user.id, interview_id, finish_type)


@router.post(
    "/{interview_id}/finish-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def finish_interview_task(
    interview_id: int,
    background_tasks: BackgroundTasks,
    request: InterviewFinishRequest | None = OptionalInterviewFinishBody,
    current_user: UserRecord = CurrentUserDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    finish_type = request.finish_type if request is not None else "normal"
    with usage_limiter.guard(current_user.id, "interview_report_finish"):
        task = _enqueue_interview_operation(
            task_repository,
            background_tasks,
            user_id=current_user.id,
            interview_id=interview_id,
            round_id=None,
            operation="finish_interview",
            payload={"finish_type": finish_type},
        )
    return _operation_task_response(task)


def _enqueue_interview_operation(
    repository: InterviewOperationTaskRepository,
    background_tasks: BackgroundTasks,
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    operation: str,
    payload: dict[str, Any],
) -> InterviewOperationTaskRecord:
    task = repository.create_task(
        user_id=user_id,
        interview_id=interview_id,
        round_id=round_id,
        operation=operation,
    )
    repository.connection.commit()
    background_tasks.add_task(run_interview_operation_task, task.id, payload)
    return task


def run_interview_operation_task(task_id: int, payload: dict[str, Any]) -> None:
    with mysql_connection() as connection:
        task_repository = InterviewOperationTaskRepository(connection)
        task = task_repository.get_task(task_id)
        if task is None:
            return
        task_repository.mark_processing(task.id)
        connection.commit()
    try:
        result = _run_interview_operation(task, payload)
    except AppError as exc:
        with mysql_connection() as connection:
            InterviewOperationTaskRepository(connection).mark_failed(
                task_id,
                error_code=exc.code.value,
                error_message=exc.message,
            )
        return
    except Exception as exc:
        with mysql_connection() as connection:
            InterviewOperationTaskRepository(connection).mark_failed(
                task_id,
                error_code=ErrorCode.INTERNAL_ERROR.value,
                error_message=str(exc) or exc.__class__.__name__,
            )
        return
    with mysql_connection() as connection:
        InterviewOperationTaskRepository(connection).mark_completed(task_id, result)


def _run_interview_operation(
    task: InterviewOperationTaskRecord,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with mysql_connection() as connection:
        service = _build_interview_service(connection)
        result: RoundAnswerResponse | FeedbackReportResponse
        if task.operation == "start_round":
            question = service.start_round(
                task.user_id,
                task.interview_id,
                int(payload["round_id"]),
            )
            result = RoundAnswerResponse(action="next_question", question=question)
        elif task.operation == "answer_round_question":
            result = service.answer_round_question(
                user_id=task.user_id,
                interview_id=task.interview_id,
                round_id=int(payload["round_id"]),
                question_id=int(payload["question_id"]),
                answer=str(payload["answer"]),
                finish_after_answer=bool(payload.get("finish_after_answer", False)),
            )
        elif task.operation == "regenerate_round_question":
            result = service.regenerate_round_question(
                task.user_id,
                task.interview_id,
                int(payload["round_id"]),
                int(payload["question_id"]),
            )
        elif task.operation == "skip_round_question":
            result = service.skip_round_question(
                task.user_id,
                task.interview_id,
                int(payload["round_id"]),
                int(payload["question_id"]),
            )
        elif task.operation == "finish_round":
            result = service.finish_round(
                task.user_id,
                task.interview_id,
                int(payload["round_id"]),
                str(payload.get("finish_type", "normal")),
            )
        elif task.operation == "finish_interview":
            result = service.finish_interview(
                task.user_id,
                task.interview_id,
                str(payload.get("finish_type", "normal")),
            )
        else:
            raise AppError(ErrorCode.VALIDATION_ERROR, 422, message="未知面试任务。")
        return result.model_dump(mode="json")


def _build_interview_service(connection: Any) -> InterviewService:
    repository = InterviewRepository(connection)
    llm_client = get_llm_client()
    return InterviewService(
        repository,
        llm_client,
        EvaluationSchedulerService(EvaluationRepository(connection), llm_client),
        MemoryTaskService(MemoryTaskRepository(connection), PreferencesRepository(connection)),
        MemoryRetrievalService(
            memory_repository=MemoryRepository(connection),
            audit_repository=RagAuditRepository(connection),
        ),
        PreferencesRepository(connection),
    )


def _operation_task_response(
    task: InterviewOperationTaskRecord,
) -> InterviewOperationTaskResponse:
    return InterviewOperationTaskResponse(
        task_id=task.id,
        operation=task.operation,
        status=task.status,
        interview_id=task.interview_id,
        round_id=task.round_id,
        result=task.result,
        error_code=task.error_code,
        error_message=task.error_message,
    )
