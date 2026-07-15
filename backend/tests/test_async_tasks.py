from contextlib import contextmanager
from datetime import datetime
from typing import Any

import app.api.interviews as interviews_api
import app.api.resumes as resumes_api
import pytest
from app.api.interviews import (
    answer_round_question_task,
    finish_interview_task,
    finish_round_task,
    start_round_task,
)
from app.core.errors import AppError, ErrorCode
from app.deps import get_current_user
from app.repositories.interview_tasks import (
    InterviewOperationTaskRecord,
    InterviewOperationTaskRepository,
)
from app.repositories.interviews import InterviewRecord, InterviewRoundRecord
from app.repositories.resumes import ResumeParseTaskRecord, ResumeRepository
from app.repositories.users import UserRecord
from app.schemas.interview import (
    InterviewFinishRequest,
    RoundAnswerRequest,
    RoundFinishRequest,
    RoundStartRequest,
)
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from main import create_app


class _FakeConnection:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


class _FakeInterviewTaskRepository:
    def __init__(
        self,
        task: InterviewOperationTaskRecord | None = None,
        *,
        active_task_exists: bool = False,
    ) -> None:
        self.connection = _FakeConnection()
        self.task = task
        self.active_task_exists = active_task_exists
        self.calls: list[dict[str, Any]] = []
        self.active_checks: list[dict[str, Any]] = []

    def create_task_for_owned_interview(self, **kwargs: Any) -> InterviewOperationTaskRecord | None:
        self.calls.append(kwargs)
        return self.task

    def has_active_task_for_scope(self, **kwargs: Any) -> bool:
        self.active_checks.append(kwargs)
        return self.active_task_exists


class _RejectingLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    @contextmanager
    def guard(self, user_id: int, scope: str) -> Any:
        self.calls.append((user_id, scope))
        raise AppError(ErrorCode.TOO_MANY_REQUESTS, 429)
        yield


class _RecordingLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    @contextmanager
    def guard(self, user_id: int, scope: str) -> Any:
        self.calls.append((user_id, scope))
        yield


class _FakeInterviewOwnershipRepository:
    def __init__(
        self,
        *,
        interviews: dict[int, InterviewRecord] | None = None,
        rounds: dict[tuple[int, int], InterviewRoundRecord] | None = None,
    ) -> None:
        self.interviews = interviews or {}
        self.rounds = rounds or {}
        self.interview_calls: list[tuple[int, int]] = []
        self.round_calls: list[tuple[int, int]] = []

    def get_interview_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> InterviewRecord | None:
        self.interview_calls.append((interview_id, user_id))
        interview = self.interviews.get(interview_id)
        if interview is None or interview.user_id != user_id:
            return None
        return interview

    def get_round(self, interview_id: int, round_id: int) -> InterviewRoundRecord | None:
        self.round_calls.append((interview_id, round_id))
        return self.rounds.get((interview_id, round_id))


class _TaskRepositoryConnection:
    def __init__(
        self,
        *,
        interview_owners: dict[int, int],
        rounds: set[tuple[int, int]],
    ) -> None:
        self.interview_owners = interview_owners
        self.rounds = rounds
        self.tasks: dict[int, dict[str, Any]] = {}
        self.next_task_id = 1

    def cursor(self) -> "_TaskRepositoryCursor":
        return _TaskRepositoryCursor(self)


