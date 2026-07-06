from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, Protocol

from app.core.config import Settings, get_settings
from app.db.mysql import mysql_connection
from app.evolution.analyzer import analyze_run
from app.evolution.triggers import EvolutionRunTrigger, build_daily_inspection_trigger
from app.repositories.evolution import EvolutionRepository

logger = logging.getLogger(__name__)


class EvolutionRunRepository(Protocol):
    def create_evolution_run(
        self,
        *,
        user_id: int | None,
        trigger_type: str,
        trigger_reason: str,
        scope_type: str,
        scope_key: str | None,
        sample_count: int,
        data_scope: dict[str, Any],
        anonymization_status: str,
        audit_metadata: dict[str, Any],
    ) -> Any:
        ... 

    def count_completed_quality_signals(self) -> int:
        ...


def run_daily_inspection(
    repository: EvolutionRunRepository,
    *,
    user_id: int | None,
    trigger_reason: str,
    sample_count: int = 0,
    sample_scope: dict[str, Any] | None = None,
    anonymization_status: str = "anonymized",
    audit_metadata: dict[str, Any] | None = None,
) -> Any:
    trigger = build_daily_inspection_trigger(
        trigger_reason=trigger_reason,
        sample_count=sample_count,
        sample_scope=sample_scope,
        anonymization_status=anonymization_status,
        audit_metadata=audit_metadata,
    )
    return create_run_from_trigger(repository, user_id=user_id, trigger=trigger)


def create_run_from_trigger(
    repository: EvolutionRunRepository,
    *,
    user_id: int | None,
    trigger: EvolutionRunTrigger,
) -> Any:
    return repository.create_evolution_run(
        user_id=user_id,
        trigger_type=trigger.trigger_type,
        trigger_reason=trigger.trigger_reason,
        scope_type=trigger.scope_type,
        scope_key=trigger.scope_key,
        sample_count=trigger.sample_count,
        data_scope=trigger.data_scope,
        anonymization_status=trigger.anonymization_status,
        audit_metadata=trigger.audit_metadata,
    )


def run_scheduled_daily_inspection_once(
    repository: EvolutionRunRepository,
    *,
    now: datetime,
    last_run_date: date | None,
    inspection_hour: int,
) -> tuple[Any | None, date | None]:
    current_date = now.date()
    if now.hour != inspection_hour or last_run_date == current_date:
        return None, last_run_date
    sample_count = repository.count_completed_quality_signals()
    result = run_daily_inspection(
        repository,
        user_id=None,
        trigger_reason=f"scheduled daily inspection for {current_date.isoformat()}",
        sample_count=sample_count,
        sample_scope={"window": "daily", "date": current_date.isoformat()},
        anonymization_status="aggregated_anonymized",
        audit_metadata={"source": "evolution_daily_scheduler"},
    )
    if _run_already_attempted(result):
        return result, current_date
    _analyze_created_run(repository, result)
    return result, current_date


def start_evolution_daily_scheduler(
    *,
    settings: Settings | None = None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> asyncio.Task[None] | None:
    resolved = settings or get_settings()
    if not resolved.evolution_daily_scheduler_enabled or resolved.app_env.lower() in {
        "test",
        "testing",
        "pytest",
    }:
        return None
    return asyncio.create_task(_daily_scheduler_loop(resolved, sleep=sleep))


async def stop_evolution_daily_scheduler(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return


async def _daily_scheduler_loop(
    settings: Settings,
    *,
    sleep: Callable[[float], Awaitable[Any]],
) -> None:
    last_run_date: date | None = None
    while True:
        try:
            _result, last_run_date = await asyncio.to_thread(
                _run_daily_scheduler_check,
                settings,
                last_run_date,
            )
        except Exception:
            logger.exception("evolution daily scheduler check failed")
        await sleep(settings.evolution_daily_scheduler_poll_seconds)


def _run_daily_scheduler_check(
    settings: Settings,
    last_run_date: date | None,
) -> tuple[Any | None, date | None]:
    with mysql_connection() as connection:
        repository = EvolutionRepository(connection)
        return run_scheduled_daily_inspection_once(
            repository,
            now=datetime.now(),
            last_run_date=last_run_date,
            inspection_hour=settings.evolution_daily_inspection_hour,
        )


def _analyze_created_run(repository: EvolutionRunRepository, run: Any | None) -> None:
    run_id = _run_id(run)
    if run_id is None:
        return
    analyze_run(repository, run_id)


def _run_already_attempted(run: Any | None) -> bool:
    status = _run_status(run)
    return status in {"analyzing", "candidate_generated", "completed", "failed"}


def _run_id(run: Any | None) -> int | None:
    if run is None:
        return None
    if isinstance(run, dict):
        value = run.get("id")
    else:
        value = getattr(run, "id", None)
    return int(value) if value is not None else None


def _run_status(run: Any | None) -> str | None:
    if run is None:
        return None
    if isinstance(run, dict):
        value = run.get("status")
    else:
        value = getattr(run, "status", None)
    return str(value) if value is not None else None
