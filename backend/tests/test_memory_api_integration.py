from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from typing import Any

from app.core.security import create_access_token
from app.deps import get_user_repository
from app.repositories.memory_tasks import MemoryTaskRecord
from app.repositories.users import UserRecord
from fastapi.testclient import TestClient
from main import create_app


def test_memory_preference_api_persists_across_requests(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=True)
    monkeypatch.setattr("app.api.preferences.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)
    headers = _auth_headers(1)

    assert client.get("/api/user/preferences", headers=headers).json() == {
        "memory_enabled": True
    }

    response = client.patch(
        "/api/user/preferences",
        headers=headers,
        json={"memory_enabled": False},
    )

    assert response.status_code == 200
    assert response.json() == {"memory_enabled": False}
    assert store.users[1].memory_enabled is False
    assert store.users[1].memory_updated_at is not None
    assert client.get("/api/user/preferences", headers=headers).json() == {
        "memory_enabled": False
    }


def test_memory_preference_api_requires_valid_login() -> None:
    repository_calls = 0

    def unexpected_repository() -> None:
        nonlocal repository_calls
        repository_calls += 1
        raise AssertionError("unauthenticated requests must not access the user repository")

    app = create_app()
    app.dependency_overrides[get_user_repository] = unexpected_repository
    client = TestClient(app, raise_server_exceptions=False)

    missing = client.get("/api/user/preferences")
    invalid = client.get("/api/user/preferences", headers={"Authorization": "Bearer invalid"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert repository_calls == 0


def test_memory_preference_update_failure_does_not_change_stored_state(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=True)
    store.fail_updates = True
    monkeypatch.setattr("app.api.preferences.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.patch(
        "/api/user/preferences",
        headers=_auth_headers(1),
        json={"memory_enabled": False},
    )

    assert response.status_code == 500
    assert store.users[1].memory_enabled is True


def test_clear_memory_api_marks_only_current_user_and_keeps_history(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=True)
    store.users[2] = _user(2, memory_enabled=True)
    store.candidate_memories = [
        {"id": 1, "user_id": 1, "status": "active", "index_status": "indexed"},
        {"id": 2, "user_id": 2, "status": "active", "index_status": "indexed"},
    ]
    monkeypatch.setattr("app.api.memories.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.delete("/api/memories", headers=_auth_headers(1))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert store.candidate_memories[0]["status"] == "deleted"
    assert store.candidate_memories[0]["index_status"] == "pending_delete"
    assert store.candidate_memories[1]["status"] == "active"
    assert store.history_deleted is False


def test_clear_status_is_user_scoped(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=True)
    store.users[2] = _user(2, memory_enabled=True)
    store.tasks = [
        _task(1, user_id=1, status="completed", result={"deleted_count": 3}),
        _task(2, user_id=2, status="failed", result={"deleted_count": 9}),
    ]
    monkeypatch.setattr("app.api.memories.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/memories/clear-status", headers=_auth_headers(1))

    assert response.status_code == 200
    assert response.json() == {
        "task_id": 1,
        "status": "completed",
        "deleted_count": 3,
        "error_message": None,
    }


def test_memory_generation_status_is_user_scoped(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=True)
    store.users[2] = _user(2, memory_enabled=True)
    store.tasks = [
        _task(1, user_id=1, status="failed", task_type="memory_summary", interview_id=43),
        _task(2, user_id=1, status="pending", task_type="memory_summary", interview_id=44),
        _task(3, user_id=2, status="failed", task_type="memory_summary", interview_id=45),
        _task(4, user_id=1, status="failed", task_type="memory_summary"),
        _task(
            5,
            user_id=1,
            status="failed",
            task_type="memory_summary",
            interview_id=46,
            error_message="cancelled_by_memory_clear",
        ),
    ]
    monkeypatch.setattr("app.api.memories.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/memories/generation-status", headers=_auth_headers(1))

    assert response.status_code == 200
    assert response.json() == {
        "pending_count": 1,
        "processing_count": 0,
        "retry_wait_count": 0,
        "failed_count": 1,
    }


def test_memory_generation_status_is_hidden_when_memory_is_disabled() -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=False)
    store.tasks = [
        _task(1, user_id=1, status="failed", task_type="memory_summary", interview_id=43)
    ]
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/memories/generation-status", headers=_auth_headers(1))

    assert response.status_code == 200
    assert response.json() == {
        "pending_count": 0,
        "processing_count": 0,
        "retry_wait_count": 0,
        "failed_count": 0,
    }


def test_retry_failed_memories_requeues_only_current_user(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=True)
    store.users[2] = _user(2, memory_enabled=True)
    store.tasks = [
        _task(
            1,
            user_id=1,
            status="failed",
            task_type="memory_summary",
            interview_id=43,
            retry_count=3,
            error_message="processing_timeout",
        ),
        _task(
            2,
            user_id=2,
            status="failed",
            task_type="memory_summary",
            interview_id=44,
            retry_count=3,
            error_message="processing_timeout",
        ),
    ]
    monkeypatch.setattr("app.api.memories.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/memories/retry-failed", headers=_auth_headers(1))

    assert response.status_code == 200
    assert response.json() == {"requeued_count": 1}
    assert store.tasks[0].status == "pending"
    assert store.tasks[0].retry_count == 0
    assert store.tasks[0].error_message is None
    assert store.tasks[1].status == "failed"


def test_retry_failed_memories_does_nothing_when_memory_is_disabled(monkeypatch) -> None:
    store = _Store()
    store.users[1] = _user(1, memory_enabled=False)
    store.tasks = [
        _task(
            1,
            user_id=1,
            status="failed",
            task_type="memory_summary",
            interview_id=43,
            retry_count=3,
        )
    ]
    monkeypatch.setattr("app.api.memories.mysql_connection", _connection_factory(store))
    app = create_app()
    app.dependency_overrides[get_user_repository] = lambda: _UserRepository(store)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/memories/retry-failed", headers=_auth_headers(1))

    assert response.status_code == 200
    assert response.json() == {"requeued_count": 0}
    assert store.tasks[0].status == "failed"
    assert store.tasks[0].retry_count == 3


class _Store:
    def __init__(self) -> None:
        self.users: dict[int, UserRecord] = {}
        self.tasks: list[MemoryTaskRecord] = []
        self.candidate_memories: list[dict[str, Any]] = []
        self.next_task_id = 1
        self.fail_updates = False
        self.history_deleted = False


class _UserRepository:
    def __init__(self, store: _Store) -> None:
        self.store = store

    def get_by_id(self, user_id: int) -> UserRecord | None:
        return self.store.users.get(user_id)


class _Connection:
    def __init__(self, store: _Store) -> None:
        self.store = store
        self.lastrowid = 0
        self.rowcount = 0
        self._result: Any = None
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> "_Connection":
        return self

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(sql.lower().split())
        self.rowcount = 0
        self._result = None
        if normalized.startswith("select get_lock"):
            self._result = {"acquired": 1}
            return
        if normalized.startswith("select release_lock"):
            self._result = {"released": 1}
            return
        if normalized.startswith("select memory_enabled from users"):
            user = self.store.users.get(int(params[0]))
            self._result = {"memory_enabled": user.memory_enabled} if user else None
            return
        if normalized.startswith("update users set memory_enabled"):
            if self.store.fail_updates:
                raise RuntimeError("database unavailable")
            memory_enabled, updated_at, user_id = params
            user = self.store.users[int(user_id)]
            self.store.users[int(user_id)] = UserRecord(
                id=user.id,
                username=user.username,
                password_hash=user.password_hash,
                display_name=user.display_name,
                memory_enabled=bool(memory_enabled),
                memory_updated_at=updated_at,
            )
            self.rowcount = 1
            return
        if normalized.startswith("update candidate_memories"):
            user_id = int(params[0])
            for memory in self.store.candidate_memories:
                if memory["user_id"] == user_id:
                    memory["status"] = "deleted"
                    memory["index_status"] = "pending_delete"
                    self.rowcount += 1
            return
        if normalized.startswith("update interviewer_memories") or normalized.startswith(
            "update agent_memories"
        ):
            return
        if (
            normalized.startswith("update memory_tasks")
            and "cancelled_by_memory_clear" in normalized
        ):
            if "set status = 'pending'" in normalized:
                user_id = int(params[0])
                updated_tasks: list[MemoryTaskRecord] = []
                for task in self.store.tasks:
                    if (
                        task.user_id == user_id
                        and task.task_type == "memory_summary"
                        and task.status == "failed"
                        and task.interview_id is not None
                        and task.error_message != "cancelled_by_memory_clear"
                    ):
                        task = replace(
                            task,
                            status="pending",
                            retry_count=0,
                            next_retry_at=None,
                            error_message=None,
                            result=None,
                            started_at=None,
                            completed_at=None,
                            processing_token=None,
                            heartbeat_at=None,
                        )
                        self.rowcount += 1
                    updated_tasks.append(task)
                self.store.tasks = updated_tasks
            return
        if normalized.startswith("select status, count(*) as count from memory_tasks"):
            user_id = int(params[0])
            counts: dict[str, int] = {}
            for task in self.store.tasks:
                if (
                    task.user_id == user_id
                    and task.task_type == "memory_summary"
                    and task.interview_id is not None
                    and not (
                        task.status == "failed"
                        and task.error_message == "cancelled_by_memory_clear"
                    )
                ):
                    counts[task.status] = counts.get(task.status, 0) + 1
            self._result = [
                {"status": status, "count": count}
                for status, count in counts.items()
            ]
            return
        if normalized.startswith("select * from memory_tasks where user_id"):
            user_id = int(params[0])
            task_type = str(params[1])
            matches = [
                task
                for task in self.store.tasks
                if task.user_id == user_id and task.task_type == task_type
            ]
            self._result = _task_row(matches[-1]) if matches else None
            return
        if normalized.startswith("insert into memory_tasks"):
            task = _task(self.store.next_task_id, user_id=int(params[1]), status=str(params[2]))
            self.store.next_task_id += 1
            self.store.tasks.append(task)
            self.lastrowid = task.id
            return
        if normalized.startswith("select * from memory_tasks where id"):
            task_id = int(params[0])
            task = next((item for item in self.store.tasks if item.id == task_id), None)
            self._result = _task_row(task) if task else None
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self) -> Any:
        return self._result

    def fetchall(self) -> list[Any]:
        return self._result if isinstance(self._result, list) else []

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _connection_factory(store: _Store) -> Any:
    @contextmanager
    def _factory() -> Iterator[_Connection]:
        connection = _Connection(store)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    return _factory


def _auth_headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _user(user_id: int, *, memory_enabled: bool) -> UserRecord:
    return UserRecord(
        id=user_id,
        username=f"user-{user_id}",
        display_name=f"User {user_id}",
        password_hash="hash",
        memory_enabled=memory_enabled,
        memory_updated_at=None,
    )


def _task(
    task_id: int,
    *,
    user_id: int,
    status: str,
    result: dict[str, Any] | None = None,
    task_type: str = "memory_clear",
    interview_id: int | None = None,
    retry_count: int = 0,
    error_message: str | None = None,
) -> MemoryTaskRecord:
    return MemoryTaskRecord(
        id=task_id,
        task_type=task_type,
        user_id=user_id,
        interview_id=interview_id,
        memory_collection=None,
        memory_id=None,
        status=status,
        retry_count=retry_count,
        max_retries=3,
        next_retry_at=None,
        error_message=error_message,
        result=result,
        created_at=datetime(2026, 6, 18, 9, 0, 0),
        started_at=None,
        completed_at=None,
    )


def _task_row(task: MemoryTaskRecord) -> dict[str, Any]:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "user_id": task.user_id,
        "interview_id": task.interview_id,
        "memory_collection": task.memory_collection,
        "memory_id": task.memory_id,
        "status": task.status,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "next_retry_at": task.next_retry_at,
        "error_message": task.error_message,
        "result": task.result,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }
