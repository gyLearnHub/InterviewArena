from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.errors import AppError, ErrorCode


@contextmanager
def interview_mutation_lock(
    connection: Any,
    interview_id: int,
    *,
    wait_seconds: int = 0,
) -> Iterator[None]:
    lock_name = f"interview_arena:interview:{interview_id}"
    acquired = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s) AS acquired", (lock_name, max(0, wait_seconds)))
        row = cursor.fetchone() or {}
        acquired = int(row.get("acquired") or 0) == 1
    if not acquired:
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            429,
            message="当前面试操作正在处理中，请稍后再试。",
        )
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


@contextmanager
def user_history_mutation_lock(
    connection: Any,
    user_id: int,
    *,
    wait_seconds: int = 1,
) -> Iterator[None]:
    lock_name = f"interview_arena:user-history:{user_id}"
    acquired = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s) AS acquired", (lock_name, max(0, wait_seconds)))
        row = cursor.fetchone() or {}
        acquired = int(row.get("acquired") or 0) == 1
    if not acquired:
        raise AppError(
            ErrorCode.TOO_MANY_REQUESTS,
            429,
            message="历史记录正在处理中，请稍后再试。",
        )
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