class _TaskRepositoryCursor:
    def __init__(self, connection: _TaskRepositoryConnection) -> None:
        self.connection = connection
        self.lastrowid = 0
        self.rowcount = 0
        self._fetchone: dict[str, Any] | None = None

    def __enter__(self) -> "_TaskRepositoryCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        normalized = " ".join(sql.casefold().split())
        if normalized.startswith("select id from interviews") and "for update" in normalized:
            interview_id = int(params[0])
            user_id = int(params[1])
            self._fetchone = (
                {"id": interview_id}
                if self.connection.interview_owners.get(interview_id) == user_id
                else None
            )
            self.rowcount = 1 if self._fetchone is not None else 0
            return
        if normalized.startswith("select 1 from interview_rounds"):
            round_id = int(params[0])
            interview_id = int(params[1])
            self._fetchone = (
                {"1": 1} if (interview_id, round_id) in self.connection.rounds else None
            )
            self.rowcount = 1 if self._fetchone is not None else 0
            return
        if "insert into interview_operation_tasks" in normalized and "values" in normalized:
            self._execute_create_task(params)
            return
        if (
            "select 1 from interview_operation_tasks" in normalized
            and "operation in" in normalized
            and "status in ('pending', 'processing')" in normalized
        ):
            self._execute_has_active_task_for_scope(params)
            return
        if "from interview_operation_tasks" in normalized and "where id = %s" in normalized:
            self._fetchone = self.connection.tasks.get(int(params[0]))
            self.rowcount = 0
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self) -> dict[str, Any] | None:
        return self._fetchone

    def _execute_create_task(self, params: tuple[Any, ...]) -> None:
        user_id, interview_id, round_id, operation, payload_json = params
        task_id = self.connection.next_task_id
        self.connection.next_task_id += 1
        self.connection.tasks[task_id] = {
            "id": task_id,
            "user_id": int(user_id),
            "interview_id": interview_id,
            "round_id": int(round_id) if round_id is not None else None,
            "operation": operation,
            "payload_json": payload_json,
            "status": "pending",
            "result_json": None,
            "error_code": None,
            "error_message": None,
            "created_at": datetime(2026, 7, 7, 12, 0),
            "started_at": None,
            "completed_at": None,
            "processing_token": None,
            "heartbeat_at": None,
        }
        self.lastrowid = task_id
        self.rowcount = 1
        self._fetchone = None

    def _execute_has_active_task_for_scope(self, params: tuple[Any, ...]) -> None:
        user_id = int(params[0])
        interview_id = int(params[1])
        operations = {str(item) for item in params[2:]}
        self._fetchone = next(
            (
                {"1": 1}
                for task in self.connection.tasks.values()
                if task["user_id"] == user_id
                and task["interview_id"] == interview_id
                and task["operation"] in operations
                and task["status"] in {"pending", "processing"}
            ),
            None,
        )
        self.rowcount = 0


def _interview_record(interview_id: int, user_id: int) -> InterviewRecord:
    return InterviewRecord(
        id=interview_id,
        user_id=user_id,
        resume_id=1,
        target_position="后端开发",
        status="created",
        question_count=0,
        started_at=None,
        ended_at=None,
    )


def _round_record(interview_id: int, round_id: int) -> InterviewRoundRecord:
    return InterviewRoundRecord(
        id=round_id,
        interview_id=interview_id,
        agent_type="resume",
        round_type="resume",
        status="pending",
        min_main_questions=1,
        max_main_questions=2,
        min_total_questions=1,
        max_total_questions=3,
        score=None,
        result=None,
        summary=None,
        is_reference_only=False,
        started_at=None,
        ended_at=None,
    )


def _interview_task_api_client(
    interview_repository: _FakeInterviewOwnershipRepository,
    task_repository: _FakeInterviewTaskRepository,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        id=1,
        username="alice",
        password_hash="hash",
    )
    app.dependency_overrides[interviews_api.get_interview_repository] = lambda: interview_repository
    app.dependency_overrides[interviews_api.get_interview_operation_task_repository] = lambda: (
        task_repository
    )
    return TestClient(app, raise_server_exceptions=False)


def test_interview_task_endpoint_rejects_foreign_interview_before_enqueue() -> None:
    interview_repository = _FakeInterviewOwnershipRepository()
    repository = _FakeInterviewTaskRepository(task=None)
    background_tasks = BackgroundTasks()

    with pytest.raises(AppError) as exc_info:
        start_round_task(
            interview_id=200,
            round_id=300,
            background_tasks=background_tasks,
            current_user=UserRecord(id=1, username="alice", password_hash="hash"),
            interview_repository=interview_repository,  # type: ignore[arg-type]
            task_repository=repository,  # type: ignore[arg-type]
        )

    assert exc_info.value.code == ErrorCode.NOT_FOUND
    assert repository.connection.commit_count == 0
    assert interview_repository.interview_calls == [(200, 1)]
    assert repository.calls == []
    assert background_tasks.tasks == []


