from typing import Any

import app.services.account_data as account_data


class _RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._result: list[dict[str, Any]] = []
        self.rowcount = 1

    def cursor(self) -> "_RecordingConnection":
        return self

    def __enter__(self) -> "_RecordingConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(sql.lower().split())
        self.executed.append((normalized, params))
        if normalized.startswith("select original_file_path from resumes"):
            self._result = [{"original_file_path": "resume/user-1.docx"}]
        elif normalized.startswith("select avatar_url from users"):
            self._result = [{"avatar_url": "/api/uploads/avatars/user_1.png"}]
        elif normalized.startswith("select id, username, display_name"):
            self._result = [
                {
                    "id": 1,
                    "username": "alice",
                    "display_name": "Alice",
                    "external_model_consent_version": "2026-07-26",
                }
            ]
        else:
            self._result = []
        self.rowcount = 1

    def fetchone(self) -> dict[str, Any] | None:
        return self._result[0] if self._result else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._result)


def test_account_deletion_clears_external_stores_and_user_rows(
    monkeypatch,
) -> None:
    events: list[Any] = []

    class FakeHistory:
        def __init__(self, _connection: Any) -> None:
            pass

        def list_interview_ids_by_user(self, user_id: int) -> list[int]:
            return [10, 11] if user_id == 1 else []

        def delete_all_by_user(self, user_id: int) -> int:
            events.append(("history", user_id))
            return 2

    class FakeShortMemory:
        def delete_many(self, user_id: int, interview_ids: list[int]) -> int:
            events.append(("redis", user_id, interview_ids))
            return len(interview_ids)

    class FakeVectorIndex:
        def delete_user_memories(self, user_id: int) -> None:
            events.append(("vectors", user_id))
            return None

    monkeypatch.setattr(account_data, "HistoryRepository", FakeHistory)
    monkeypatch.setattr(
        account_data,
        "get_short_term_memory_store",
        lambda: FakeShortMemory(),
    )
    monkeypatch.setattr(account_data, "ChromaMemoryIndex", FakeVectorIndex)
    connection = _RecordingConnection()

    resume_paths, avatar_url = account_data.delete_account_data(connection, 1)

    statements = [sql for sql, _params in connection.executed]
    assert ("redis", 1, [10, 11]) in events
    assert ("vectors", 1) in events
    assert ("history", 1) in events
    assert resume_paths == ["resume/user-1.docx"]
    assert avatar_url == "/api/uploads/avatars/user_1.png"
    assert any("insert into file_cleanup_tasks" in sql for sql in statements)
    assert "delete from resumes where user_id = %s" in statements
    assert "delete from users where id = %s" in statements


def test_account_export_excludes_password_hash() -> None:
    exported = account_data.export_account_data(_RecordingConnection(), 1)

    assert exported["profile"]["username"] == "alice"
    assert "password_hash" not in exported["profile"]
    assert "resumes" in exported["data"]
    assert "interview_qa" in exported["data"]
