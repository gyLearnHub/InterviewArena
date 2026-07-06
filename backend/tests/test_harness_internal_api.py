import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.api.internal_harness import (
    evaluate_hard_rules,
    mark_event_write_failed,
    require_trace_created,
    validate_scoring_context_isolation,
    validate_tool_whitelist,
)
from app.api.internal_harness import (
    get_harness_repository as get_internal_harness_repository,
)
from app.api.interviews import (
    get_harness_repository as get_public_harness_repository,
)
from app.api.interviews import (
    get_interview_repository,
)
from app.core.errors import AppError, ErrorCode
from app.deps import get_current_user
from app.repositories.users import UserRecord
from fastapi.testclient import TestClient
from main import create_app

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "harness"


@pytest.fixture()
def harness_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, "_FakeHarnessRepository"]:
    monkeypatch.setenv("HARNESS_INTERNAL_API_ENABLED", "true")
    monkeypatch.setenv("HARNESS_INTERNAL_USER_IDS", "1")
    repository = _FakeHarnessRepository()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_internal_harness_repository] = lambda: repository
    return TestClient(app, raise_server_exceptions=False), repository


def test_internal_api_is_hidden_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_INTERNAL_API_ENABLED", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USER_IDS", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USERNAMES", raising=False)
    repository = _FakeHarnessRepository()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_internal_harness_repository] = lambda: repository
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/internal/harness/interviews/100/traces")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND


def test_internal_api_rejects_non_internal_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESS_INTERNAL_API_ENABLED", "true")
    monkeypatch.delenv("HARNESS_INTERNAL_USER_IDS", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USERNAMES", raising=False)
    repository = _FakeHarnessRepository()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_internal_harness_repository] = lambda: repository
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/internal/harness/interviews/100/traces")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == ErrorCode.FORBIDDEN


def test_public_harness_status_returns_current_users_real_records() -> None:
    repository = _FakeHarnessRepository()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_interview_repository] = lambda: _FakeInterviewRepository()
    app.dependency_overrides[get_public_harness_repository] = lambda: repository
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/interviews/100/harness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["interview_id"] == 100
    assert payload["harness_status"] == "completed"
    assert [item["id"] for item in payload["traces"]] == [11, 12]
    assert payload["evaluations"][0]["rule_name"] == "context_isolation"
    assert payload["checkpoints"][0]["checkpoint_type"] == "question_generated"


def test_public_harness_status_hides_foreign_interview() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_interview_repository] = lambda: _FakeInterviewRepository()
    app.dependency_overrides[get_public_harness_repository] = lambda: _FakeHarnessRepository()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/interviews/200/harness")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND


def test_list_traces_returns_only_current_users_interview(
    harness_client: tuple[TestClient, "_FakeHarnessRepository"],
) -> None:
    client, _repository = harness_client

    response = client.get("/api/internal/harness/interviews/100/traces")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [11, 12]
    assert payload["items"][1]["event_write_failed"] is True


def test_internal_api_rejects_foreign_interview(
    harness_client: tuple[TestClient, "_FakeHarnessRepository"],
) -> None:
    client, _repository = harness_client

    response = client.get("/api/internal/harness/interviews/200/traces")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == ErrorCode.FORBIDDEN


def test_trace_detail_rejects_foreign_trace(
    harness_client: tuple[TestClient, "_FakeHarnessRepository"],
) -> None:
    client, _repository = harness_client

    response = client.get("/api/internal/harness/traces/21")

    assert response.status_code == 404


def test_checkpoint_and_evaluation_queries_are_user_scoped(
    harness_client: tuple[TestClient, "_FakeHarnessRepository"],
) -> None:
    client, _repository = harness_client

    checkpoints = client.get("/api/internal/harness/interviews/100/checkpoints")
    evaluations = client.get("/api/internal/harness/interviews/100/evaluations")

    assert checkpoints.status_code == 200
    assert checkpoints.json()["items"][0]["checkpoint_type"] == "question_generated"
    assert evaluations.status_code == 200
    assert evaluations.json()["items"][0]["rule_name"] == "context_isolation"


def test_improvement_candidates_are_view_only(
    harness_client: tuple[TestClient, "_FakeHarnessRepository"],
) -> None:
    client, repository = harness_client

    response = client.get("/api/internal/harness/improvement-candidates")

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"id": 91, "user_id": 1, "candidate_type": "prompt", "status": "pending"}
    ]
    assert repository.business_writes == 0


def test_replay_and_rerun_do_not_mutate_business_data(
    harness_client: tuple[TestClient, "_FakeHarnessRepository"],
) -> None:
    client, repository = harness_client

    replay = client.post(
        "/api/internal/harness/traces/11/replay",
        json={"reason": "debug failed event", "options": {"dry_run": True}},
    )
    rerun = client.post(
        "/api/internal/harness/nodes/round-1-score/rerun",
        json={"reason": "rerun failed node"},
    )

    assert replay.status_code == 200
    assert replay.json()["status"] == "completed"
    assert replay.json()["source_trace_id"] == 11
    assert rerun.status_code == 200
    assert rerun.json()["status"] == "completed"
    assert rerun.json()["source_node_id"] == "round-1-score"
    assert repository.replay_runs == [
        {"mode": "replay", "trace_id": 11, "user_id": 1},
        {"mode": "rerun", "node_id": "round-1-score", "user_id": 1},
    ]
    assert repository.business_writes == 0


