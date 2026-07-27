import asyncio
import contextlib
import logging
from hashlib import sha256
from pathlib import Path
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.http_status import (
    HTTP_413_CONTENT_TOO_LARGE,
    HTTP_422_UNPROCESSABLE_CONTENT,
)
from app.db.mysql import mysql_connection
from app.deps import DatabaseConnectionDep, get_current_user
from app.repositories.job_match_tasks import (
    JobMatchAnalysisTaskRecord,
    JobMatchAnalysisTaskRepository,
)
from app.repositories.resumes import (
    FileCleanupTaskRecord,
    ResumeDetailRecord,
    ResumeParseTaskRecord,
    ResumeRecord,
    ResumeRepository,
)
from app.repositories.users import UserRecord
from app.schemas.resume import (
    JobMatchAnalysisRequest,
    JobMatchAnalysisResponse,
    JobMatchAnalysisTaskResponse,
    ResumeDetailResponse,
    ResumeListItem,
    ResumeParseTaskResponse,
    ResumeUpdateRequest,
    StructuredResumeData,
)
from app.services.job_match_analysis import JobMatchAnalysisService
from app.services.llm import LLMClient, get_llm_client
from app.services.privacy import (
    ensure_external_model_consent,
    require_external_model_consent,
)
from app.services.resume_parser import (
    MAX_RESUME_BYTES,
    ResumeParserService,
    resolve_upload_dir,
    store_resume_upload,
    validate_resume_extension,
)
from app.services.resumes import ResumeService, delete_resume_file
from app.services.runner_health import record_runner_failure, record_runner_success
from app.services.usage_limits import usage_limiter

router = APIRouter(prefix="/resumes", tags=["resumes"])
LOGGER = logging.getLogger(__name__)
RESUME_PARSE_VERSION = b"resume-parser-v2-project-completeness\0"
ResumeFile = File(...)
CurrentUserDep = Depends(get_current_user)


def get_resume_repository(connection: Any = DatabaseConnectionDep) -> ResumeRepository:
    return ResumeRepository(connection)


def get_job_match_task_repository(
    connection: Any = DatabaseConnectionDep,
) -> JobMatchAnalysisTaskRepository:
    return JobMatchAnalysisTaskRepository(connection)


def get_resume_parser() -> ResumeParserService:
    return ResumeParserService(llm_client=get_llm_client())


ResumeRepositoryDep = Depends(get_resume_repository)
JobMatchTaskRepositoryDep = Depends(get_job_match_task_repository)
ResumeParserDep = Depends(get_resume_parser)


def get_resume_service(
    resumes: ResumeRepository = ResumeRepositoryDep,
    parser: ResumeParserService = ResumeParserDep,
) -> ResumeService:
    return ResumeService(resumes, resolve_upload_dir(parser.settings))


ResumeServiceDep = Depends(get_resume_service)


def get_job_match_llm_client() -> LLMClient:
    return get_llm_client()


JobMatchLLMClientDep = Depends(get_job_match_llm_client)


def get_job_match_analysis_service(
    resumes: ResumeRepository = ResumeRepositoryDep,
    llm_client: LLMClient = JobMatchLLMClientDep,
) -> JobMatchAnalysisService:
    return JobMatchAnalysisService(resumes, llm_client)


JobMatchAnalysisServiceDep = Depends(get_job_match_analysis_service)


@router.get("", response_model=list[ResumeListItem])
def list_resumes(
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
) -> list[ResumeListItem]:
    return [
        ResumeListItem(
            id=resume.id,
            name=resume.name,
            uploaded_at=resume.uploaded_at,
            last_used_at=resume.last_used_at,
            parse_status=resume.parse_status,
            is_default=resume.is_default,
        )
        for resume in resumes.list_summaries_by_user(current_user.id)
    ]


