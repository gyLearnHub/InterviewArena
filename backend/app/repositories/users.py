from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    password_hash: str
    display_name: str | None = None
    avatar_url: str | None = None
    memory_enabled: bool = True
    memory_updated_at: datetime | None = None


class DuplicateUsernameError(Exception):
    pass


class UserRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def commit(self) -> None:
        self.connection.commit()

    def get_by_id(self, user_id: int) -> UserRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, avatar_url, password_hash,
                       memory_enabled, memory_updated_at
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return _to_user_record(row)

    def get_by_username(self, username: str) -> UserRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, display_name, avatar_url, password_hash,
                       memory_enabled, memory_updated_at
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            row = cursor.fetchone()
        return _to_user_record(row)

    def create(self, username: str, password_hash: str) -> UserRecord:
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO users (username, display_name, password_hash) VALUES (%s, %s, %s)",
                    (username, username, password_hash),
                )
            except Exception as exc:
                if _is_duplicate_key_error(exc):
                    raise DuplicateUsernameError(username) from exc
                raise
            user_id = int(cursor.lastrowid)
        return UserRecord(
            id=user_id,
            username=username,
            display_name=username,
            password_hash=password_hash,
        )

    def consume_auth_rate_limit(
        self,
        *,
        scope: str,
        identifier_hash: str,
        window_started_at: datetime,
        limit: int,
    ) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_rate_limits (
                    scope, identifier_hash, window_started_at, request_count
                )
                VALUES (%s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    request_count = request_count + 1,
                    updated_at = UTC_TIMESTAMP()
                """,
                (scope, identifier_hash, window_started_at),
            )
            cursor.execute(
                """
                SELECT request_count
                FROM auth_rate_limits
                WHERE scope = %s
                  AND identifier_hash = %s
                  AND window_started_at = %s
                """,
                (scope, identifier_hash, window_started_at),
            )
            row = cursor.fetchone() or {}
            cursor.execute(
                """
                DELETE FROM auth_rate_limits
                WHERE window_started_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 2 DAY)
                LIMIT 100
                """
            )
        return int(row.get("request_count") or 0) <= max(1, limit)

    def get_auth_rate_limit_count(
        self,
        *,
        scope: str,
        identifier_hash: str,
        window_started_at: datetime,
    ) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT request_count
                FROM auth_rate_limits
                WHERE scope = %s
                  AND identifier_hash = %s
                  AND window_started_at = %s
                """,
                (scope, identifier_hash, window_started_at),
            )
            row = cursor.fetchone() or {}
        return int(row.get("request_count") or 0)

    def clear_auth_rate_limit(
        self,
        *,
        scope: str,
        identifier_hash: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM auth_rate_limits
                WHERE scope = %s AND identifier_hash = %s
                """,
                (scope, identifier_hash),
            )

    def update_display_name(self, user_id: int, display_name: str) -> UserRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET display_name = %s
                WHERE id = %s
                """,
                (display_name, user_id),
            )
        return self.get_by_id(user_id)

    def update_avatar_url(self, user_id: int, avatar_url: str) -> UserRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET avatar_url = %s
                WHERE id = %s
                """,
                (avatar_url, user_id),
            )
        return self.get_by_id(user_id)


def _to_user_record(row: dict[str, Any] | None) -> UserRecord | None:
    if row is None:
        return None
    return UserRecord(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=row.get("display_name") or str(row["username"]),
        avatar_url=str(row["avatar_url"]) if row.get("avatar_url") else None,
        password_hash=str(row["password_hash"]),
        memory_enabled=bool(row.get("memory_enabled", True)),
        memory_updated_at=row.get("memory_updated_at"),
    )


def _is_duplicate_key_error(exc: Exception) -> bool:
    args = getattr(exc, "args", ())
    code = args[0] if args else None
    return code == 1062 or "duplicate" in str(exc).casefold()
