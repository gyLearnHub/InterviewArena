from datetime import datetime
from typing import Any

from app.repositories.users import CURRENT_PRIVACY_VERSION


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

    def get_external_model_consent(self, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT external_model_consent_at, external_model_consent_version
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        return bool(
            row
            and row.get("external_model_consent_at") is not None
            and row.get("external_model_consent_version") == CURRENT_PRIVACY_VERSION
        )

    def update_external_model_consent(self, user_id: int, consent: bool) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET external_model_consent_at = CASE
                        WHEN %s = 1 THEN UTC_TIMESTAMP()
                        ELSE NULL
                    END,
                    external_model_consent_version = CASE
                        WHEN %s = 1 THEN %s
                        ELSE NULL
                    END
                WHERE id = %s
                """,
                (consent, consent, CURRENT_PRIVACY_VERSION, user_id),
            )
        return consent
