import asyncio
import contextlib
from importlib import import_module
from typing import Any

from app.core.config import get_settings
from app.db.mysql import mysql_connection
from app.repositories.evaluations import EvaluationRepository
from app.repositories.interviews import InterviewRepository
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRecord, MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.services.llm import get_llm_client
from app.services.memory_index import MemoryIndexService
from app.services.memory_lifecycle import MemoryLifecycleService
from app.services.memory_summary import MemorySummaryService


class MemoryTaskService:
    def __init__(
        self,
        tasks: MemoryTaskRepository,
        preferences: PreferencesRepository | None = None,
    ) -> None:
        self.tasks = tasks
        self.preferences = preferences
        self.settings = get_settings()

    def create_summary_task_if_enabled(self, *, user_id: int, interview_id: int) -> None:
        if self.preferences is not None and not self.preferences.get_memory_enabled(user_id):
            return
        self.tasks.create_summary_task(
            user_id=user_id,
            interview_id=interview_id,
            max_retries=self.settings.memory_task_max_retries,
        )
        _record_harness_event(
            user_id=user_id,
            interview_id=interview_id,
            event_type="memory_summary_task_created",
            payload={},
        )

    def create_or_get_clear_task(self, *, user_id: int) -> MemoryTaskRecord:
        return self.tasks.create_or_get_clear_task(
            user_id=user_id,
            max_retries=self.settings.memory_task_max_retries,
        )

    def latest_clear_task(self, user_id: int) -> MemoryTaskRecord | None:
        return self.tasks.latest_clear_task(user_id)


class MemoryTaskRunner:
    def run_once(self) -> bool:
        task = self._claim_due_task()
        if task is None:
            return False

        try:
            with mysql_connection() as connection:
                tasks = MemoryTaskRepository(connection)
                result = self._handle_task(connection, task)
                tasks.mark_completed(task.id, result)
            if task.interview_id is not None and task.user_id is not None:
                _record_harness_event(
                    user_id=task.user_id,
                    interview_id=task.interview_id,
                    event_type="memory_task_completed",
                    payload={"task_type": task.task_type, "result": result},
                )
        except Exception as exc:
            with mysql_connection() as connection:
                tasks = MemoryTaskRepository(connection)
                tasks.mark_failed_or_retry(task, str(exc) or exc.__class__.__name__)
            if task.interview_id is not None and task.user_id is not None:
                _record_harness_event(
                    user_id=task.user_id,
                    interview_id=task.interview_id,
                    event_type="memory_task_failed",
                    payload={
                        "task_type": task.task_type,
                        "error": str(exc) or exc.__class__.__name__,
                    },
                )
        return True

    def _claim_due_task(self) -> MemoryTaskRecord | None:
        with mysql_connection() as connection:
            return MemoryTaskRepository(connection).claim_due_task(
                processing_timeout_seconds=get_settings().memory_task_processing_timeout_seconds,
            )

    def _handle_task(self, connection: Any, task: MemoryTaskRecord) -> dict[str, Any]:
        memories = MemoryRepository(connection)
        lifecycle = MemoryLifecycleService(memories, MemoryIndexService(memories))
        if task.task_type == "memory_clear":
            if task.user_id is None:
                raise ValueError("memory_clear requires user_id")
            deleted_count = lifecycle.clear_user_candidate_memories(task.user_id)
            return {"deleted_count": deleted_count}
        if task.task_type == "memory_summary":
            if task.user_id is None or task.interview_id is None:
                raise ValueError("memory_summary requires user_id and interview_id")
            if not PreferencesRepository(connection).get_memory_enabled(task.user_id):
                return {"skipped": "memory_disabled"}
            summary = MemorySummaryService(
                interview_repository=InterviewRepository(connection),
                evaluation_repository=EvaluationRepository(connection),
                lifecycle_service=lifecycle,
                llm_client=get_llm_client(),
            )
            return summary.summarize_interview(
                user_id=task.user_id,
                interview_id=task.interview_id,
            )
        raise ValueError(f"unsupported memory task type: {task.task_type}")


def start_memory_task_runner() -> asyncio.Task[None]:
    settings = get_settings()

    async def _loop() -> None:
        runner = MemoryTaskRunner()
        while True:
            try:
                await asyncio.to_thread(runner.run_once)
            except Exception:
                pass
            await asyncio.sleep(max(1, settings.memory_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_memory_task_runner(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _record_harness_event(
    *,
    user_id: int,
    interview_id: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    try:
        module = import_module("app.harness.execution")
    except Exception:
        return
    service = None
    for factory_name in ("get_harness_execution_service", "get_execution_service"):
        factory = getattr(module, factory_name, None)
        if callable(factory):
            service = factory()
            break
    if service is None:
        service = getattr(module, "harness_execution_service", None)
    if service is None:
        return
    event_payload = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": None,
        "node_type": "memory_write_tracker",
        "event_type": event_type,
        "payload": payload,
    }
    for method_name in ("record_event", "create_event", "trace_event"):
        method = getattr(service, method_name, None)
        if callable(method):
            method(**event_payload)
            return
