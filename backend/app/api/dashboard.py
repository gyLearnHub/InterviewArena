from typing import Any

from fastapi import APIRouter, Depends

from app.deps import DatabaseConnectionDep, get_current_user
from app.repositories.history import HistoryRepository
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRepository
from app.repositories.users import UserRecord
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_history_repository(connection: Any = DatabaseConnectionDep) -> HistoryRepository:
    return HistoryRepository(connection)


HistoryRepositoryDep = Depends(get_history_repository)
CurrentUserDep = Depends(get_current_user)


def get_dashboard_service(
    repository: HistoryRepository = HistoryRepositoryDep,
) -> DashboardService:
    return DashboardService(
        repository,
        memory_repository=MemoryRepository(repository.connection),
        memory_task_repository=MemoryTaskRepository(repository.connection),
    )


DashboardServiceDep = Depends(get_dashboard_service)


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    current_user: UserRecord = CurrentUserDep,
    service: DashboardService = DashboardServiceDep,
) -> DashboardSummary:
    return service.get_summary(current_user)