def test_interview_task_endpoint_persists_payload_before_background_work() -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
        rounds={(10, 20): _round_record(10, 20)},
    )
    task = InterviewOperationTaskRecord(
        id=9,
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="start_round",
        status="pending",
        payload={"round_id": 20},
    )
    repository = _FakeInterviewTaskRepository(task=task)
    background_tasks = BackgroundTasks()

    response = start_round_task(
        interview_id=10,
        round_id=20,
        background_tasks=background_tasks,
        request=RoundStartRequest(difficulty="pressure", time_limit_minutes=60),
        current_user=UserRecord(id=1, username="alice", password_hash="hash"),
        interview_repository=interview_repository,  # type: ignore[arg-type]
        task_repository=repository,  # type: ignore[arg-type]
    )

    assert response.task_id == 9
    assert repository.connection.commit_count == 1
    payload = repository.calls[0]["payload"]
    assert payload["round_id"] == 20
    assert payload["difficulty"] == "pressure"
    assert payload["time_limit_minutes"] == 60
    assert datetime.fromisoformat(payload["round_started_at"])
    assert repository.calls[0]["exclusive_operations"] == interviews_api.ROUND_MUTATING_OPERATIONS
    assert len(background_tasks.tasks) == 1


@pytest.mark.parametrize(
    ("path", "json_body", "expected_scope", "expected_operations"),
    [
        (
            "/api/interviews/10/rounds/20/start-task",
            None,
            "interview_question_enqueue",
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "/api/interviews/10/rounds/20/answers-task",
            {"question_id": 30, "answer": "我会先定位瓶颈。"},
            "interview_answer_enqueue",
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "/api/interviews/10/rounds/20/finish-task",
            {"finish_type": "normal"},
            "interview_round_finish_enqueue",
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "/api/interviews/10/finish-task",
            {"finish_type": "normal"},
            "interview_report_finish_enqueue",
            interviews_api.INTERVIEW_MUTATING_OPERATIONS,
        ),
    ],
)
def test_interview_task_api_rejects_enqueue_limit_before_task_create(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    json_body: dict[str, Any] | None,
    expected_scope: str,
    expected_operations: tuple[str, ...],
) -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
        rounds={(10, 20): _round_record(10, 20)},
    )
    task_repository = _FakeInterviewTaskRepository(
        task=InterviewOperationTaskRecord(
            id=9,
            user_id=1,
            interview_id=10,
            round_id=20,
            operation=expected_operations[0],
            status="pending",
        )
    )
    limiter = _RejectingLimiter()
    monkeypatch.setattr(interviews_api, "usage_limiter", limiter)
    client = _interview_task_api_client(interview_repository, task_repository)

    response = client.post(path, json=json_body) if json_body is not None else client.post(path)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == ErrorCode.TOO_MANY_REQUESTS.value
    assert limiter.calls == [(1, expected_scope)]
    assert task_repository.active_checks == [
        {
            "user_id": 1,
            "interview_id": 10,
            "operations": expected_operations,
        }
    ]
    assert task_repository.calls == []
    assert task_repository.connection.commit_count == 0


@pytest.mark.parametrize(
    ("path", "json_body", "expected_operations"),
    [
        (
            "/api/interviews/10/rounds/20/start-task",
            None,
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "/api/interviews/10/rounds/20/answers-task",
            {"question_id": 30, "answer": "我会先定位瓶颈。"},
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "/api/interviews/10/rounds/20/finish-task",
            {"finish_type": "normal"},
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "/api/interviews/10/finish-task",
            {"finish_type": "normal"},
            interviews_api.INTERVIEW_MUTATING_OPERATIONS,
        ),
    ],
)
def test_interview_task_api_rejects_active_scope_before_task_create(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    json_body: dict[str, Any] | None,
    expected_operations: tuple[str, ...],
) -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
        rounds={(10, 20): _round_record(10, 20)},
    )
    task_repository = _FakeInterviewTaskRepository(active_task_exists=True)
    limiter = _RecordingLimiter()
    monkeypatch.setattr(interviews_api, "usage_limiter", limiter)
    client = _interview_task_api_client(interview_repository, task_repository)

    response = client.post(path, json=json_body) if json_body is not None else client.post(path)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == ErrorCode.TOO_MANY_REQUESTS.value
    assert limiter.calls == []
    assert task_repository.active_checks == [
        {
            "user_id": 1,
            "interview_id": 10,
            "operations": expected_operations,
        }
    ]
    assert task_repository.calls == []
    assert task_repository.connection.commit_count == 0


