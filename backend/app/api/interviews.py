import asyncio
import contextlib
from collections.abc import Iterator
from datetime import datetime
from threading import Event, Thread
from typing import Any, TypeVar, cast

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query
from starlette.status import HTTP_204_NO_CONTENT

from app.autonomous_evolution.runtime import prepare_interview_evolution_context_task
from app.core.config import get_settings
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
    HistoryListResponse,
    ReportListResponse,
)
from app.schemas.interview import (
    AnswerDraftRequest,
    AnswerDraftResponse,
    FeedbackReportResponse,
    InterviewCreateRequest,
    InterviewCreateResponse,
    InterviewDifficulty,
    InterviewFinishRequest,
    InterviewGoal,
    InterviewOperationTaskResponse,
    InterviewRoundResponse,
    InterviewStateResponse,
    RoundAnswerRequest,
    RoundAnswerResponse,
    RoundFinishRequest,
    RoundStartRequest,
    TimeLimitMinutes,
    WeaknessPracticeRequest,
    WeaknessPracticeResponse,
)
from app.services.evaluations import EvaluationSchedulerService
from app.services.history import HistoryService
from app.services.interview_mutation_lock import interview_mutation_lock
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
    background_tasks: BackgroundTasks,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> InterviewCreateResponse:
    interview = service.create_interview(
        user_id=current_user.id,
        resume_id=request.resume_id,
        target_position=request.target_position,
        job_description=request.job_description,
        selected_rounds=request.selected_rounds,
        interview_goal=request.interview_goal,
        difficulty=request.difficulty,
        time_limit_minutes=request.time_limit_minutes,
    )
    background_tasks.add_task(
        prepare_interview_evolution_context_task,
        user_id=current_user.id,
        interview_id=interview.id,
        target_position=interview.target_position,
        job_description=interview.job_description,
    )
    rounds = service.list_rounds(interview)
    return InterviewCreateResponse(
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
            )
            for item in rounds
        ],
    )


@router.post("/{interview_id}/practice", response_model=WeaknessPracticeResponse)
def create_weakness_practice(
    interview_id: int,
    request: WeaknessPracticeRequest,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> WeaknessPracticeResponse:
    interview = service.create_weakness_practice(
        user_id=current_user.id,
        source_interview_id=interview_id,
        weakness=request.weakness,
        suggestion=request.suggestion,
        round_type=request.round_type,
    )
    rounds = service.list_rounds(interview)
    return WeaknessPracticeResponse(
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
            )
            for item in rounds
        ],
        source_interview_id=interview_id,
        practice_focus=request.weakness.strip(),
    )


@router.get("/history/page", response_model=HistoryListResponse)
def list_history_page(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserRecord = CurrentUserDep,
    service: HistoryService = HistoryServiceDep,
) -> HistoryListResponse:
    return service.list_history_page(current_user, limit=limit, offset=offset)


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
    with _interview_service_mutation_lock(service, interview_id):
        return service.pause_interview(current_user.id, interview_id)


