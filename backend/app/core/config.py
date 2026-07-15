import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHROMA_PERSIST_DIR = str(PROJECT_ROOT / "chromadb")


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    database_url: str = "mysql+pymysql://interview_arena:change_me@127.0.0.1:3306/interview_arena?charset=utf8mb4"
    jwt_secret_key: str = "change_me_to_a_long_random_secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_timeout_seconds: int = 60
    deepseek_retry_count: int = 2
    upload_dir: str = "resume"
    resume_max_text_chars: int = 30000
    resume_conversion_timeout_seconds: int = 30
    avatar_upload_dir: str = "uploads/avatars"
    embedding_model_path: str = ""
    reranker_model_path: str = ""
    embedding_device: str = "cpu"
    reranker_device: str = "cpu"
    chroma_persist_dir: str = DEFAULT_CHROMA_PERSIST_DIR
    chroma_enabled: bool = False
    memory_task_poll_seconds: int = 5
    memory_task_max_retries: int = 3
    memory_task_processing_timeout_seconds: int = 900
    memory_query_timeout_seconds: int = 3
    memory_retrieval_timeout_seconds: int = 4
    memory_enabled_default: bool = True
    memory_min_relevance_score: float = 0.15
    usage_limit_active_timeout_seconds: int = 900
    interview_task_processing_timeout_seconds: int = 900
    interview_task_heartbeat_seconds: int = 30
    evolution_enabled: bool = False
    evolution_trigger_interviews: int = 10
    evolution_synthetic_samples: int = 10
    evolution_judge_model: str = "deepseek-flash"
    evolution_task_poll_seconds: int = 5
    evolution_task_max_retries: int = 3
    evolution_task_processing_timeout_seconds: int = 3600
    evolution_task_heartbeat_seconds: int = 30
    evolution_observation_interviews: int = 5
    auto_migrate_on_startup: bool = True
    auth_cookie_name: str = "interview_arena_token"
    auth_cookie_secure: bool = True
    auth_cookie_samesite: str = "lax"
    csrf_protection_enabled: bool = True
    csrf_cookie_name: str = "interview_arena_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cors_allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    cors_allowed_origin_regex: str = r"^https?://(127\.0\.0\.1|localhost):\d+$"


def _read_int(name: str, default: int) -> int:
    value = _get_env(name, str(default))
    if value is None or value == "":
        return default
    return int(value)


def _read_float(name: str, default: float) -> float:
    value = _get_env(name, str(default))
    if value is None or value == "":
        return default
    return float(value)