def test_interview_task_endpoint_rejects_enqueue_limit_before_task_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
        rounds={(10, 20): _round_record(10, 20)},
    )
    task = InterviewOperationTaskRecord(
        id=9,
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="start_round",
        status="pending",
    )
    repository = _FakeInterviewTaskRepository(task=task)
    background_tasks = BackgroundTasks()

    limiter = _RejectingLimiter()
    monkeypatch.setattr(interviews_api, "usage_limiter", limiter)

    with pytest.raises(AppError) as exc_info:
        start_round_task(
            interview_id=10,
            round_id=20,
            background_tasks=background_tasks,
            current_user=UserRecord(id=1, username="alice", password_hash="hash"),
            interview_repository=interview_repository,  # type: ignore[arg-type]
            task_repository=repository,  # type: ignore[arg-type]
        )

    assert exc_info.value.code == ErrorCode.TOO_MANY_REQUESTS
    assert limiter.calls == [(1, "interview_question_enqueue")]
    assert repository.calls == []
    assert repository.connection.commit_count == 0
    assert background_tasks.tasks == []


@pytest.mark.parametrize(
    ("call_name", "expected_operation", "expected_scope_operations"),
    [
        (
            "answer_round_question_task",
            "answer_round_question",
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        ("finish_round_task", "finish_round", interviews_api.ROUND_MUTATING_OPERATIONS),
        (
            "finish_interview_task",
            "finish_interview",
            interviews_api.INTERVIEW_MUTATING_OPERATIONS,
        ),
    ],
)
def test_interview_task_handlers_reject_active_scope_before_task_create(
    call_name: str,
    expected_operation: str,
    expected_scope_operations: tuple[str, ...],
) -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
        rounds={(10, 20): _round_record(10, 20)},
    )
    repository = _FakeInterviewTaskRepository(active_task_exists=True)
    background_tasks = BackgroundTasks()
    current_user = UserRecord(id=1, username="alice", password_hash="hash")

    with pytest.raises(AppError) as exc_info:
        if call_name == "answer_round_question_task":
            answer_round_question_task(
                interview_id=10,
                round_id=20,
                request=RoundAnswerRequest(question_id=30, answer="我会先定位瓶颈。"),
                background_tasks=background_tasks,
                current_user=current_user,
                interview_repository=interview_repository,  # type: ignore[arg-type]
                task_repository=repository,  # type: ignore[arg-type]
            )
        elif call_name == "finish_round_task":
            finish_round_task(
                interview_id=10,
                round_id=20,
                background_tasks=background_tasks,
                request=RoundFinishRequest(finish_type="normal"),
                current_user=current_user,
                interview_repository=interview_repository,  # type: ignore[arg-type]
                task_repository=repository,  # type: ignore[arg-type]
            )
        else:
            finish_interview_task(
                interview_id=10,
                background_tasks=background_tasks,
                request=InterviewFinishRequest(finish_type="normal"),
                current_user=current_user,
                interview_repository=interview_repository,  # type: ignore[arg-type]
                task_repository=repository,  # type: ignore[arg-type]
            )

    assert exc_info.value.code == ErrorCode.TOO_MANY_REQUESTS
    assert repository.active_checks == [
        {
            "user_id": 1,
            "interview_id": 10,
            "operations": expected_scope_operations,
        }
    ]
    assert repository.calls == []
    assert repository.connection.commit_count == 0
    assert background_tasks.tasks == []
    assert expected_operation in expected_scope_operations


