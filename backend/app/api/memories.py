from fastapi import APIRouter, Depends

from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRecord, MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.users import UserRecord
from app.schemas.memory import MemoryClearStatusResponse
from app.services.memory_tasks import MemoryTaskService

router = APIRouter(prefix="/memories", tags=["memories"])
CurrentUserDep = Depends(get_current_user)


@router.delete("", response_model=MemoryClearStatusResponse)
def clear_memories(current_user: UserRecord = CurrentUserDep) -> MemoryClearStatusResponse:
    with mysql_connection() as connection:
        memory_repository = MemoryRepository(connection)
        memory_repository.mark_user_candidate_pending_delete(current_user.id)
        service = MemoryTaskService(
            MemoryTaskRepository(connection),
            PreferencesRepository(connection),
        )
        task = service.create_or_get_clear_task(user_id=current_user.id)
        return _clear_status_response(task)


@router.get("/clear-status", response_model=MemoryClearStatusResponse)
def get_clear_status(current_user: UserRecord = CurrentUserDep) -> MemoryClearStatusResponse:
    with mysql_connection() as connection:
        service = MemoryTaskService(MemoryTaskRepository(connection))
        task = service.latest_clear_task(current_user.id)
    if task is None:
        return MemoryClearStatusResponse(task_id=None, status="idle")
    return _clear_status_response(task)


def _clear_status_response(task: MemoryTaskRecord) -> MemoryClearStatusResponse:
    result = task.result or {}
    deleted_count = result.get("deleted_count")
    return MemoryClearStatusResponse(
        task_id=task.id,
        status=task.status,  # type: ignore[arg-type]
        deleted_count=int(deleted_count) if isinstance(deleted_count, int) else 0,
        error_message=task.error_message,
    )