@router.post(
    "/upload-async",
    response_model=ResumeParseTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_resume_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = ResumeFile,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
    parser: ResumeParserService = ResumeParserDep,
) -> ResumeParseTaskResponse:
    require_external_model_consent(current_user)
    validate_resume_extension(file.filename or "")
    content = file.file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_413_CONTENT_TOO_LARGE)

    content_hash = resume_content_hash(content)
    duplicated_resume = find_duplicate_resume(content_hash, current_user.id, resumes)
    if duplicated_resume is not None:
        task = resumes.get_or_create_completed_parse_task(
            user_id=current_user.id,
            original_file_path=duplicated_resume.original_file_path,
            content_hash=content_hash,
            resume_id=duplicated_resume.id,
        )
        return _parse_task_response(task, resumes)

    existing_task = resumes.get_active_parse_task_by_content_hash(current_user.id, content_hash)
    if existing_task is not None:
        return _parse_task_response(existing_task, resumes)

    with usage_limiter.guard(current_user.id, "resume_upload_enqueue"):
        existing_task = resumes.get_active_parse_task_by_content_hash(current_user.id, content_hash)
        if existing_task is not None:
            return _parse_task_response(existing_task, resumes)

        upload_dir = resolve_upload_dir(parser.settings) / str(current_user.id)
        original_path = store_resume_upload(
            file.filename or "resume.docx",
            upload_dir,
            content,
        )
        try:
            task = resumes.create_parse_task(
                user_id=current_user.id,
                original_file_path=str(original_path),
                content_hash=content_hash,
            )
        except Exception:
            if not _remove_resume_upload(original_path):
                with mysql_connection() as cleanup_connection:
                    ResumeRepository(cleanup_connection).enqueue_file_cleanup(
                        str(original_path)
                    )
            raise

    background_tasks.add_task(parse_resume_upload_task, task.id, current_user.id)
    return _parse_task_response(task, resumes)


@router.get("/upload-tasks/{task_id}", response_model=ResumeParseTaskResponse)
def get_resume_upload_task(
    task_id: int,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
) -> ResumeParseTaskResponse:
    task = resumes.get_parse_task_for_user(task_id, current_user.id)
    if task is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return _parse_task_response(task, resumes)


@router.get(
    "/job-match-tasks/{task_id}",
    response_model=JobMatchAnalysisTaskResponse,
)
def get_job_match_analysis_task(
    task_id: int,
    current_user: UserRecord = CurrentUserDep,
    tasks: JobMatchAnalysisTaskRepository = JobMatchTaskRepositoryDep,
) -> JobMatchAnalysisTaskResponse:
    task = tasks.get_task_for_user(task_id, current_user.id)
    if task is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return _job_match_task_response(task)


@router.get("/{resume_id}", response_model=ResumeDetailResponse)
def get_resume_detail(
    resume_id: int,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
) -> ResumeDetailResponse:
    resume = resumes.get_detail_for_user(resume_id, current_user.id)
    if resume is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return _to_resume_detail(resume)


@router.post(
    "/{resume_id}/job-match-analysis",
    response_model=JobMatchAnalysisTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_resume_job_match_analysis(
    resume_id: int,
    background_tasks: BackgroundTasks,
    request: JobMatchAnalysisRequest,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
    tasks: JobMatchAnalysisTaskRepository = JobMatchTaskRepositoryDep,
) -> JobMatchAnalysisTaskResponse:
    require_external_model_consent(current_user)
    resume = resumes.get_detail_for_user(resume_id, current_user.id)
    if resume is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    if resume.parse_status != "parsed":
        raise AppError(ErrorCode.CONFLICT, status.HTTP_409_CONFLICT)
    request_hash = sha256(
        (
            f"{resume_id}\0{request.target_position}\0{request.job_description}"
        ).encode()
    ).hexdigest()
    with usage_limiter.guard(current_user.id, "job_match_analysis_enqueue"):
        task = tasks.create_or_get_active_task(
            user_id=current_user.id,
            resume_id=resume_id,
            target_position=request.target_position,
            job_description=request.job_description,
            request_hash=request_hash,
        )
        tasks.connection.commit()
    if task is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    background_tasks.add_task(run_job_match_analysis_task, task.id)
    return _job_match_task_response(task)


@router.patch("/{resume_id}", response_model=ResumeDetailResponse)
def rename_resume(
    resume_id: int,
    request: ResumeUpdateRequest,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
    ) -> ResumeDetailResponse:
    name = request.name.strip()
    if not name:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    resume = resumes.rename_for_user(resume_id, current_user.id, name)
    if resume is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return _to_resume_detail(resume)


@router.post("/{resume_id}/default", response_model=ResumeDetailResponse)
def set_default_resume(
    resume_id: int,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
) -> ResumeDetailResponse:
    resume = resumes.set_default_for_user(resume_id, current_user.id)
    if resume is None:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
    return _to_resume_detail(resume)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int,
    current_user: UserRecord = CurrentUserDep,
    service: ResumeService = ResumeServiceDep,
) -> None:
    service.delete_resume(resume_id=resume_id, user_id=current_user.id)


