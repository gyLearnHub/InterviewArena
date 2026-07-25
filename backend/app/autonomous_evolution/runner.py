from __future__ import annotations

import asyncio
import contextlib
import logging
from threading import Event, Thread

from app.autonomous_evolution.engine import AutonomousEvolutionEngine
from app.autonomous_evolution.repository import AutonomousEvolutionRepository
from app.autonomous_evolution.runtime import prepare_interview_evolution_context
from app.core.config import get_settings
from app.core.errors import safe_error_code
from app.db.mysql import mysql_connection
from app.services.llm import DeepSeekLLMClient, get_llm_client

LOGGER = logging.getLogger(__name__)


class EvolutionTaskRunner:
    def run_once(self) -> bool:
        settings = get_settings()
        if not settings.evolution_enabled:
            return False
        with mysql_connection() as connection:
            repository = AutonomousEvolutionRepository(connection)
            unbound = repository.get_next_unbound_interview()
            if unbound is not None:
                bound = prepare_interview_evolution_context(
                    connection=connection,
                    llm_client=get_llm_client(),
                    user_id=int(unbound["user_id"]),
                    interview_id=int(unbound["id"]),
                    target_position=str(unbound["target_position"]),
                    job_description=(
                        str(unbound["job_description"])
                        if unbound.get("job_description") is not None
                        else None
                    ),
                )
                if bound is not None:
                    return True
            run = repository.claim_due_run(
                settings.evolution_task_processing_timeout_seconds
            )
        if run is None:
            return False
        if not run.processing_token:
            raise RuntimeError("claimed evolution run has no processing token")
        stop_heartbeat = Event()
        heartbeat_thread = Thread(
            target=_heartbeat_loop,
            args=(
                run.id,
                run.processing_token,
                settings.evolution_task_heartbeat_seconds,
                stop_heartbeat,
            ),
            name=f"evolution-heartbeat-{run.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            with mysql_connection() as connection:
                repository = AutonomousEvolutionRepository(connection)
                AutonomousEvolutionEngine(
                    repository,
                    generator_client=get_llm_client(),
                    judge_client=DeepSeekLLMClient(model_name=settings.evolution_judge_model),
                    synthetic_sample_count=settings.evolution_synthetic_samples,
                ).run(run)
        except Exception as exc:
            LOGGER.exception("autonomous evolution run %s failed", run.id)
            with mysql_connection() as connection:
                repository = AutonomousEvolutionRepository(connection)
                latest = repository.get_run(run.id)
                owned_run = (
                    latest
                    if latest is not None
                    and latest.status == "processing"
                    and latest.processing_token == run.processing_token
                    else run
                )
                repository.fail_or_retry_run(
                    owned_run,
                    safe_error_code(exc),
                )
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=max(1, settings.evolution_task_heartbeat_seconds))
        return True


def start_evolution_task_runner() -> asyncio.Task[None] | None:
    settings = get_settings()
    if not settings.evolution_enabled:
        return None

    async def _loop() -> None:
        runner = EvolutionTaskRunner()
        while True:
            try:
                handled = await asyncio.to_thread(runner.run_once)
                if not handled:
                    await asyncio.sleep(max(1, settings.evolution_task_poll_seconds))
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("autonomous evolution runner loop failed")
                await asyncio.sleep(max(1, settings.evolution_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_evolution_task_runner(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _heartbeat_loop(
    run_id: int,
    processing_token: str,
    interval_seconds: int,
    stop_event: Event,
) -> None:
    while not stop_event.wait(max(1, interval_seconds)):
        try:
            with mysql_connection() as connection:
                owned = AutonomousEvolutionRepository(connection).heartbeat_run(
                    run_id,
                    processing_token,
                )
            if not owned:
                LOGGER.warning("evolution run %s lost its processing lease", run_id)
                return
        except Exception:
            LOGGER.exception("failed to heartbeat autonomous evolution run %s", run_id)
