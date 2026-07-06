from datetime import datetime
from typing import Any


class PreferencesRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get_memory_enabled(self, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT memory_enabled FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
        return bool(row["memory_enabled"]) if row is not None else True

    def update_memory_enabled(self, user_id: int, memory_enabled: bool) -> bool:
        updated_at = datetime.utcnow()
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET memory_enabled = %s, memory_updated_at = %s
                WHERE id = %s
                """,
                (memory_enabled, updated_at, user_id),
            )
        return memory_enabled
