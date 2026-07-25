from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from app.core.errors import AppError, ErrorCode


@contextmanager
def memory_user_lock(
    connection: Any,
    user_id: int,
    *,
    wait_seconds: int = 5,
) -> Iterator[None]:
    lock_name = f"interview_arena:memory:user:{user_id}"
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT GET_LOCK(%s, %s) AS acquired",
            (lock_name, max(0, wait_seconds)),
        )
        row = cursor.fetchone() or {}
    if int(row.get("acquired") or 0) != 1:
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            429,
            message="记忆正在处理中，请稍后再试。",
        )
    try:
        yield
    finally:
        with suppress(Exception):
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