def test_interview_task_endpoint_rejects_active_scope_task_before_create() -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
        rounds={(10, 20): _round_record(10, 20)},
    )
    task = InterviewOperationTaskRecord(
        id=9,
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="start_round",
        status="pending",
    )
    repository = _FakeInterviewTaskRepository(task=task, active_task_exists=True)
    background_tasks = BackgroundTasks()

    with pytest.raises(AppError) as exc_info:
        start_round_task(
            interview_id=10,
            round_id=20,
            background_tasks=background_tasks,
            current_user=UserRecord(id=1, username="alice", password_hash="hash"),
            interview_repository=interview_repository,  # type: ignore[arg-type]
            task_repository=repository,  # type: ignore[arg-type]
        )

    assert exc_info.value.code == ErrorCode.TOO_MANY_REQUESTS
    assert repository.active_checks == [
        {
            "user_id": 1,
            "interview_id": 10,
            "operations": interviews_api.ROUND_MUTATING_OPERATIONS,
        }
    ]
    assert repository.calls == []
    assert repository.connection.commit_count == 0
    assert background_tasks.tasks == []


def test_interview_task_api_rejects_missing_round_before_task_create() -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 1)},
    )
    task_repository = _FakeInterviewTaskRepository(
        task=InterviewOperationTaskRecord(
            id=9,
            user_id=1,
            interview_id=10,
            round_id=99,
            operation="start_round",
            status="pending",
        )
    )
    client = _interview_task_api_client(interview_repository, task_repository)

    response = client.post("/api/interviews/10/rounds/99/start-task")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert interview_repository.round_calls == [(10, 99)]
    assert task_repository.calls == []
    assert task_repository.connection.commit_count == 0


def test_interview_task_api_rejects_foreign_interview_before_task_create() -> None:
    interview_repository = _FakeInterviewOwnershipRepository(
        interviews={10: _interview_record(10, 2)},
    )
    task_repository = _FakeInterviewTaskRepository(
        task=InterviewOperationTaskRecord(
            id=9,
            user_id=1,
            interview_id=10,
            operation="finish_interview",
            status="pending",
        )
    )
    client = _interview_task_api_client(interview_repository, task_repository)

    response = client.post("/api/interviews/10/finish-task")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert interview_repository.interview_calls == [(10, 1)]
    assert interview_repository.round_calls == []
    assert task_repository.calls == []
    assert task_repository.connection.commit_count == 0


def test_interview_background_task_holds_usage_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    task = InterviewOperationTaskRecord(
        id=7,
        user_id=3,
        interview_id=11,
        round_id=22,
        operation="start_round",
        status="processing",
        payload={"round_id": 22},
    )

    class FakeLimiter:
        def acquire(self, user_id: int, scope: str) -> str:
            events.append(f"acquire:{user_id}:{scope}")
            return "lease-token"

        def release(self, lease: str) -> None:
            events.append(f"release:{lease}")

    class FakeTaskRepository:
        completed: list[tuple[int, dict[str, Any]]] = []

        def __init__(self, _connection: Any) -> None:
            pass

        def mark_completed(self, task_id: int, result: dict[str, Any]) -> bool:
            self.completed.append((task_id, result))
            return True

    @contextmanager
    def fake_mysql_connection() -> Any:
        yield object()

    def fake_run(_task: InterviewOperationTaskRecord, _payload: dict[str, Any]) -> dict[str, Any]:
        events.append("run")
        return {"ok": True}

    monkeypatch.setattr(
        interviews_api,
        "_load_task_for_execution",
        lambda _task_id, **_kwargs: task,
    )
    monkeypatch.setattr(interviews_api, "usage_limiter", FakeLimiter())
    monkeypatch.setattr(interviews_api, "_run_interview_operation", fake_run)
    monkeypatch.setattr(interviews_api, "mysql_connection", fake_mysql_connection)
    monkeypatch.setattr(interviews_api, "InterviewOperationTaskRepository", FakeTaskRepository)

    interviews_api.run_interview_operation_task(task.id)

    assert events == ["acquire:3:interview_question", "run", "release:lease-token"]
    assert FakeTaskRepository.completed == [(7, {"ok": True})]


