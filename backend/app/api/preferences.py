from fastapi import APIRouter, Depends

from app.db.mysql import mysql_connection
from app.deps import get_current_user
from app.repositories.preferences import PreferencesRepository
from app.repositories.users import UserRecord
from app.schemas.preferences import UserPreferencesResponse, UserPreferencesUpdate

router = APIRouter(prefix="/user/preferences", tags=["preferences"])
CurrentUserDep = Depends(get_current_user)


@router.get("", response_model=UserPreferencesResponse)
def get_preferences(current_user: UserRecord = CurrentUserDep) -> UserPreferencesResponse:
    return UserPreferencesResponse(memory_enabled=current_user.memory_enabled)


@router.patch("", response_model=UserPreferencesResponse)
def update_preferences(
    request: UserPreferencesUpdate,
    current_user: UserRecord = CurrentUserDep,
) -> UserPreferencesResponse:
    with mysql_connection() as connection:
        repository = PreferencesRepository(connection)
        memory_enabled = repository.update_memory_enabled(
            current_user.id,
            request.memory_enabled,
        )
    return UserPreferencesResponse(memory_enabled=memory_enabled)
