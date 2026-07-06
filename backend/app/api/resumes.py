from collections.abc import Iterator
from contextlib import suppress
from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status

from app.core.errors import AppError, ErrorCode
from app.core.http_status import (
    HTTP_413_CONTENT_TOO_LARGE,
    HTTP_422_UNPROCESSABLE_CONTENT,
)
from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.resumes import (
    ResumeDetailRecord,
    ResumeParseTaskRecord,
    ResumeRecord,
    ResumeRepository,
)
from app.repositories.users import UserRecord
from app.schemas.resume import (
    ResumeDetailResponse,
    ResumeListItem,
    ResumeParseTaskResponse,
    ResumeUpdateRequest,
    ResumeUploadResponse,
    StructuredResumeData,
)
from app.services.llm import get_llm_client
from app.services.resume_parser import (
    MAX_RESUME_BYTES,
    ResumeParserService,
    make_resume_path,
    resolve_upload_dir,
    validate_resume_extension,
)
from app.services.usage_limits import usage_limiter

router = APIRouter(prefix="/resumes", tags=["resumes"])
ResumeFile = File(...)
CurrentUserDep = Depends(get_current_user)


def get_resume_repository() -> Iterator[ResumeRepository]:
    with mysql_connection() as connection:
        yield ResumeRepository(connection)


def get_resume_parser() -> ResumeParserService:
    return ResumeParserService(llm_client=get_llm_client())


ResumeRepositoryDep = Depends(get_resume_repository)
ResumeParserDep = Depends(get_resume_parser)


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


@router.post("/upload", response_model=ResumeUploadResponse)
def upload_resume(
    file: UploadFile = ResumeFile,
    current_user: UserRecord = CurrentUserDep,
    resumes: ResumeRepository = ResumeRepositoryDep,
    parser: ResumeParserService = ResumeParserDep,
) -> ResumeUploadResponse:
    validate_resume_extension(file.filename or "")
    content = file.file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_413_CONTENT_TOO_LARGE)

    content_hash = resume_content_hash(content)
    duplicated_resume = find_duplicate_resume(content_hash, current_user.id, resumes)
    if duplicated_resume is not None:
        if duplicated_resume.deleted_at is not None:
            duplicated_resume = resumes.restore_for_user(duplicated_resume.id, current_user.id)
            if duplicated_resume is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        return ResumeUploadResponse(
            id=duplicated_resume.id,
            structured_data=StructuredResumeData.model_validate(
                duplicated_resume.structured_data,
            ),
        )

    with usage_limiter.guard(current_user.id, "resume_upload"):
        upload_dir = resolve_upload_dir(parser.settings)
        upload_dir.mkdir(parents=True, exist_ok=True)
        original_path = make_resume_path(file.filename or "resume.docx", upload_dir)
        original_path.write_bytes(content)

        try:
            structured_data = parser.parse(original_path)
            resume = resumes.create(
                user_id=current_user.id,
                original_file_path=str(original_path),
                structured_data=structured_data,
                content_hash=content_hash,
            )
        except Exception:
            with suppress(OSError):
                original_path.unlink()
            raise

    return ResumeUploadResponse(
        id=resume.id,
        structured_data=StructuredResumeData.model_validate(resume.structured_data),
    )


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
    validate_resume_extension(file.filename or "")
    content = file.file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_413_CONTENT_TOO_LARGE)

    content_hash = resume_content_hash(content)
    duplicated_resume = find_duplicate_resume(content_hash, current_user.id, resumes)
    if duplicated_resume is not None:
        if duplicated_resume.deleted_at is not None:
            duplicated_resume = resumes.restore_for_user(duplicated_resume.id, current_user.id)
            if duplicated_resume is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        task = resumes.create_parse_task(
            user_id=current_user.id,
            original_file_path=duplicated_resume.original_file_path,
            content_hash=content_hash,
        )
        resumes.mark_parse_task_completed(task.id, duplicated_resume.id)
        completed_task = resumes.get_parse_task_for_user(task.id, current_user.id) or task
        return _parse_task_response(completed_task, resumes)

    with usage_limiter.guard(current_user.id, "resume_upload"):
        upload_dir = resolve_upload_dir(parser.settings)
        upload_dir.mkdir(parents=True, exist_ok=True)
        original_path = make_resume_path(file.filename or "resume.docx", upload_dir)
        original_path.write_bytes(content)
        task = resumes.create_parse_task(
            user_id=current_user.id,
            original_file_path=str(original_path),
            content_hash=content_hash,
        )

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
    resumes: ResumeRepository = ResumeRepositoryDep,
) -> None:
    deleted = resumes.soft_delete_for_user(resume_id, current_user.id)
    if not deleted:
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)


def find_duplicate_resume(
    content_hash: str,
    user_id: int,
    resumes: ResumeRepository,
) -> ResumeRecord | None:
    # Legacy rows can have a NULL content_hash; avoid re-reading historical files here.
    return resumes.get_by_content_hash(user_id, content_hash)


def resume_content_hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def parse_resume_upload_task(task_id: int, user_id: int) -> None:
    task: ResumeParseTaskRecord | None = None
    try:
        with mysql_connection() as connection:
            repository = ResumeRepository(connection)
            task = repository.get_parse_task_for_user(task_id, user_id)
            if task is None or not repository.mark_parse_task_processing(task_id):
                return

        parser = ResumeParserService(llm_client=get_llm_client())
        parse_path = Path(task.original_file_path)
        structured_data = parser.parse(parse_path)

        with mysql_connection() as connection:
            repository = ResumeRepository(connection)
            resume = repository.create(
                user_id=user_id,
                original_file_path=task.original_file_path,
                structured_data=structured_data,
                content_hash=task.content_hash,
            )
            repository.mark_parse_task_completed(task_id, resume.id)
    except Exception as exc:
        if task is not None:
            with suppress(OSError):
                Path(task.original_file_path).unlink()
        with mysql_connection() as connection:
            ResumeRepository(connection).mark_parse_task_failed(
                task_id,
                str(exc) or exc.__class__.__name__,
            )


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
