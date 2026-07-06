import inspect

import app.services.usage_limits as usage_limits_module
import pytest
from app.core.errors import AppError, ErrorCode
from app.services.usage_limits import (
    InMemoryUsageLimitStore,
    MySQLUsageLimitStore,
    UsageLimiter,
    UsageLimitRule,
)


def test_usage_limiter_enforces_daily_limit() -> None:
    limiter = UsageLimiter({"expensive": UsageLimitRule(daily_limit=1)})

    with limiter.guard(7, "expensive"):
        pass

    with pytest.raises(AppError) as exc_info:
        with limiter.guard(7, "expensive"):
            pass

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == ErrorCode.TOO_MANY_REQUESTS


def test_usage_limiter_blocks_concurrent_same_user_scope() -> None:
    limiter = UsageLimiter({"expensive": UsageLimitRule(daily_limit=2)})

    with limiter.guard(7, "expensive"):
        with pytest.raises(AppError) as exc_info:
            with limiter.guard(7, "expensive"):
                pass

    assert exc_info.value.code == ErrorCode.TOO_MANY_REQUESTS


def test_usage_limiter_enforces_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr(usage_limits_module, "monotonic", lambda: now)
    limiter = UsageLimiter({"expensive": UsageLimitRule(daily_limit=3, cooldown_seconds=10)})

    with limiter.guard(7, "expensive"):
        pass

    with pytest.raises(AppError):
        with limiter.guard(7, "expensive"):
            pass

    now = 111.0
    with limiter.guard(7, "expensive"):
        pass


def test_usage_limiter_instances_share_configured_store() -> None:
    store = InMemoryUsageLimitStore()
    first = UsageLimiter({"expensive": UsageLimitRule(daily_limit=2)}, store=store)
    second = UsageLimiter({"expensive": UsageLimitRule(daily_limit=2)}, store=store)

    with first.guard(7, "expensive"):
        with pytest.raises(AppError) as exc_info:
            with second.guard(7, "expensive"):
                pass

    assert exc_info.value.code == ErrorCode.TOO_MANY_REQUESTS


def test_mysql_usage_store_uses_row_lock_and_expiring_active_lease() -> None:
    source = inspect.getsource(MySQLUsageLimitStore.acquire).lower()

    assert "on duplicate key update" in source
    assert "for update" in source
    assert "active_expires_at" in source
    assert "used_count = used_count + 1" in source
