from __future__ import annotations

from typing import Any, cast

from app.repositories.evolution import EvolutionRepository


def resolve_active_version_bundle_id(
    repository: Any,
    *,
    job_family: str | None = None,
    developer_user_id: int | None = None,
) -> int | None:
    evolution_repository = _evolution_repository(repository)
    if evolution_repository is None:
        return None
    bundle = None
    if developer_user_id is not None:
        bundle = evolution_repository.get_active_version_bundle(
            scope_type="developer_canary",
            scope_key=str(developer_user_id),
        )
    if bundle is None and job_family:
        bundle = evolution_repository.get_active_version_bundle(
            scope_type="job_family",
            scope_key=job_family,
        )
    if bundle is None:
        bundle = evolution_repository.get_active_version_bundle(scope_type="global", scope_key=None)
    if bundle is None:
        bundle = evolution_repository.get_or_create_active_default_version_bundle()
    return bundle.id


def _evolution_repository(repository: Any) -> EvolutionRepository | None:
    if isinstance(repository, EvolutionRepository):
        return repository
    if hasattr(repository, "get_active_version_bundle") and hasattr(
        repository,
        "get_or_create_active_default_version_bundle",
    ):
        return cast(EvolutionRepository, repository)
    connection = getattr(repository, "connection", None)
    if connection is None:
        return None
    return EvolutionRepository(connection)
