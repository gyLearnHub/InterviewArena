from pathlib import Path

import pytest
from app.api.health import health_check
from app.core.config import Settings, _parse_env_file, _validate_settings
from app.core.errors import (
    ERROR_MESSAGES,
    AppError,
    ErrorCode,
    build_error_response,
    safe_error_code,
)
from app.db.mysql import parse_mysql_url
from main import create_app


def test_health_check() -> None:
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/health" in paths
    assert "/api/harness/evolution/status" in paths
    assert health_check() == {"status": "ok"}


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


def test_cookie_cors_configuration_rejects_wildcard_origin() -> None:
    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        _validate_settings(
            Settings(
                app_env="test",
                cors_allowed_origins="*",
            )
        )
