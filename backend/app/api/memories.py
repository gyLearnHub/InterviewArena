from typing import Literal

from fastapi import APIRouter, Depends, Query
from starlette.status import HTTP_204_NO_CONTENT

from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRecord, MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.users import UserRecord
from app.schemas.memory import ManagedMemoryListResponse, MemoryClearStatusResponse
from app.services.memory_index import MemoryIndexService
from app.services.memory_management import MemoryManagementService
from app.services.memory_tasks import MemoryTaskService
from app.services.memory_user_lock import memory_user_lock

router = APIRouter(prefix="/memories", tags=["memories"])
CurrentUserDep = Depends(get_current_user)


@router.get("", response_model=ManagedMemoryListResponse)
def list_memories(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    query: str = Query(default="", max_length=128),
    memory_type: str | None = Query(default=None, max_length=64),
    status_filter: Literal[
        "active",
        "pending_review",
        "superseded",
        "archived",
    ]
    | None = Query(default=None, alias="status"),
    current_user: UserRecord = CurrentUserDep,
) -> ManagedMemoryListResponse:
    with mysql_connection() as connection:
        repository = MemoryRepository(connection)
        service = MemoryManagementService(repository)
        return service.list_memories(
            current_user,
            limit=limit,
            offset=offset,
            query=query,
            memory_type=memory_type,
            status_filter=status_filter,
        )


@router.delete("", response_model=MemoryClearStatusResponse)
def clear_memories(current_user: UserRecord = CurrentUserDep) -> MemoryClearStatusResponse:
    with mysql_connection() as connection:
        with memory_user_lock(connection, current_user.id):
            memory_repository = MemoryRepository(connection)
            task_repository = MemoryTaskRepository(connection)
            task_repository.cancel_summary_tasks_for_user(current_user.id)
            memory_repository.mark_user_memories_pending_delete(current_user.id)
            service = MemoryTaskService(
                task_repository,
                PreferencesRepository(connection),
            )
            task = service.create_or_get_clear_task(user_id=current_user.id)
            connection.commit()
        return _clear_status_response(task)


@router.get("/clear-status", response_model=MemoryClearStatusResponse)
def get_clear_status(current_user: UserRecord = CurrentUserDep) -> MemoryClearStatusResponse:
    with mysql_connection() as connection:
        service = MemoryTaskService(MemoryTaskRepository(connection))
        task = service.latest_clear_task(current_user.id)
    if task is None:
        return MemoryClearStatusResponse(task_id=None, status="idle")
    return _clear_status_response(task)


@router.delete("/{memory_id}", status_code=HTTP_204_NO_CONTENT)
def delete_memory(memory_id: int, current_user: UserRecord = CurrentUserDep) -> None:
    with mysql_connection() as connection:
        repository = MemoryRepository(connection)
        service = MemoryManagementService(
            repository,
            MemoryIndexService(repository),
        )
        service.delete_memory(current_user, memory_id)


def _clear_status_response(task: MemoryTaskRecord) -> MemoryClearStatusResponse:
    result = task.result or {}
    deleted_count = result.get("deleted_count")
    return MemoryClearStatusResponse(
        task_id=task.id,
        status=task.status,  # type: ignore[arg-type]
        deleted_count=int(deleted_count) if isinstance(deleted_count, int) else 0,
        error_message=task.error_message,
    )