def _read_bool(name: str, default: bool) -> bool:
    value = _get_env(name, "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


@lru_cache
def _file_env() -> dict[str, str]:
    backend_root = Path(__file__).resolve().parents[2]
    return _parse_env_file(backend_root / ".env")


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return _file_env().get(name, default)
    return value


@lru_cache
def get_settings() -> Settings:
    settings = Settings(
        app_env=_get_env("APP_ENV", Settings.app_env),
        database_url=_get_env("DATABASE_URL", Settings.database_url),
        jwt_secret_key=_get_env("JWT_SECRET_KEY", Settings.jwt_secret_key),
        jwt_algorithm=_get_env("JWT_ALGORITHM", Settings.jwt_algorithm),
        jwt_expire_minutes=_read_int("JWT_EXPIRE_MINUTES", Settings.jwt_expire_minutes),
        deepseek_api_key=_get_env("DEEPSEEK_API_KEY", Settings.deepseek_api_key),
        deepseek_base_url=_get_env("DEEPSEEK_BASE_URL", Settings.deepseek_base_url),
        deepseek_model=_get_env("DEEPSEEK_MODEL", Settings.deepseek_model),
        deepseek_timeout_seconds=_read_int(
            "DEEPSEEK_TIMEOUT_SECONDS",
            Settings.deepseek_timeout_seconds,
        ),
        deepseek_retry_count=_read_int("DEEPSEEK_RETRY_COUNT", Settings.deepseek_retry_count),
        upload_dir=_get_env("UPLOAD_DIR", Settings.upload_dir),
        resume_max_text_chars=_read_int(
            "RESUME_MAX_TEXT_CHARS",
            Settings.resume_max_text_chars,
        ),
        resume_conversion_timeout_seconds=_read_int(
            "RESUME_CONVERSION_TIMEOUT_SECONDS",
            Settings.resume_conversion_timeout_seconds,
        ),
        avatar_upload_dir=_get_env("AVATAR_UPLOAD_DIR", Settings.avatar_upload_dir),
        embedding_model_path=_get_env("EMBEDDING_MODEL_PATH", Settings.embedding_model_path),
        reranker_model_path=_get_env("RERANKER_MODEL_PATH", Settings.reranker_model_path),
        embedding_device=_get_env("EMBEDDING_DEVICE", Settings.embedding_device),
        reranker_device=_get_env("RERANKER_DEVICE", Settings.reranker_device),
        chroma_persist_dir=_get_env("CHROMA_PERSIST_DIR", Settings.chroma_persist_dir),
        chroma_enabled=_read_bool("CHROMA_ENABLED", Settings.chroma_enabled),
        memory_task_poll_seconds=_read_int(
            "MEMORY_TASK_POLL_SECONDS",
            Settings.memory_task_poll_seconds,
        ),
        memory_task_max_retries=_read_int(
            "MEMORY_TASK_MAX_RETRIES",
            Settings.memory_task_max_retries,
        ),
        memory_task_processing_timeout_seconds=_read_int(
            "MEMORY_TASK_PROCESSING_TIMEOUT_SECONDS",
            Settings.memory_task_processing_timeout_seconds,
        ),
        memory_query_timeout_seconds=_read_int(
            "MEMORY_QUERY_TIMEOUT_SECONDS",
            Settings.memory_query_timeout_seconds,
        ),
        memory_retrieval_timeout_seconds=_read_int(
            "MEMORY_RETRIEVAL_TIMEOUT_SECONDS",
            Settings.memory_retrieval_timeout_seconds,
        ),
        memory_enabled_default=_read_bool(
            "MEMORY_ENABLED_DEFAULT",
            Settings.memory_enabled_default,
        ),
        memory_min_relevance_score=_read_float(
            "MEMORY_MIN_RELEVANCE_SCORE",
            Settings.memory_min_relevance_score,
        ),
        usage_limit_active_timeout_seconds=_read_int(
            "USAGE_LIMIT_ACTIVE_TIMEOUT_SECONDS",
            Settings.usage_limit_active_timeout_seconds,
        ),
        interview_task_processing_timeout_seconds=_read_int(
            "INTERVIEW_TASK_PROCESSING_TIMEOUT_SECONDS",
            Settings.interview_task_processing_timeout_seconds,
        ),
        interview_task_heartbeat_seconds=_read_int(
            "INTERVIEW_TASK_HEARTBEAT_SECONDS",
            Settings.interview_task_heartbeat_seconds,
        ),
        evolution_enabled=_read_bool(
            "EVOLUTION_ENABLED",
            Settings.evolution_enabled,
        ),
        evolution_trigger_interviews=_read_int(
            "EVOLUTION_TRIGGER_INTERVIEWS",
            Settings.evolution_trigger_interviews,
        ),
        evolution_synthetic_samples=_read_int(
            "EVOLUTION_SYNTHETIC_SAMPLES",
            Settings.evolution_synthetic_samples,
        ),
        evolution_judge_model=_get_env(
            "EVOLUTION_JUDGE_MODEL",
            Settings.evolution_judge_model,
        ),
        evolution_task_poll_seconds=_read_int(
            "EVOLUTION_TASK_POLL_SECONDS",
            Settings.evolution_task_poll_seconds,
        ),
        evolution_task_max_retries=_read_int(
            "EVOLUTION_TASK_MAX_RETRIES",
            Settings.evolution_task_max_retries,
        ),
        evolution_task_processing_timeout_seconds=_read_int(
            "EVOLUTION_TASK_PROCESSING_TIMEOUT_SECONDS",
            Settings.evolution_task_processing_timeout_seconds,
        ),
        evolution_task_heartbeat_seconds=_read_int(
            "EVOLUTION_TASK_HEARTBEAT_SECONDS",
            Settings.evolution_task_heartbeat_seconds,
        ),
        evolution_observation_interviews=_read_int(
            "EVOLUTION_OBSERVATION_INTERVIEWS",
            Settings.evolution_observation_interviews,
        ),
        auto_migrate_on_startup=_read_bool(
            "AUTO_MIGRATE_ON_STARTUP",
            Settings.auto_migrate_on_startup,
        ),
        auth_cookie_name=_get_env("AUTH_COOKIE_NAME", Settings.auth_cookie_name),
        auth_cookie_secure=_read_bool("AUTH_COOKIE_SECURE", Settings.auth_cookie_secure),
        auth_cookie_samesite=_get_env(
            "AUTH_COOKIE_SAMESITE",
            Settings.auth_cookie_samesite,
        ),
        csrf_protection_enabled=_read_bool(
            "CSRF_PROTECTION_ENABLED",
            Settings.csrf_protection_enabled,
        ),
        csrf_cookie_name=_get_env("CSRF_COOKIE_NAME", Settings.csrf_cookie_name),
        csrf_header_name=_get_env("CSRF_HEADER_NAME", Settings.csrf_header_name),
        cors_allowed_origins=_get_env(
            "CORS_ALLOWED_ORIGINS",
            Settings.cors_allowed_origins,
        ),
        cors_allowed_origin_regex=_get_env(
            "CORS_ALLOWED_ORIGIN_REGEX",
            Settings.cors_allowed_origin_regex,
        ),
    )
    _validate_settings(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    is_test = settings.app_env.strip().lower() in {"test", "testing", "pytest"}
    normalized_jwt_secret = settings.jwt_secret_key.strip().lower()
    weak_secret_markers = {
        Settings.jwt_secret_key.lower(),
        "change_me_to_a_long_random_secret_at_least_32_chars",
    }
    if not is_test:
        if (
            not normalized_jwt_secret
            or normalized_jwt_secret in weak_secret_markers
            or "change_me" in normalized_jwt_secret
            or "placeholder" in normalized_jwt_secret
            or "example" in normalized_jwt_secret
        ):
            raise RuntimeError(
                "JWT_SECRET_KEY must be configured before starting the application."
            )
        if len(settings.jwt_secret_key) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters long.")
    if settings.interview_task_processing_timeout_seconds < 1:
        raise RuntimeError("INTERVIEW_TASK_PROCESSING_TIMEOUT_SECONDS must be at least 1.")
    if settings.interview_task_heartbeat_seconds < 1:
        raise RuntimeError("INTERVIEW_TASK_HEARTBEAT_SECONDS must be at least 1.")
    if (
        settings.interview_task_heartbeat_seconds
        >= settings.interview_task_processing_timeout_seconds
    ):
        raise RuntimeError(
            "INTERVIEW_TASK_HEARTBEAT_SECONDS must be less than "
            "INTERVIEW_TASK_PROCESSING_TIMEOUT_SECONDS."
        )
    if settings.evolution_trigger_interviews < 1:
        raise RuntimeError("EVOLUTION_TRIGGER_INTERVIEWS must be at least 1.")
    if not 1 <= settings.evolution_synthetic_samples <= 50:
        raise RuntimeError("EVOLUTION_SYNTHETIC_SAMPLES must be between 1 and 50.")
    if not settings.evolution_judge_model.strip():
        raise RuntimeError("EVOLUTION_JUDGE_MODEL must not be empty.")
    if settings.evolution_task_poll_seconds < 1:
        raise RuntimeError("EVOLUTION_TASK_POLL_SECONDS must be at least 1.")
    if settings.evolution_task_max_retries < 0:
        raise RuntimeError("EVOLUTION_TASK_MAX_RETRIES must not be negative.")
    if settings.evolution_task_processing_timeout_seconds < 2:
        raise RuntimeError(
            "EVOLUTION_TASK_PROCESSING_TIMEOUT_SECONDS must be at least 2."
        )
    if settings.evolution_task_heartbeat_seconds < 1:
        raise RuntimeError("EVOLUTION_TASK_HEARTBEAT_SECONDS must be at least 1.")
    if (
        settings.evolution_task_heartbeat_seconds
        >= settings.evolution_task_processing_timeout_seconds
    ):
        raise RuntimeError(
            "EVOLUTION_TASK_HEARTBEAT_SECONDS must be less than "
            "EVOLUTION_TASK_PROCESSING_TIMEOUT_SECONDS."
        )
    if settings.evolution_observation_interviews < 1:
        raise RuntimeError("EVOLUTION_OBSERVATION_INTERVIEWS must be at least 1.")
