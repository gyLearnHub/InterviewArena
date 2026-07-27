from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.health import _background_queue_checks, health_check
from app.core.config import Settings, _get_env, _parse_env_file, _validate_settings
from app.core.errors import (
    ERROR_MESSAGES,
    AppError,
    ErrorCode,
    build_error_response,
    safe_error_code,
)
from app.core.observability import HTTP_METRICS
from app.db import mysql
from app.db.mysql import MySQLConnectionPool, parse_mysql_url
from fastapi.testclient import TestClient
from main import create_app


def test_health_check() -> None:
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/health" in paths
    assert "/api/metrics" in paths
    assert "/api/harness/evolution/status" in paths
    assert health_check() == {"status": "ok"}


def test_request_observability_echoes_id_and_exports_route_metrics() -> None:
    HTTP_METRICS.reset_for_tests()
    client = TestClient(create_app())

    response = client.get(
        "/api/health?ignored=secret",
        headers={"X-Request-ID": "test-request-42"},
    )
    metrics_response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-42"
    assert metrics_response.status_code == 200
    assert metrics_response.headers["Cache-Control"] == "no-store"
    assert (
        'interviewarena_http_requests_total{method="GET",'
        'route="/api/health",status_code="200"} 1'
        in metrics_response.text
    )
    assert "ignored" not in metrics_response.text
    assert "secret" not in metrics_response.text


def test_request_observability_replaces_unsafe_request_id() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/health",
        headers={"X-Request-ID": "unsafe request id"},
    )

    request_id = response.headers["X-Request-ID"]
    assert request_id != "unsafe request id"
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_unexpected_error_is_redacted_and_keeps_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()

    @app.get("/api/test-unexpected-error", include_in_schema=False)
    def unexpected_error() -> None:
        raise RuntimeError("database-password-must-not-leak")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get(
        "/api/test-unexpected-error",
        headers={"X-Request-ID": "unexpected-error-42"},
    )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "unexpected-error-42"
    assert response.json()["error"]["code"] == ErrorCode.INTERNAL_ERROR
    assert "database-password-must-not-leak" not in response.text
    assert "database-password-must-not-leak" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


class _QueueHealthCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> None:
        normalized = " ".join(sql.split()).lower()
        self.executed_sql.append(normalized)
        if (
            "from interview_operation_tasks" in normalized
            and "next_retry_at" in normalized
        ):
            raise AssertionError(
                "interview_operation_tasks has no next_retry_at column"
            )

    def fetchone(self) -> dict[str, Any]:
        return {"pending_count": 0, "oldest_pending_seconds": 0}


def test_background_queue_checks_match_interview_task_schema() -> None:
    cursor = _QueueHealthCursor()
    settings = SimpleNamespace(
        usage_limit_active_timeout_seconds=300,
        interview_task_processing_timeout_seconds=300,
        memory_task_processing_timeout_seconds=300,
    )

    checks = _background_queue_checks(cursor, settings)

    interview_sql = next(
        sql for sql in cursor.executed_sql if "from interview_operation_tasks" in sql
    )
    assert "status = 'pending'" in interview_sql
    assert "retry_wait" not in interview_sql
    assert "next_retry_at" not in interview_sql
    assert checks["interview_operation_runner"]["status"] == "ok"


def test_fixed_error_message_mapping() -> None:
    error = AppError(ErrorCode.INVALID_UPLOAD_TYPE)

    assert build_error_response(error) == {
        "error": {
            "code": ErrorCode.INVALID_UPLOAD_TYPE,
            "message": "上传格式不支持，需要重新上传哦。",
            "details": None,
        }
    }
    assert ERROR_MESSAGES[ErrorCode.LLM_API_KEY_MISSING] == "需要配置好API Key噢。"
    assert ERROR_MESSAGES[ErrorCode.NETWORK_TIMEOUT] == "当前网络环境不好，请稍后重试。"
    assert ERROR_MESSAGES[ErrorCode.TOO_MANY_REQUESTS] == "请求过于频繁，请稍后再试。"
    assert safe_error_code(RuntimeError("database-password")) == "RuntimeError"
    assert safe_error_code(AppError(ErrorCode.NETWORK_TIMEOUT)) == "NETWORK_TIMEOUT"