def test_interview_background_task_recovers_completion_after_processing_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = InterviewOperationTaskRecord(
        id=8,
        user_id=3,
        interview_id=11,
        round_id=22,
        operation="start_round",
        status="processing",
        payload={"round_id": 22},
        processing_token="expired-token",
    )

    class FakeTaskRepository:
        calls: list[tuple[str, int, dict[str, Any]]] = []

        def __init__(self, _connection: Any) -> None:
            pass

        def mark_completed(
            self,
            task_id: int,
            result: dict[str, Any],
            *,
            processing_token: str | None = None,
        ) -> bool:
            assert processing_token == "expired-token"
            self.calls.append(("lease", task_id, result))
            return False

        def mark_completed_after_processing_timeout(
            self,
            task_id: int,
            result: dict[str, Any],
        ) -> bool:
            self.calls.append(("timeout", task_id, result))
            return True

    class FakeLimiter:
        def acquire(self, _user_id: int, _scope: str) -> str:
            return "lease"

        def release(self, _lease: str) -> None:
            return None

    @contextmanager
    def fake_mysql_connection() -> Any:
        yield object()

    monkeypatch.setattr(
        interviews_api,
        "_load_task_for_execution",
        lambda _task_id, **_kwargs: task,
    )
    monkeypatch.setattr(interviews_api, "_start_interview_task_heartbeat", lambda _task: None)
    monkeypatch.setattr(interviews_api, "usage_limiter", FakeLimiter())
    monkeypatch.setattr(
        interviews_api,
        "_run_interview_operation",
        lambda _task, _payload: {"ok": True},
    )
    monkeypatch.setattr(interviews_api, "mysql_connection", fake_mysql_connection)
    monkeypatch.setattr(interviews_api, "InterviewOperationTaskRepository", FakeTaskRepository)

    interviews_api.run_interview_operation_task(task.id)

    assert FakeTaskRepository.calls == [
        ("lease", 8, {"ok": True}),
        ("timeout", 8, {"ok": True}),
    ]


def test_interview_task_repository_claims_recoverable_tasks() -> None:
    method_source = __import__("inspect").getsource(InterviewOperationTaskRepository.claim_due_task)

    assert "processing_timeout" in method_source
    assert "status = 'pending'" in method_source
    assert "LAST_INSERT_ID" in method_source
    assert "heartbeat_at" in method_source


def test_interview_task_terminal_updates_are_scoped_to_processing_lease() -> None:
    completed_source = __import__("inspect").getsource(
        InterviewOperationTaskRepository.mark_completed
    )
    failed_source = __import__("inspect").getsource(InterviewOperationTaskRepository.mark_failed)
    heartbeat_source = __import__("inspect").getsource(InterviewOperationTaskRepository.heartbeat)

    for source in (completed_source, failed_source, heartbeat_source):
        assert "status = 'processing'" in source
        assert "processing_token" in source


@pytest.mark.parametrize(
    ("repository_class", "method_name"),
    [
        (InterviewOperationTaskRepository, "mark_processing"),
        (InterviewOperationTaskRepository, "mark_completed"),
        (InterviewOperationTaskRepository, "mark_completed_after_processing_timeout"),
        (InterviewOperationTaskRepository, "mark_failed"),
        (ResumeRepository, "mark_parse_task_processing"),
        (ResumeRepository, "mark_parse_task_completed"),
        (ResumeRepository, "mark_parse_task_failed"),
    ],
)
def test_async_task_status_writes_use_utc_timestamps(
    repository_class: type,
    method_name: str,
) -> None:
    method_source = __import__("inspect").getsource(getattr(repository_class, method_name))

    assert "UTC_TIMESTAMP()" in method_source
    assert "CURRENT_TIMESTAMP" not in method_source


def test_interview_task_repository_creates_task_only_for_owned_interview_round() -> None:
    connection = _TaskRepositoryConnection(
        interview_owners={10: 1},
        rounds={(10, 20)},
    )
    repository = InterviewOperationTaskRepository(connection)

    task = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="start_round",
        payload={"round_id": 20},
    )

    assert task is not None
    assert task.user_id == 1
    assert task.interview_id == 10
    assert task.round_id == 20
    assert task.payload == {"round_id": 20}
    assert len(connection.tasks) == 1
    method_source = __import__("inspect").getsource(
        InterviewOperationTaskRepository.create_task_for_owned_interview
    )
    assert "FOR UPDATE" in method_source


