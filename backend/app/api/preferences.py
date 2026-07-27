from typing import Any

from fastapi import APIRouter, Depends

from app.deps import DatabaseConnectionDep, get_current_user
from app.repositories.preferences import PreferencesRepository
from app.repositories.users import CURRENT_PRIVACY_VERSION, UserRecord
from app.schemas.preferences import UserPreferencesResponse, UserPreferencesUpdate

router = APIRouter(prefix="/user/preferences", tags=["preferences"])
CurrentUserDep = Depends(get_current_user)


@router.get("", response_model=UserPreferencesResponse)
def get_preferences(current_user: UserRecord = CurrentUserDep) -> UserPreferencesResponse:
    return UserPreferencesResponse(
        memory_enabled=current_user.memory_enabled,
        external_model_consent=current_user.external_model_consent,
        privacy_version=CURRENT_PRIVACY_VERSION,
    )


@router.patch("", response_model=UserPreferencesResponse)
def update_preferences(
    request: UserPreferencesUpdate,
    current_user: UserRecord = CurrentUserDep,
    connection: Any = DatabaseConnectionDep,
) -> UserPreferencesResponse:
    repository = PreferencesRepository(connection)
    memory_enabled = (
        repository.update_memory_enabled(current_user.id, request.memory_enabled)
        if request.memory_enabled is not None
        else current_user.memory_enabled
    )
    external_model_consent = (
        repository.update_external_model_consent(
            current_user.id,
            request.external_model_consent,
        )
        if request.external_model_consent is not None
        else current_user.external_model_consent
    )
    return UserPreferencesResponse(
        memory_enabled=memory_enabled,
        external_model_consent=external_model_consent,
        privacy_version=CURRENT_PRIVACY_VERSION,
    )
