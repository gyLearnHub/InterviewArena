import asyncio
import contextlib
import logging
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.mysql import mysql_connection
from app.harness.events import record_harness_event
from app.repositories.evaluations import EvaluationRepository
from app.repositories.interviews import InterviewRepository
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRecord, MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.services.llm import get_llm_client
from app.services.memory_index import ChromaMemoryIndex, MemoryIndexService
from app.services.memory_lifecycle import MemoryLifecycleService
from app.services.memory_summary import MemorySummaryService
from app.services.memory_user_lock import memory_user_lock
from app.services.privacy import ensure_external_model_consent
from app.services.runner_health import record_runner_failure, record_runner_success

LOGGER = logging.getLogger(__name__)


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
        record_harness_event(
            connection=self.tasks.connection,
            user_id=user_id,
            interview_id=interview_id,
            round_id=None,
            node_type="memory_write_tracker",
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

    def retry_failed_summary_tasks_if_enabled(self, *, user_id: int) -> int:
        if self.preferences is not None and not self.preferences.get_memory_enabled(user_id):
            return 0
        return self.tasks.requeue_failed_summary_tasks(user_id)


class MemoryTaskRunner:
    def run_once(self) -> bool:
        task = self._claim_due_task()
        if task is None:
            return False
        if task.processing_token is None:
            raise RuntimeError("claimed memory task has no processing token")

        heartbeat = _start_memory_task_heartbeat(task)
        try:
            with mysql_connection() as connection:
                tasks = MemoryTaskRepository(connection)
                lock = (
                    memory_user_lock(connection, task.user_id)
                    if task.user_id is not None
                    else contextlib.nullcontext()
                )
                with lock:
                    if not tasks.owns_processing_lease(task.id, task.processing_token):
                        return True
                    result = self._handle_task(connection, task)
                    completed = tasks.mark_completed(task.id, task.processing_token, result)
                    if not completed:
                        raise RuntimeError(
                            "memory task processing lease was lost before completion"
                        )
                    if task.interview_id is not None and task.user_id is not None:
                        record_harness_event(
                            connection=connection,
                            user_id=task.user_id,
                            interview_id=task.interview_id,
                            round_id=None,
                            node_type="memory_write_tracker",
                            event_type="memory_task_completed",
                            payload={"task_type": task.task_type, "result": result},
                        )
                    connection.commit()
        except Exception as exc:
            error_id = uuid4().hex[:12]
            LOGGER.exception(
                "memory task failed",
                extra={"task_id": task.id, "error_id": error_id},
            )
            public_error = (
                exc.message
                if isinstance(exc, AppError)
                else f"记忆任务处理失败，请稍后重试。（错误编号：{error_id}）"
            )
            with mysql_connection() as connection:
                tasks = MemoryTaskRepository(connection)
                failed = tasks.mark_failed_or_retry(
                    task,
                    public_error,
                    task.processing_token,
                )
                if failed and task.interview_id is not None and task.user_id is not None:
                    record_harness_event(
                        connection=connection,
                        user_id=task.user_id,
                        interview_id=task.interview_id,
                        round_id=None,
                        node_type="memory_write_tracker",
                        event_type="memory_task_failed",
                        payload={
                            "task_type": task.task_type,
                            "error": public_error,
                        },
                    )
        finally:
            _stop_memory_task_heartbeat(heartbeat)
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
            deleted_count = lifecycle.clear_user_memories(task.user_id)
            return {"deleted_count": deleted_count}
        if task.task_type == "memory_summary":
            if task.user_id is None or task.interview_id is None:
                raise ValueError("memory_summary requires user_id and interview_id")
            if not PreferencesRepository(connection).get_memory_enabled(task.user_id):
                return {"skipped": "memory_disabled"}
            ensure_external_model_consent(connection, task.user_id)
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
        if task.task_type == "memory_vector_scope_cleanup":
            cleanup_error = ChromaMemoryIndex().delete_unscoped_memories()
            if cleanup_error not in {None, "chroma_disabled"}:
                raise RuntimeError(cleanup_error)
            return {"deleted_legacy_scope": True}
        if task.task_type == "memory_reindex":
            if task.memory_collection is None or task.memory_id is None:
                raise ValueError("memory_reindex requires memory collection and id")
            memory = memories.get(task.memory_collection, task.memory_id)
            if memory is None or memory.status != "active":
                return {"skipped": "memory_missing_or_inactive"}
            index_error = ChromaMemoryIndex().upsert(memory)
            if index_error not in {None, "chroma_disabled"}:
                memories.mark_index_failed(memory.collection, memory.id)
                raise RuntimeError(index_error)
            memories.mark_indexed(memory.collection, memory.id)
            return {
                "collection": memory.collection,
                "memory_id": memory.id,
                "indexed": True,
            }
        raise ValueError(f"unsupported memory task type: {task.task_type}")


def _start_memory_task_heartbeat(task: MemoryTaskRecord) -> tuple[Event, Thread]:
    if task.processing_token is None:
        raise RuntimeError("memory task heartbeat requires a processing token")
    stop_event = Event()
    timeout_seconds = max(1, get_settings().memory_task_processing_timeout_seconds)
    interval = max(1, min(30, timeout_seconds // 3))

    def _heartbeat_loop() -> None:
        while not stop_event.wait(interval):
            try:
                with mysql_connection() as connection:
                    alive = MemoryTaskRepository(connection).heartbeat(
                        task.id,
                        task.processing_token or "",
                    )
                if not alive:
                    return
            except Exception:
                continue

    thread = Thread(target=_heartbeat_loop, name=f"memory-task-heartbeat-{task.id}", daemon=True)
    thread.start()
    return stop_event, thread


def _stop_memory_task_heartbeat(heartbeat: tuple[Event, Thread]) -> None:
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=1)


def start_memory_task_runner() -> asyncio.Task[None]:
    settings = get_settings()

    async def _loop() -> None:
        runner = MemoryTaskRunner()
        while True:
            try:
                await asyncio.to_thread(runner.run_once)
                record_runner_success("memory")
            except Exception as exc:
                record_runner_failure("memory", exc)
                LOGGER.exception("memory task runner iteration failed")
            await asyncio.sleep(max(1, settings.memory_task_poll_seconds))

    return asyncio.create_task(_loop())


async def stop_memory_task_runner(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
