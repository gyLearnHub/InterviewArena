import asyncio
import contextlib
import logging

from app.core.config import get_settings
from app.db.mysql import mysql_connection
from app.repositories.cache_cleanup_tasks import (
    CacheCleanupTaskRecord,
    CacheCleanupTaskRepository,
)
from app.services.runner_health import record_runner_failure, record_runner_success
from app.services.short_term_memory_store import get_short_term_memory_store

LOGGER = logging.getLogger(__name__)


class CacheCleanupTaskRunner:
    def run_once(self) -> bool:
        settings = get_settings()
        with mysql_connection() as connection:
            task = CacheCleanupTaskRepository(connection).claim_due(
                settings.usage_limit_active_timeout_seconds
            )
        if task is None:
            return False
        _process_task(task)
        return True


def _process_task(task: CacheCleanupTaskRecord) -> None:
    if task.processing_token is None:
        return
    try:
        get_short_term_memory_store().delete_many(
            task.user_id,
            task.interview_ids,
        )
    except Exception as exc:
        LOGGER.warning(
            "short-term memory cache cleanup will be retried",
            exc_info=True,
            extra={"task_id": task.id, "user_id": task.user_id},
        )
        with mysql_connection() as connection:
            CacheCleanupTaskRepository(connection).retry(task, str(exc))
        return
    with mysql_connection() as connection:
        CacheCleanupTaskRepository(connection).complete(
            task.id,
            task.processing_token,
        )


def start_cache_cleanup_task_runner() -> asyncio.Task[None]:
    settings = get_settings()

    async def _loop() -> None:
        runner = CacheCleanupTaskRunner()
        while True:
            try:
                await asyncio.to_thread(runner.run_once)
                record_runner_success("cache_cleanup")
            except Exception as exc:
                record_runner_failure("cache_cleanup", exc)
                LOGGER.exception("cache cleanup task runner iteration failed")
            await asyncio.sleep(max(1, settings.memory_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_cache_cleanup_task_runner(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
