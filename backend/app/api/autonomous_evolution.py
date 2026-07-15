from collections.abc import Iterator

from fastapi import APIRouter, Depends

from app.autonomous_evolution.repository import AutonomousEvolutionRepository
from app.core.config import get_settings
from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.users import UserRecord
from app.schemas.autonomous_evolution import AutonomousEvolutionStatusResponse

router = APIRouter(prefix="/harness/evolution", tags=["harness"])


def get_evolution_repository() -> Iterator[AutonomousEvolutionRepository]:
    with mysql_connection() as connection:
        yield AutonomousEvolutionRepository(connection)


EvolutionRepositoryDep = Depends(get_evolution_repository)
CurrentUserDep = Depends(get_current_user)


@router.get("/status", response_model=AutonomousEvolutionStatusResponse)
def get_autonomous_evolution_status(
    current_user: UserRecord = CurrentUserDep,
    repository: AutonomousEvolutionRepository = EvolutionRepositoryDep,
) -> AutonomousEvolutionStatusResponse:
    settings = get_settings()
    status = repository.get_status_for_user(current_user.id)
    return AutonomousEvolutionStatusResponse(
        enabled=settings.evolution_enabled,
        trigger_interviews=settings.evolution_trigger_interviews,
        synthetic_samples=settings.evolution_synthetic_samples,
        observation_interviews=settings.evolution_observation_interviews,
        families=status["families"],
        runs=status["runs"],
    )