def test_interview_task_repository_blocks_duplicate_active_scope_task() -> None:
    connection = _TaskRepositoryConnection(
        interview_owners={10: 1},
        rounds={(10, 20)},
    )
    repository = InterviewOperationTaskRepository(connection)
    scope_operations = interviews_api.ROUND_MUTATING_OPERATIONS

    task = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="start_round",
        payload={"round_id": 20},
        exclusive_operations=scope_operations,
    )
    duplicate = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="regenerate_round_question",
        payload={"round_id": 20, "question_id": 30},
        exclusive_operations=scope_operations,
    )

    assert task is not None
    assert duplicate is None
    assert repository.has_active_task_for_scope(
        user_id=1,
        interview_id=10,
        operations=scope_operations,
    )
    assert len(connection.tasks) == 1


@pytest.mark.parametrize(
    (
        "operation",
        "round_id",
        "payload",
        "scope_operations",
        "existing_status",
    ),
    [
        (
            "answer_round_question",
            20,
            {"round_id": 20, "question_id": 30, "answer": "先定位瓶颈。"},
            interviews_api.ROUND_MUTATING_OPERATIONS,
            "pending",
        ),
        (
            "finish_round",
            20,
            {"round_id": 20, "finish_type": "normal"},
            interviews_api.ROUND_MUTATING_OPERATIONS,
            "processing",
        ),
        (
            "finish_interview",
            None,
            {"finish_type": "normal"},
            interviews_api.INTERVIEW_MUTATING_OPERATIONS,
            "pending",
        ),
    ],
)
def test_interview_task_repository_blocks_duplicate_active_scope_for_core_tasks(
    operation: str,
    round_id: int | None,
    payload: dict[str, Any],
    scope_operations: tuple[str, ...],
    existing_status: str,
) -> None:
    connection = _TaskRepositoryConnection(
        interview_owners={10: 1},
        rounds={(10, 20)},
    )
    repository = InterviewOperationTaskRepository(connection)

    task = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=round_id,
        operation=operation,
        payload=payload,
        exclusive_operations=scope_operations,
    )
    assert task is not None
    connection.tasks[task.id]["status"] = existing_status

    duplicate = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=round_id,
        operation=operation,
        payload=payload,
        exclusive_operations=scope_operations,
    )

    assert duplicate is None
    assert repository.has_active_task_for_scope(
        user_id=1,
        interview_id=10,
        operations=scope_operations,
    )
    assert len(connection.tasks) == 1


@pytest.mark.parametrize(
    (
        "active_operation",
        "active_round_id",
        "active_payload",
        "next_operation",
        "next_round_id",
        "next_payload",
        "conflicting_operations",
    ),
    [
        (
            "answer_round_question",
            20,
            {"round_id": 20, "question_id": 30, "answer": "先定位瓶颈。"},
            "finish_round",
            20,
            {"round_id": 20, "finish_type": "normal"},
            interviews_api.ROUND_MUTATING_OPERATIONS,
        ),
        (
            "answer_round_question",
            20,
            {"round_id": 20, "question_id": 30, "answer": "先定位瓶颈。"},
            "finish_interview",
            None,
            {"finish_type": "normal"},
            interviews_api.INTERVIEW_MUTATING_OPERATIONS,
        ),
    ],
)
def test_interview_task_repository_blocks_cross_operation_state_mutations(
    active_operation: str,
    active_round_id: int | None,
    active_payload: dict[str, Any],
    next_operation: str,
    next_round_id: int | None,
    next_payload: dict[str, Any],
    conflicting_operations: tuple[str, ...],
) -> None:
    connection = _TaskRepositoryConnection(
        interview_owners={10: 1},
        rounds={(10, 20)},
    )
    repository = InterviewOperationTaskRepository(connection)
    active = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=active_round_id,
        operation=active_operation,
        payload=active_payload,
        exclusive_operations=conflicting_operations,
    )
    assert active is not None
    connection.tasks[active.id]["status"] = "processing"

    blocked = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=next_round_id,
        operation=next_operation,
        payload=next_payload,
        exclusive_operations=conflicting_operations,
    )

    assert blocked is None
    assert len(connection.tasks) == 1