def find_duplicate_resume(
    content_hash: str,
    user_id: int,
    resumes: ResumeRepository,
) -> ResumeRecord | None:
    # Legacy rows can have a NULL content_hash; avoid re-reading historical files here.
    return resumes.get_by_content_hash(user_id, content_hash)


def resume_content_hash(content: bytes) -> str:
    # Parser-versioned hashes allow corrected parsing logic to reprocess an unchanged file once.
    return sha256(RESUME_PARSE_VERSION + content).hexdigest()


def parse_resume_upload_task(
    task_id: int,
    user_id: int | None = None,
    *,
    already_claimed: bool = False,
) -> None:
    task: ResumeParseTaskRecord | None = None
    heartbeat: tuple[Event, Thread] | None = None
    try:
        with mysql_connection() as connection:
            repository = ResumeRepository(connection)
            task = (
                repository.get_parse_task_for_user(task_id, user_id)
                if user_id is not None
                else repository.get_parse_task(task_id)
            )
            if task is None:
                return
            if task.status == "pending":
                if not repository.mark_parse_task_processing(task_id):
                    return
                connection.commit()
                task = repository.get_parse_task(task_id)
            elif task.status != "processing" or not already_claimed:
                return

        if task is None:
            return
        heartbeat = _start_resume_parse_task_heartbeat(task)
        try:
            with usage_limiter.guard(task.user_id, "resume_upload"):
                with mysql_connection() as connection:
                    ensure_external_model_consent(connection, task.user_id)
                parser = ResumeParserService(llm_client=get_llm_client())
                parse_path = Path(task.original_file_path)
                if resume_content_hash(parse_path.read_bytes()) != task.content_hash:
                    raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)
                structured_data = parser.parse(parse_path)
            with mysql_connection() as connection:
                repository = ResumeRepository(connection)
                if task.processing_token is None:
                    return
                repository.complete_parse_task(
                    task_id,
                    task.processing_token,
                    structured_data=structured_data,
                )
        finally:
            _stop_resume_parse_task_heartbeat(heartbeat)
            heartbeat = None
    except Exception:
        error_id = uuid4().hex[:12]
        LOGGER.exception(
            "resume parse task failed",
            extra={"task_id": task_id, "error_id": error_id},
        )
        _stop_resume_parse_task_heartbeat(heartbeat)
        cleanup_required = (
            task is not None
            and not _remove_resume_upload(Path(task.original_file_path))
        )
        if task is not None and task.processing_token is not None:
            with mysql_connection() as connection:
                repository = ResumeRepository(connection)
                repository.mark_parse_task_failed(
                    task_id,
                    f"简历解析失败，请稍后重试。（错误编号：{error_id}）",
                    task.processing_token,
                )
                if cleanup_required:
                    repository.enqueue_file_cleanup(task.original_file_path)


