from pathlib import Path
from typing import Protocol

from fastapi import status

from app.core.errors import AppError, ErrorCode
from app.services.resume_parser import resolve_upload_dir


class ResumeDeleteRepository(Protocol):
    def has_active_interview_dependency_for_resume(
        self,
        resume_id: int,
        user_id: int,
    ) -> bool:
        ...

    def soft_delete_for_user(self, resume_id: int, user_id: int) -> bool:
        ...

    def get_original_file_path_for_user(self, resume_id: int, user_id: int) -> str | None:
        ...


ACTIVE_INTERVIEW_DELETE_MESSAGE = "该简历仍有进行中的面试，请先结束面试后再删除。"


class ResumeService:
    def __init__(
        self,
        repository: ResumeDeleteRepository,
        upload_dir: Path | None = None,
    ) -> None:
        self.repository = repository
        self.upload_dir = upload_dir or resolve_upload_dir()

    def delete_resume(self, *, resume_id: int, user_id: int) -> None:
        if self.repository.has_active_interview_dependency_for_resume(resume_id, user_id):
            raise _active_interview_dependency_error()

        original_file_path = self.repository.get_original_file_path_for_user(
            resume_id,
            user_id,
        )
        deleted = self.repository.soft_delete_for_user(resume_id, user_id)
        if deleted:
            _delete_original_file(original_file_path, self.upload_dir)
            return

        if self.repository.has_active_interview_dependency_for_resume(resume_id, user_id):
            raise _active_interview_dependency_error()
        raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)


def _delete_original_file(original_file_path: str | None, upload_dir: Path) -> None:
    if not original_file_path:
        return
    try:
        upload_root = upload_dir.resolve()
        original_file = Path(original_file_path).resolve()
    except OSError:
        return
    if not original_file.is_relative_to(upload_root):
        return
    try:
        original_file.unlink(missing_ok=True)
    except OSError:
        return


def _active_interview_dependency_error() -> AppError:
    return AppError(
        ErrorCode.CONFLICT,
        status.HTTP_409_CONFLICT,
        message=ACTIVE_INTERVIEW_DELETE_MESSAGE,
    )