def test_interview_task_repository_does_not_create_foreign_or_unscoped_round_task() -> None:
    connection = _TaskRepositoryConnection(
        interview_owners={10: 1, 11: 1},
        rounds={(11, 20)},
    )
    repository = InterviewOperationTaskRepository(connection)

    foreign_interview = repository.create_task_for_owned_interview(
        user_id=2,
        interview_id=10,
        operation="finish_interview",
        payload={"finish_type": "normal"},
    )
    wrong_round = repository.create_task_for_owned_interview(
        user_id=1,
        interview_id=10,
        round_id=20,
        operation="start_round",
        payload={"round_id": 20},
    )

    assert foreign_interview is None
    assert wrong_round is None
    assert connection.tasks == {}


def test_resume_background_task_holds_usage_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    task = ResumeParseTaskRecord(
        id=5,
        user_id=8,
        original_file_path="resume.docx",
        content_hash="hash",
        status="processing",
        created_at=datetime(2026, 7, 7, 12, 0),
        processing_token="lease-token",
    )

    class FakeRepository:
        completed: list[tuple[int, str]] = []

        def __init__(self, _connection: Any) -> None:
            pass

        def get_parse_task_for_user(
            self,
            task_id: int,
            user_id: int,
        ) -> ResumeParseTaskRecord | None:
            return task if task_id == task.id and user_id == task.user_id else None

        def complete_parse_task(
            self,
            task_id: int,
            processing_token: str,
            structured_data: dict[str, Any],
        ) -> Any:
            events.append(f"complete:{task_id}:{processing_token}")
            self.completed.append((task_id, processing_token))
            return type("Resume", (), {"id": 99})()

    class FakeParser:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def parse(self, _path: Any) -> dict[str, Any]:
            events.append("parse")
            return {"basic_info": {"name": "Alice"}}

    class FakeLimiter:
        @contextmanager
        def guard(self, user_id: int, scope: str) -> Any:
            events.append(f"acquire:{user_id}:{scope}")
            try:
                yield
            finally:
                events.append("release")

    @contextmanager
    def fake_mysql_connection() -> Any:
        yield object()

    monkeypatch.setattr(resumes_api, "mysql_connection", fake_mysql_connection)
    monkeypatch.setattr(resumes_api, "ResumeRepository", FakeRepository)
    monkeypatch.setattr(resumes_api, "ResumeParserService", FakeParser)
    monkeypatch.setattr(resumes_api, "get_llm_client", lambda: object())
    monkeypatch.setattr(resumes_api, "usage_limiter", FakeLimiter())
    monkeypatch.setattr(resumes_api, "_start_resume_parse_task_heartbeat", lambda _task: None)

    resumes_api.parse_resume_upload_task(task.id, task.user_id, already_claimed=True)

    assert events == [
        "acquire:8:resume_upload",
        "parse",
        "release",
        "complete:5:lease-token",
    ]
    assert FakeRepository.completed == [(5, "lease-token")]


def test_resume_repository_claims_recoverable_parse_tasks() -> None:
    method_source = __import__("inspect").getsource(ResumeRepository.claim_due_parse_task)

    assert "processing_timeout" in method_source
    assert "status = 'pending'" in method_source
    assert "LAST_INSERT_ID" in method_source
    assert "heartbeat_at" in method_source


def test_resume_parse_task_terminal_updates_require_active_lease() -> None:
    for method in (
        ResumeRepository.mark_parse_task_completed,
        ResumeRepository.mark_parse_task_failed,
        ResumeRepository.heartbeat_parse_task,
    ):
        source = __import__("inspect").getsource(method)
        assert "status = 'processing'" in source
        assert "processing_token" in source


def test_stale_resume_parse_lease_cannot_create_resume() -> None:
    class MissingLeaseCursor:
        def __enter__(self) -> "MissingLeaseCursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _sql: str, _params: Any = None) -> None:
            return None

        def fetchone(self) -> None:
            return None

    class MissingLeaseConnection:
        def cursor(self) -> MissingLeaseCursor:
            return MissingLeaseCursor()

    class GuardedRepository(ResumeRepository):
        def create(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("stale worker must not create a resume")

    repository = GuardedRepository(MissingLeaseConnection())

    assert repository.complete_parse_task(5, "stale-token", {"name": "Alice"}) is None
