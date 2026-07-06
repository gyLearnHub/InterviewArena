from pathlib import Path
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.mysql import mysql_connection
from app.services.avatar_storage import resolve_avatar_upload_dir
from app.services.resume_parser import resolve_upload_dir

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check() -> JSONResponse:
    checks: dict[str, dict[str, Any]] = {
        "settings": {"status": "ok"},
        "database": {"status": "ok"},
        "llm": {"status": "ok"},
        "uploads": {"status": "ok"},
        "avatars": {"status": "ok"},
    }

    try:
        settings = get_settings()
    except Exception as exc:
        checks["settings"] = _failed_check(exc)
        return _readiness_response(checks)

    if not settings.deepseek_api_key:
        checks["llm"] = {"status": "degraded", "reason": "DEEPSEEK_API_KEY is not configured"}

    try:
        with mysql_connection(settings.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ready")
                cursor.fetchone()
    except Exception as exc:
        checks["database"] = _failed_check(exc)

    upload_dir = resolve_upload_dir(settings)
    avatar_upload_dir = resolve_avatar_upload_dir(settings)
    checks["uploads"] = _directory_check(upload_dir)
    checks["avatars"] = _directory_check(avatar_upload_dir)

    return _readiness_response(checks)


def _readiness_response(checks: dict[str, dict[str, Any]]) -> JSONResponse:
    has_failed = any(item["status"] == "failed" for item in checks.values())
    overall_status = "failed" if has_failed else "ok"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE if has_failed else status.HTTP_200_OK
    return JSONResponse(
        status_code=status_code,
        content={"status": overall_status, "checks": checks},
    )


def _directory_check(path: Path) -> dict[str, Any]:
    target = path if path.exists() else path.parent
    if target.exists() and target.is_dir():
        return {"status": "ok", "path": str(path)}
    return {"status": "failed", "path": str(path), "reason": "directory is not available"}


def _failed_check(exc: Exception) -> dict[str, str]:
    return {"status": "failed", "reason": exc.__class__.__name__}