def _start_resume_parse_task_heartbeat(
    task: ResumeParseTaskRecord,
) -> tuple[Event, Thread] | None:
    if task.processing_token is None:
        return None
    stop_event = Event()
    timeout_seconds = max(1, get_settings().usage_limit_active_timeout_seconds)
    interval = max(1, min(30, timeout_seconds // 3))

    def _heartbeat_loop() -> None:
        while not stop_event.wait(interval):
            try:
                with mysql_connection() as connection:
                    alive = ResumeRepository(connection).heartbeat_parse_task(
                        task.id,
                        task.processing_token or "",
                    )
                if not alive:
                    return
            except Exception:
                continue

    thread = Thread(target=_heartbeat_loop, name=f"resume-task-heartbeat-{task.id}", daemon=True)
    thread.start()
    return stop_event, thread


def _stop_resume_parse_task_heartbeat(heartbeat: tuple[Event, Thread] | None) -> None:
    if heartbeat is None:
        return
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=1)


def _remove_resume_upload(path: Path) -> bool:
    return delete_resume_file(str(path), resolve_upload_dir())


def run_job_match_analysis_task(
    task_id: int,
    *,
    already_claimed: bool = False,
) -> None:
    task: JobMatchAnalysisTaskRecord | None = None
    heartbeat: tuple[Event, Thread] | None = None
    try:
        with mysql_connection() as connection:
            repository = JobMatchAnalysisTaskRepository(connection)
            task = repository.get_task(task_id)
            if task is None:
                return
            if task.status == "pending":
                if not repository.mark_processing(task_id):
                    return
                connection.commit()
                task = repository.get_task(task_id)
            elif task.status != "processing" or not already_claimed:
                return
        if task is None or task.processing_token is None:
            return

        heartbeat = _start_job_match_task_heartbeat(task)
        with mysql_connection() as connection:
            ensure_external_model_consent(connection, task.user_id)
            result = JobMatchAnalysisService(
                ResumeRepository(connection),
                get_llm_client(),
            ).analyze(
                resume_id=task.resume_id,
                user_id=task.user_id,
                target_position=task.target_position,
                job_description=task.job_description,
            )
        with mysql_connection() as connection:
            completed = JobMatchAnalysisTaskRepository(connection).mark_completed(
                task.id,
                task.processing_token,
                result.model_dump(mode="json"),
            )
        if not completed:
            raise RuntimeError(f"job match task {task.id} lost its processing lease")
    except AppError as exc:
        _mark_job_match_task_failed(task, exc.code.value, exc.message)
    except Exception:
        error_id = uuid4().hex[:12]
        LOGGER.exception(
            "job match analysis task failed",
            extra={"task_id": task_id, "error_id": error_id},
        )
        _mark_job_match_task_failed(
            task,
            ErrorCode.INTERNAL_ERROR.value,
            f"岗位匹配分析失败，请稍后重试。（错误编号：{error_id}）",
        )
    finally:
        _stop_resume_parse_task_heartbeat(heartbeat)


def _mark_job_match_task_failed(
    task: JobMatchAnalysisTaskRecord | None,
    error_code: str,
    error_message: str,
) -> None:
    if task is None or task.processing_token is None:
        return
    with mysql_connection() as connection:
        JobMatchAnalysisTaskRepository(connection).mark_failed(
            task.id,
            task.processing_token,
            error_code=error_code,
            error_message=error_message,
        )


def _start_job_match_task_heartbeat(
    task: JobMatchAnalysisTaskRecord,
) -> tuple[Event, Thread]:
    stop_event = Event()
    timeout_seconds = max(1, get_settings().interview_task_processing_timeout_seconds)
    interval = max(1, min(30, timeout_seconds // 3))

    def _heartbeat_loop() -> None:
        while not stop_event.wait(interval):
            try:
                with mysql_connection() as connection:
                    alive = JobMatchAnalysisTaskRepository(connection).heartbeat(
                        task.id,
                        task.processing_token or "",
                    )
                if not alive:
                    return
            except Exception:
                LOGGER.warning(
                    "job match task heartbeat failed",
                    extra={"task_id": task.id},
                    exc_info=True,
                )

    thread = Thread(
        target=_heartbeat_loop,
        name=f"job-match-task-heartbeat-{task.id}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


class JobMatchAnalysisTaskRunner:
    def run_once(self) -> bool:
        settings = get_settings()
        with mysql_connection() as connection:
            task = JobMatchAnalysisTaskRepository(connection).claim_due_task(
                settings.interview_task_processing_timeout_seconds
            )
        if task is None:
            return False
        run_job_match_analysis_task(task.id, already_claimed=True)
        return True


def start_job_match_analysis_task_runner() -> asyncio.Task[None]:
    settings = get_settings()

    async def _loop() -> None:
        runner = JobMatchAnalysisTaskRunner()
        while True:
            try:
                await asyncio.to_thread(runner.run_once)
                record_runner_success("job_match_analysis")
            except Exception as exc:
                record_runner_failure("job_match_analysis", exc)
                LOGGER.exception("job match analysis task runner iteration failed")
            await asyncio.sleep(max(1, settings.memory_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_job_match_analysis_task_runner(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


class ResumeParseTaskRunner:
    def run_once(self) -> bool:
        settings = get_settings()
        with mysql_connection() as connection:
            repository = ResumeRepository(connection)
            stale_paths = repository.fail_stale_parse_tasks(
                settings.usage_limit_active_timeout_seconds
            )
            cleanup_task = repository.claim_due_file_cleanup(
                settings.usage_limit_active_timeout_seconds
            )
            task = repository.claim_due_parse_task(
                processing_timeout_seconds=settings.usage_limit_active_timeout_seconds,
            )
        for path in stale_paths:
            if not _remove_resume_upload(Path(path)):
                with mysql_connection() as connection:
                    ResumeRepository(connection).enqueue_file_cleanup(path)
        if cleanup_task is not None:
            _process_file_cleanup_task(cleanup_task)
        if task is None:
            return cleanup_task is not None or bool(stale_paths)
        parse_resume_upload_task(task.id, task.user_id, already_claimed=True)
        return True


def _process_file_cleanup_task(task: FileCleanupTaskRecord) -> None:
    if task.processing_token is None:
        return
    deleted = _remove_resume_upload(Path(task.original_file_path))
    with mysql_connection() as connection:
        repository = ResumeRepository(connection)
        if deleted:
            repository.complete_file_cleanup(task.id, task.processing_token)
        else:
            repository.retry_file_cleanup(task, "file_is_temporarily_unavailable")


def start_resume_parse_task_runner() -> asyncio.Task[None]:
    settings = get_settings()

    async def _loop() -> None:
        runner = ResumeParseTaskRunner()
        while True:
            try:
                await asyncio.to_thread(runner.run_once)
                record_runner_success("resume_parse")
            except Exception as exc:
                record_runner_failure("resume_parse", exc)
                LOGGER.exception("resume parse task runner iteration failed")
            await asyncio.sleep(max(1, settings.memory_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_resume_parse_task_runner(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _parse_task_response(
    task: ResumeParseTaskRecord,
    resumes: ResumeRepository,
) -> ResumeParseTaskResponse:
    structured_data: StructuredResumeData | None = None
    if task.resume_id is not None and task.status == "completed":
        resume = resumes.get_detail_for_user(task.resume_id, task.user_id)
        if resume is not None:
            structured_data = StructuredResumeData.model_validate(resume.structured_data)
    return ResumeParseTaskResponse(
        task_id=task.id,
        status=task.status,
        resume_id=task.resume_id,
        structured_data=structured_data,
        error_message=task.error_message,
    )


def _job_match_task_response(
    task: JobMatchAnalysisTaskRecord,
) -> JobMatchAnalysisTaskResponse:
    result = (
        JobMatchAnalysisResponse.model_validate(task.result)
        if task.status == "completed" and task.result is not None
        else None
    )
    return JobMatchAnalysisTaskResponse(
        task_id=task.id,
        status=task.status,
        result=result,
        error_code=task.error_code,
        error_message=task.error_message,
    )


def _to_resume_detail(resume: ResumeDetailRecord) -> ResumeDetailResponse:
    return ResumeDetailResponse(
        id=resume.id,
        name=resume.name,
        uploaded_at=resume.uploaded_at,
        last_used_at=resume.last_used_at,
        parse_status=resume.parse_status,
        is_default=resume.is_default,
        structured_data=StructuredResumeData.model_validate(resume.structured_data),
    )
