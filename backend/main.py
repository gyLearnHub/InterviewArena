import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036 - keep a friendly direct-startup error.
    raise RuntimeError(
        "InterviewArena backend requires Python 3.11+. "
        "Start the backend with a Python 3.11+ interpreter."
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

if __package__ in {None, ""}:
    backend_root = Path(__file__).resolve().parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

from app.api.auth import router as auth_router
from app.api.autonomous_evolution import router as autonomous_evolution_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.interviews import (
    router as interviews_router,
)
from app.api.interviews import (
    start_interview_operation_task_runner,
    stop_interview_operation_task_runner,
)
from app.api.memories import router as memories_router
from app.api.notifications import router as notifications_router
from app.api.preferences import router as preferences_router
from app.api.resumes import (
    router as resumes_router,
)
from app.api.resumes import (
    start_resume_parse_task_runner,
    stop_resume_parse_task_runner,
)
from app.api.review_bookmarks import router as review_bookmarks_router
from app.api.user_feedback import router as user_feedback_router
from app.autonomous_evolution import (
    start_evolution_task_runner,
    stop_evolution_task_runner,
)
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.mysql import mysql_connection
from app.services.avatar_storage import resolve_avatar_upload_dir
from app.services.memory_tasks import start_memory_task_runner, stop_memory_task_runner
from app.services.short_term_memory_store import close_short_term_memory_store
from scripts.migrate_v1 import migrate


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    run_startup_migrations()
    task = start_memory_task_runner()
    resume_parse_task_runner = start_resume_parse_task_runner()
    interview_operation_task_runner = start_interview_operation_task_runner()
    evolution_task_runner = start_evolution_task_runner()
    app.state.memory_task_runner = task
    app.state.resume_parse_task_runner = resume_parse_task_runner
    app.state.interview_operation_task_runner = interview_operation_task_runner
    app.state.evolution_task_runner = evolution_task_runner
    try:
        yield
    finally:
        await stop_evolution_task_runner(evolution_task_runner)
        await stop_interview_operation_task_runner(interview_operation_task_runner)
        await stop_resume_parse_task_runner(resume_parse_task_runner)
        await stop_memory_task_runner(task)
        close_short_term_memory_store()


def create_app() -> FastAPI:
    app = FastAPI(title="InterviewArena API", lifespan=lifespan)
    settings = get_settings()
    allowed_origins = [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_origin_regex=settings.cors_allowed_origin_regex or None,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_exception_handlers(app)
    avatar_upload_dir = resolve_avatar_upload_dir()
    avatar_upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/api/uploads/avatars",
        StaticFiles(directory=str(avatar_upload_dir)),
        name="avatars",
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(resumes_router, prefix="/api")
    app.include_router(interviews_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(preferences_router, prefix="/api")
    app.include_router(memories_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(user_feedback_router, prefix="/api")
    app.include_router(review_bookmarks_router, prefix="/api")
    app.include_router(autonomous_evolution_router, prefix="/api")

    return app


def run_startup_migrations() -> None:
    settings = get_settings()
    if not settings.auto_migrate_on_startup or settings.app_env.strip().lower() in {
        "test",
        "testing",
        "pytest",
    }:
        return

    with mysql_connection() as connection:
        migrate(connection)


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