def test_parse_mysql_url() -> None:
    config = parse_mysql_url(
        "mysql+pymysql://user:pass@localhost:3307/interview_arena?charset=utf8mb4"
    )

    assert config.host == "localhost"
    assert config.port == 3307
    assert config.user == "user"
    assert config.password == "pass"
    assert config.database == "interview_arena"
    assert config.charset == "utf8mb4"


class _PooledConnection:
    def __init__(self) -> None:
        self.open = True
        self.ping_count = 0
        self.close_count = 0

    def ping(self) -> None:
        self.ping_count += 1

    def close(self) -> None:
        self.open = False
        self.close_count += 1


def test_mysql_pool_reuses_and_closes_bounded_connections() -> None:
    created: list[_PooledConnection] = []

    def factory() -> _PooledConnection:
        connection = _PooledConnection()
        created.append(connection)
        return connection

    pool = MySQLConnectionPool(
        max_size=1,
        acquire_timeout_seconds=1,
        connection_factory=factory,
    )

    first = pool.acquire()
    pool.release(first)
    second = pool.acquire()

    assert second is first
    assert len(created) == 1
    assert first.ping_count == 2
    pool.release(second)
    pool.close()
    assert first.close_count == 1


def test_create_connection_sets_explicit_network_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_connect(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    import pymysql

    monkeypatch.setattr(pymysql, "connect", fake_connect)
    monkeypatch.setattr(
        mysql,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="mysql://u:p@127.0.0.1/db",
            mysql_connect_timeout_seconds=4,
            mysql_read_timeout_seconds=20,
            mysql_write_timeout_seconds=21,
        ),
    )

    mysql.create_connection()

    assert captured["connect_timeout"] == 4
    assert captured["read_timeout"] == 20
    assert captured["write_timeout"] == 21


def test_parse_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# local config",
                "DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/interview_arena",
                "JWT_ALGORITHM='HS256'",
                "",
            ]
        ),
        encoding="utf-8",
    )

    values = _parse_env_file(env_file)

    assert values["DATABASE_URL"].startswith("mysql+pymysql://user:pass@")
    assert values["JWT_ALGORITHM"] == "HS256"


def test_test_environment_does_not_inherit_local_env_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    monkeypatch.setattr(
        "app.core.config._file_env",
        lambda: {"AUTH_COOKIE_SECURE": "false"},
    )

    assert _get_env("AUTH_COOKIE_SECURE", "true") == "true"


def test_cookie_cors_configuration_rejects_wildcard_origin() -> None:
    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        _validate_settings(
            Settings(
                app_env="test",
                cors_allowed_origins="*",
            )
        )


def test_multiple_replicas_reject_local_storage() -> None:
    with pytest.raises(RuntimeError, match="shared_filesystem"):
        _validate_settings(
            Settings(
                app_env="test",
                deployment_replica_count=2,
                storage_backend="local",
            )
        )


def test_multiple_replicas_accept_shared_paths_without_local_chroma(
    tmp_path: Path,
) -> None:
    shared_root = tmp_path.resolve()

    _validate_settings(
        Settings(
            app_env="test",
            deployment_replica_count=2,
            storage_backend="shared_filesystem",
            shared_storage_root=str(shared_root),
            upload_dir=str(shared_root / "resumes"),
            avatar_upload_dir=str(shared_root / "avatars"),
            chroma_enabled=False,
        )
    )


def test_multiple_replicas_reject_local_chroma(tmp_path: Path) -> None:
    shared_root = tmp_path.resolve()

    with pytest.raises(RuntimeError, match="CHROMA_ENABLED"):
        _validate_settings(
            Settings(
                app_env="test",
                deployment_replica_count=2,
                storage_backend="shared_filesystem",
                shared_storage_root=str(shared_root),
                upload_dir=str(shared_root / "resumes"),
                avatar_upload_dir=str(shared_root / "avatars"),
                chroma_enabled=True,
            )
        )