def test_trace_guard_blocks_when_main_trace_creation_fails() -> None:
    with pytest.raises(AppError) as exc_info:
        require_trace_created(None)

    assert exc_info.value.status_code == 503


def test_event_write_failure_marks_trace_without_blocking() -> None:
    trace = mark_event_write_failed({"id": 12, "status": "running"}, "event insert failed")

    assert trace["event_write_failed"] is True
    assert trace["event_write_error"] == "event insert failed"
    assert trace["status"] == "running"


def test_scoring_node_rejects_long_term_memory_context() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_scoring_context_isolation(
            "question_evaluation",
            {"candidate_memories": [{"id": 1, "content": "跨轮记忆"}]},
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.details == {"forbidden_keys": ["candidate_memories"]}


def test_tool_whitelist_rejects_raw_sql_and_shell() -> None:
    for tool_name in ["raw_sql", "shell"]:
        with pytest.raises(AppError):
            validate_tool_whitelist(tool_name)

    validate_tool_whitelist("question_evaluator")


def test_hard_rule_failure_fails_overall_evaluation() -> None:
    result = evaluate_hard_rules(
        [
            {"rule_name": "question_repeat", "status": "warning"},
            {"rule_name": "context_isolation", "status": "failed", "hard_rule": True},
        ]
    )

    assert result == "FAIL"


class _FakeHarnessRepository:
    def __init__(self) -> None:
        self.interview_owners = {100: 1, 200: 2}
        self.traces = _load_traces()
        self.traces.append(
            {
                "id": 21,
                "user_id": 2,
                "interview_id": 200,
                "node_id": "foreign-node",
                "node_type": "question_generation",
                "status": "completed",
            }
        )
        self.checkpoints = [
            {
                "id": 31,
                "user_id": 1,
                "interview_id": 100,
                "node_id": "round-1-question",
                "checkpoint_type": "question_generated",
                "status": "available",
            }
        ]
        self.evaluations = [
            {
                "id": 41,
                "user_id": 1,
                "interview_id": 100,
                "rule_name": "context_isolation",
                "status": "passed",
                "severity": "high",
                "hard_rule": True,
            }
        ]
        self.candidates = [
            {"id": 91, "user_id": 1, "candidate_type": "prompt", "status": "pending"},
            {"id": 92, "user_id": 2, "candidate_type": "code", "status": "pending"},
        ]
        self.replay_runs: list[dict[str, Any]] = []
        self.business_writes = 0

    def list_traces(self, interview_id: int, user_id: int) -> list[dict[str, Any]]:
        self._require_owner(interview_id, user_id)
        return [
            trace
            for trace in self.traces
            if trace["interview_id"] == interview_id and trace["user_id"] == user_id
        ]

    def get_trace(self, trace_id: int, user_id: int) -> dict[str, Any] | None:
        return next(
            (
                trace
                for trace in self.traces
                if trace["id"] == trace_id and trace["user_id"] == user_id
            ),
            None,
        )

    def list_checkpoints(self, interview_id: int, user_id: int) -> list[dict[str, Any]]:
        self._require_owner(interview_id, user_id)
        return [
            checkpoint
            for checkpoint in self.checkpoints
            if checkpoint["interview_id"] == interview_id and checkpoint["user_id"] == user_id
        ]

    def list_rule_evaluations(self, interview_id: int, user_id: int) -> list[dict[str, Any]]:
        self._require_owner(interview_id, user_id)
        return [
            evaluation
            for evaluation in self.evaluations
            if evaluation["interview_id"] == interview_id and evaluation["user_id"] == user_id
        ]

    def list_improvement_candidates(
        self,
        user_id: int,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            candidate
            for candidate in self.candidates
            if candidate["user_id"] == user_id
            and (status is None or candidate["status"] == status)
        ]

    def replay_trace(
        self,
        trace_id: int,
        user_id: int,
        reason: str | None,
        options: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        assert reason is not None
        assert options == {"dry_run": True}
        self.replay_runs.append({"mode": mode, "trace_id": trace_id, "user_id": user_id})
        return {
            "replay_run_id": "run-replay-1",
            "status": "completed",
            "result": {"changed": False},
        }

    def rerun_node(
        self,
        node_id: str,
        user_id: int,
        reason: str | None,
        options: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        assert reason is not None
        assert options == {}
        self.replay_runs.append({"mode": mode, "node_id": node_id, "user_id": user_id})
        return {"replay_run_id": "run-rerun-1", "status": "completed", "result": {"changed": False}}

    def _require_owner(self, interview_id: int, user_id: int) -> None:
        if self.interview_owners.get(interview_id) != user_id:
            raise AppError(ErrorCode.FORBIDDEN, status_code=403)


class _FakeInterviewRepository:
    def get_interview_for_user(self, interview_id: int, user_id: int) -> Any | None:
        if interview_id != 100 or user_id != 1:
            return None
        return SimpleNamespace(
            id=100,
            harness_status="completed",
            recovery_count=1,
            had_degradation=False,
        )


def _load_traces() -> list[dict[str, Any]]:
    return json.loads((FIXTURE_DIR / "sample_traces.json").read_text(encoding="utf-8"))
