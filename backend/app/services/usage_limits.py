from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Any, Protocol
from uuid import uuid4

from fastapi import status

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.db.mysql import mysql_connection


@dataclass(frozen=True)
class UsageLimitRule:
    daily_limit: int
    cooldown_seconds: int = 0


@dataclass
class UsageState:
    day: str
    used: int = 0
    next_allowed_at: float = 0.0
    active: bool = False


@dataclass(frozen=True)
class UsageLease:
    user_id: int
    scope: str
    token: str | None = None


class UsageLimitStore(Protocol):
    def acquire(self, user_id: int, scope: str, rule: UsageLimitRule) -> UsageLease:
        ...

    def release(self, lease: UsageLease) -> None:
        ...

    def reset(self) -> None:
        ...


DEFAULT_USAGE_LIMITS: dict[str, UsageLimitRule] = {
    "resume_upload": UsageLimitRule(daily_limit=20, cooldown_seconds=10),
    "interview_question": UsageLimitRule(daily_limit=120, cooldown_seconds=2),
    "interview_answer": UsageLimitRule(daily_limit=200, cooldown_seconds=1),
    "interview_round_finish": UsageLimitRule(daily_limit=60, cooldown_seconds=3),
    "interview_report_finish": UsageLimitRule(daily_limit=20, cooldown_seconds=10),
}


class InMemoryUsageLimitStore:
    def __init__(self) -> None:
        self._states: dict[tuple[int, str], UsageState] = {}
        self._lock = Lock()

    def acquire(self, user_id: int, scope: str, rule: UsageLimitRule) -> UsageLease:
        key = (user_id, scope)
        now = monotonic()
        today = _today_key()
        with self._lock:
            state = self._states.get(key)
            if state is None or state.day != today:
                state = UsageState(day=today)
                self._states[key] = state
            if state.active:
                raise _too_many_requests("当前操作正在处理中，请稍后再试。")
            if state.used >= rule.daily_limit:
                raise _too_many_requests("今日操作次数已达上限，请明天再试。")
            if state.next_allowed_at > now:
                raise _too_many_requests("请求过于频繁，请稍后再试。")
            state.active = True
            state.used += 1
            state.next_allowed_at = now + rule.cooldown_seconds
        return UsageLease(user_id=user_id, scope=scope)

    def release(self, lease: UsageLease) -> None:
        key = (lease.user_id, lease.scope)
        with self._lock:
            state = self._states.get(key)
            if state is not None:
                state.active = False

    def reset(self) -> None:
        with self._lock:
            self._states.clear()


class MySQLUsageLimitStore:
    def __init__(
        self,
        *,
        connection_factory: Any = mysql_connection,
        active_timeout_seconds: int | None = None,
    ) -> None:
        self.connection_factory = connection_factory
        self.active_timeout_seconds = active_timeout_seconds

    def acquire(self, user_id: int, scope: str, rule: UsageLimitRule) -> UsageLease:
        token = uuid4().hex
        now = _utc_now()
        today = now.date().isoformat()
        lease_timeout = max(1, self.active_timeout_seconds or _active_timeout_seconds())
        active_expires_at = now + timedelta(seconds=lease_timeout)
        next_allowed_at = now + timedelta(seconds=rule.cooldown_seconds)

        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO usage_limits (
                        user_id, scope, usage_date, used_count,
                        next_allowed_at, active_token, active_expires_at
                    )
                    VALUES (%s, %s, %s, 0, NULL, NULL, NULL)
                    ON DUPLICATE KEY UPDATE updated_at = updated_at
                    """,
                    (user_id, scope, today),
                )
                cursor.execute(
                    """
                    SELECT used_count, next_allowed_at, active_token, active_expires_at
                    FROM usage_limits
                    WHERE user_id = %s AND scope = %s AND usage_date = %s
                    FOR UPDATE
                    """,
                    (user_id, scope, today),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("usage limit row was not initialized")

                active_token = row.get("active_token")
                active_until = _normalize_datetime(row.get("active_expires_at"))
                if active_token and active_until is not None and active_until > now:
                    raise _too_many_requests("当前操作正在处理中，请稍后再试。")

                if int(row.get("used_count") or 0) >= rule.daily_limit:
                    raise _too_many_requests("今日操作次数已达上限，请明天再试。")

                stored_next_allowed_at = _normalize_datetime(row.get("next_allowed_at"))
                if stored_next_allowed_at is not None and stored_next_allowed_at > now:
                    raise _too_many_requests("请求过于频繁，请稍后再试。")

                cursor.execute(
                    """
                    UPDATE usage_limits
                    SET used_count = used_count + 1,
                        next_allowed_at = %s,
                        active_token = %s,
                        active_expires_at = %s,
                        updated_at = UTC_TIMESTAMP()
                    WHERE user_id = %s AND scope = %s AND usage_date = %s
                    """,
                    (next_allowed_at, token, active_expires_at, user_id, scope, today),
                )
        return UsageLease(user_id=user_id, scope=scope, token=token)

    def release(self, lease: UsageLease) -> None:
        if lease.token is None:
            return
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE usage_limits
                    SET active_token = NULL,
                        active_expires_at = NULL,
                        updated_at = UTC_TIMESTAMP()
                    WHERE user_id = %s AND scope = %s AND active_token = %s
                    """,
                    (lease.user_id, lease.scope, lease.token),
                )

    def reset(self) -> None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM usage_limits")


class UsageLimiter:
    def __init__(
        self,
        rules: dict[str, UsageLimitRule] | None = None,
        store: UsageLimitStore | None = None,
    ) -> None:
        self.rules = rules or DEFAULT_USAGE_LIMITS
        self.store = store or InMemoryUsageLimitStore()

    @contextmanager
    def guard(self, user_id: int, scope: str) -> Iterator[None]:
        lease = self.acquire(user_id, scope)
        try:
            yield
        finally:
            self.release(lease)

    def acquire(self, user_id: int, scope: str) -> UsageLease:
        return self.store.acquire(user_id, scope, self.rules[scope])

    def release(self, lease_or_user_id: UsageLease | int, scope: str | None = None) -> None:
        if isinstance(lease_or_user_id, UsageLease):
            lease = lease_or_user_id
        else:
            if scope is None:
                raise ValueError("scope is required when releasing by user_id")
            lease = UsageLease(user_id=lease_or_user_id, scope=scope)
        self.store.release(lease)

    def reset(self) -> None:
        self.store.reset()


def _default_store() -> UsageLimitStore:
    settings = get_settings()
    if settings.app_env.strip().lower() in {"test", "testing", "pytest"}:
        return InMemoryUsageLimitStore()
    return MySQLUsageLimitStore(
        active_timeout_seconds=settings.usage_limit_active_timeout_seconds,
    )


def _today_key() -> str:
    return datetime.now(UTC).date().isoformat()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _active_timeout_seconds() -> int:
    return get_settings().usage_limit_active_timeout_seconds


def _normalize_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
    return None


def _too_many_requests(message: str) -> AppError:
    return AppError(
        ErrorCode.TOO_MANY_REQUESTS,
        status.HTTP_429_TOO_MANY_REQUESTS,
        message=message,
    )


usage_limiter = UsageLimiter(store=_default_store())