@router.post("/{interview_id}/resume", response_model=InterviewStateResponse)
def resume_interview(
    interview_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> InterviewStateResponse:
    with _interview_service_mutation_lock(service, interview_id):
        return service.resume_interview(current_user.id, interview_id)


@router.post(
    "/{interview_id}/rounds/{round_id}/start-task",
    response_model=InterviewOperationTaskResponse,
    status_code=202,
)
def start_round_task(
    interview_id: int,
    round_id: int,
    background_tasks: BackgroundTasks,
    request: RoundStartRequest | None = None,
    current_user: UserRecord = CurrentUserDep,
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    task = _enqueue_interview_operation(
        interview_repository,
        task_repository,
        background_tasks,
        user_id=current_user.id,
        interview_id=interview_id,
        round_id=round_id,
        operation="start_round",
        payload={
            "round_id": round_id,
            "round_started_at": datetime.utcnow().isoformat(),
            "difficulty": request.difficulty if request is not None else None,
            "time_limit_minutes": (request.time_limit_minutes if request is not None else None),
        },
    )
    return _operation_task_response(task)


@router.get(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/draft",
    response_model=AnswerDraftResponse,
)
def get_round_answer_draft(
    interview_id: int,
    round_id: int,
    question_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> AnswerDraftResponse:
    return service.get_answer_draft(current_user.id, interview_id, round_id, question_id)


@router.put(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/draft",
    response_model=AnswerDraftResponse,
)
def save_round_answer_draft(
    interview_id: int,
    round_id: int,
    question_id: int,
    request: AnswerDraftRequest,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> AnswerDraftResponse:
    return service.save_answer_draft(
        current_user.id,
        interview_id,
        round_id,
        question_id,
        request.answer,
    )


@router.delete(
    "/{interview_id}/rounds/{round_id}/questions/{question_id}/draft",
    status_code=HTTP_204_NO_CONTENT,
)
def delete_round_answer_draft(
    interview_id: int,
    round_id: int,
    question_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: InterviewService = InterviewServiceDep,
) -> None:
    service.delete_answer_draft(current_user.id, interview_id, round_id, question_id)


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
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    task = _enqueue_interview_operation(
        interview_repository,
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
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    task = _enqueue_interview_operation(
        interview_repository,
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
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    task = _enqueue_interview_operation(
        interview_repository,
        task_repository,
        background_tasks,
        user_id=current_user.id,
        interview_id=interview_id,
        round_id=round_id,
        operation="skip_round_question",
        payload={"round_id": round_id, "question_id": question_id},
    )
    return _operation_task_response(task)


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
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    finish_type = request.finish_type if request is not None else "normal"
    task = _enqueue_interview_operation(
        interview_repository,
        task_repository,
        background_tasks,
        user_id=current_user.id,
        interview_id=interview_id,
        round_id=round_id,
        operation="finish_round",
        payload={"round_id": round_id, "finish_type": finish_type},
    )
    return _operation_task_response(task)


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
    interview_repository: InterviewRepository = InterviewRepositoryDep,
    task_repository: InterviewOperationTaskRepository = InterviewTaskRepositoryDep,
) -> InterviewOperationTaskResponse:
    finish_type = request.finish_type if request is not None else "normal"
    task = _enqueue_interview_operation(
        interview_repository,
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
    interview_repository: InterviewRepository,
    repository: InterviewOperationTaskRepository,
    background_tasks: BackgroundTasks,
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    operation: str,
    payload: dict[str, Any],
) -> InterviewOperationTaskRecord:
    active_operations = _conflicting_operations_for_operation(operation)
    _ensure_owned_interview_scope(
        interview_repository,
        user_id=user_id,
        interview_id=interview_id,
        round_id=round_id,
    )
    _ensure_no_active_interview_operation(
        repository,
        user_id=user_id,
        interview_id=interview_id,
        operations=active_operations,
    )
    with usage_limiter.guard(user_id, _operation_enqueue_scope(operation)):
        task = repository.create_task_for_owned_interview(
            user_id=user_id,
            interview_id=interview_id,
            round_id=round_id,
            operation=operation,
            payload=payload,
            exclusive_operations=active_operations,
        )
        if task is None:
            _ensure_no_active_interview_operation(
                repository,
                user_id=user_id,
                interview_id=interview_id,
                operations=active_operations,
            )
            raise AppError(ErrorCode.NOT_FOUND, 404)
        repository.connection.commit()
        background_tasks.add_task(run_interview_operation_task, task.id)
        return task


def _ensure_no_active_interview_operation(
    repository: InterviewOperationTaskRepository,
    *,
    user_id: int,
    interview_id: int,
    operations: tuple[str, ...],
) -> None:
    if repository.has_active_task_for_scope(
        user_id=user_id,
        interview_id=interview_id,
        operations=operations,
    ):
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            429,
            message="当前操作正在处理中，请稍后再试。",
        )


def _ensure_owned_interview_scope(
    repository: InterviewRepository,
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
) -> None:
    interview = repository.get_interview_for_user(interview_id, user_id)
    if interview is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)
    if round_id is not None and repository.get_round(interview.id, round_id) is None:
        raise AppError(ErrorCode.NOT_FOUND, 404)


def run_interview_operation_task(task_id: int, *, already_claimed: bool = False) -> None:
    task: InterviewOperationTaskRecord | None = None
    lease = None
    heartbeat: tuple[Event, Thread] | None = None
    try:
        task = _load_task_for_execution(task_id, already_claimed=already_claimed)
        if task is None:
            return
        payload = task.payload
        if payload is None:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                500,
                message="面试任务缺少可恢复的 payload。",
            )
        heartbeat = _start_interview_task_heartbeat(task)
        lease = usage_limiter.acquire(task.user_id, _operation_usage_scope(task.operation))
        result = _run_interview_operation(task, payload)
    except AppError as exc:
        _mark_interview_task_failed(
            task_id,
            exc.code.value,
            exc.message,
            processing_token=task.processing_token if task is not None else None,
        )
        return
    except Exception as exc:
        _mark_interview_task_failed(
            task_id,
            ErrorCode.INTERNAL_ERROR.value,
            str(exc) or exc.__class__.__name__,
            processing_token=task.processing_token if task is not None else None,
        )
        return
    finally:
        if lease is not None:
            usage_limiter.release(lease)
        _stop_interview_task_heartbeat(heartbeat)
    with mysql_connection() as connection:
        repository = InterviewOperationTaskRepository(connection)
        if task.processing_token is None:
            completed = repository.mark_completed(task_id, result)
        else:
            completed = repository.mark_completed(
                task_id,
                result,
                processing_token=task.processing_token,
            )
            if not completed:
                completed = repository.mark_completed_after_processing_timeout(task_id, result)
        if not completed:
            raise RuntimeError(
                f"interview task {task_id} committed business data but could not be completed"
            )


def _run_interview_operation(
    task: InterviewOperationTaskRecord,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with mysql_connection() as connection:
        with interview_mutation_lock(connection, task.interview_id, wait_seconds=1):
            service = _build_interview_service(connection)
            result: RoundAnswerResponse | FeedbackReportResponse
            if task.operation == "start_round":
                question = service.start_round(
                    task.user_id,
                    task.interview_id,
                    int(payload["round_id"]),
                    difficulty=payload.get("difficulty"),
                    time_limit_minutes=payload.get("time_limit_minutes"),
                    started_at=(
                        datetime.fromisoformat(str(payload["round_started_at"]))
                        if payload.get("round_started_at")
                        else None
                    ),
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


def _load_task_for_execution(
    task_id: int,
    *,
    already_claimed: bool = False,
) -> InterviewOperationTaskRecord | None:
    with mysql_connection() as connection:
        task_repository = InterviewOperationTaskRepository(connection)
        task = task_repository.get_task(task_id)
        if task is None:
            return None
        if task.status == "pending":
            if not task_repository.mark_processing(task.id):
                return None
            connection.commit()
            return task_repository.get_task(task.id)
        if task.status == "processing" and already_claimed:
            return task
        return None


def _mark_interview_task_failed(
    task_id: int,
    error_code: str | None,
    error_message: str,
    *,
    processing_token: str | None = None,
) -> None:
    with mysql_connection() as connection:
        InterviewOperationTaskRepository(connection).mark_failed(
            task_id,
            error_code=error_code,
            error_message=error_message,
            processing_token=processing_token,
        )


def _start_interview_task_heartbeat(
    task: InterviewOperationTaskRecord,
) -> tuple[Event, Thread] | None:
    if task.processing_token is None:
        return None
    stop_event = Event()
    interval = max(1, get_settings().interview_task_heartbeat_seconds)

    def _heartbeat_loop() -> None:
        while not stop_event.wait(interval):
            try:
                with mysql_connection() as connection:
                    alive = InterviewOperationTaskRepository(connection).heartbeat(
                        task.id,
                        task.processing_token or "",
                    )
                if not alive:
                    return
            except Exception:
                continue

    thread = Thread(target=_heartbeat_loop, name=f"interview-task-heartbeat-{task.id}", daemon=True)
    thread.start()
    return stop_event, thread


def _stop_interview_task_heartbeat(heartbeat: tuple[Event, Thread] | None) -> None:
    if heartbeat is None:
        return
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=1)


def _interview_service_mutation_lock(
    service: InterviewService,
    interview_id: int,
) -> contextlib.AbstractContextManager[None]:
    connection = getattr(service.repository, "connection", None)
    if connection is None:
        return contextlib.nullcontext()
    return interview_mutation_lock(connection, interview_id, wait_seconds=1)


def _operation_usage_scope(operation: str) -> str:
    if operation in {"start_round", "regenerate_round_question", "skip_round_question"}:
        return "interview_question"
    if operation == "answer_round_question":
        return "interview_answer"
    if operation == "finish_round":
        return "interview_round_finish"
    if operation == "finish_interview":
        return "interview_report_finish"
    return "interview_question"


def _operation_enqueue_scope(operation: str) -> str:
    return f"{_operation_usage_scope(operation)}_enqueue"


ROUND_MUTATING_OPERATIONS: tuple[str, ...] = (
    "start_round",
    "regenerate_round_question",
    "skip_round_question",
    "answer_round_question",
    "finish_round",
)
INTERVIEW_MUTATING_OPERATIONS: tuple[str, ...] = (
    *ROUND_MUTATING_OPERATIONS,
    "finish_interview",
)


def _conflicting_operations_for_operation(operation: str) -> tuple[str, ...]:
    if operation == "finish_interview":
        return INTERVIEW_MUTATING_OPERATIONS
    if operation in ROUND_MUTATING_OPERATIONS:
        return ROUND_MUTATING_OPERATIONS
    return (operation,)


class InterviewOperationTaskRunner:
    def run_once(self) -> bool:
        with mysql_connection() as connection:
            task = InterviewOperationTaskRepository(connection).claim_due_task(
                processing_timeout_seconds=(
                    get_settings().interview_task_processing_timeout_seconds
                ),
            )
        if task is None:
            return False
        run_interview_operation_task(task.id, already_claimed=True)
        return True


def start_interview_operation_task_runner() -> asyncio.Task[None]:
    settings = get_settings()

    async def _loop() -> None:
        runner = InterviewOperationTaskRunner()
        while True:
            try:
                await asyncio.to_thread(runner.run_once)
            except Exception:
                pass
            await asyncio.sleep(max(1, settings.memory_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_interview_operation_task_runner(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


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
