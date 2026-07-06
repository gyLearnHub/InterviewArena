from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from app.api.internal_evolution import get_evolution_repository
from app.core.errors import ErrorCode
from app.deps import get_current_user
from app.repositories.evolution import EvolutionRepository
from app.repositories.users import UserRecord
from fastapi.testclient import TestClient
from main import create_app


@pytest.fixture()
def evolution_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, _FakeEvolutionRepository]:
    monkeypatch.setenv("HARNESS_INTERNAL_API_ENABLED", "true")
    monkeypatch.setenv("HARNESS_INTERNAL_USER_IDS", "1")
    repository = _FakeEvolutionRepository()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_evolution_repository] = lambda: repository
    return TestClient(app, raise_server_exceptions=False), repository


def test_internal_evolution_api_is_hidden_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_INTERNAL_API_ENABLED", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USER_IDS", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USERNAMES", raising=False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_evolution_repository] = lambda: _FakeEvolutionRepository()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/internal/evolution/summary")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND


def test_internal_evolution_write_api_is_hidden_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HARNESS_INTERNAL_API_ENABLED", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USER_IDS", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USERNAMES", raising=False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_evolution_repository] = lambda: _FakeEvolutionRepository()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/internal/evolution/runs",
        json={"trigger_type": "manual", "trigger_reason": "manual check"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND


def test_internal_evolution_api_rejects_non_internal_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HARNESS_INTERNAL_API_ENABLED", "true")
    monkeypatch.delenv("HARNESS_INTERNAL_USER_IDS", raising=False)
    monkeypatch.delenv("HARNESS_INTERNAL_USERNAMES", raising=False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(1, "alice", "hash")
    app.dependency_overrides[get_evolution_repository] = lambda: _FakeEvolutionRepository()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/internal/evolution/summary")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == ErrorCode.FORBIDDEN


def test_authorized_internal_user_can_read_empty_evolution_data(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, _repository = evolution_client

    assert client.get("/api/internal/evolution/summary").json() == {
        "run_count": 0,
        "candidate_count": 0,
        "risk_distribution": {},
        "latest_quality_signals": [],
        "version_bundle_status": {},
    }
    assert client.get("/api/internal/evolution/runs").json() == {"items": []}
    assert client.get("/api/internal/evolution/candidates").json() == {"items": []}
    assert client.get("/api/internal/evolution/version-bundles").json() == {"items": []}
    assert client.get("/api/internal/evolution/validation-runs").json() == {"items": []}
    assert client.get("/api/internal/evolution/audit-events").json() == {"items": []}


def test_repository_summary_filters_latest_quality_signals_by_user() -> None:
    repository = _SummaryRepository()

    summary = EvolutionRepository.get_evolution_summary(repository, user_id=1)  # type: ignore[arg-type]

    assert repository.quality_signal_user_id == 1
    assert summary["latest_quality_signals"] == [
        {
            "id": 1,
            "user_id": 1,
            "interview_id": 10,
            "signal_type": "interview_completed",
        }
    ]


def test_manual_run_can_be_created(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client

    response = client.post(
        "/api/internal/evolution/runs",
        json={
            "trigger_type": "manual",
            "trigger_reason": "developer requested analysis",
            "sample_count": 2,
            "data_scope": {"interview_ids": [100, 101]},
            "anonymization_status": "anonymized",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 1
    assert payload["trigger_type"] == "manual"
    assert payload["trigger_reason"] == "developer requested analysis"
    assert payload["data_scope"] == {"interview_ids": [100, 101]}
    assert payload["audit_metadata"]["triggered_by_user_id"] == 1
    assert repository.business_writes == 0


def test_daily_inspection_run_can_be_created(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client

    response = client.post(
        "/api/internal/evolution/runs",
        json={
            "trigger_type": "daily_inspection",
            "trigger_reason": "manual daily inspection",
            "sample_count": 10,
            "sample_scope": {"window": "24h"},
            "anonymization_status": "aggregated_anonymized",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trigger_type"] == "daily_inspection"
    assert payload["data_scope"] == {
        "inspection_type": "daily",
        "sample_scope": {"window": "24h"},
    }
    assert payload["anonymization_status"] == "aggregated_anonymized"
    assert repository.runs[0]["audit_metadata"]["triggered_by_username"] == "alice"


def test_internal_trigger_types_can_be_created(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client

    for trigger_type in ["immediate", "sample_10", "sample_50"]:
        response = client.post(
            "/api/internal/evolution/runs",
            json={
                "trigger_type": trigger_type,
                "trigger_reason": f"{trigger_type} matched",
                "sample_count": 10,
                "sample_scope": {"job_family": "backend"},
                "anonymization_status": "aggregated_anonymized",
            },
        )

        assert response.status_code == 200
        assert response.json()["trigger_type"] == trigger_type

    assert [run["trigger_type"] for run in repository.runs] == [
        "immediate",
        "sample_10",
        "sample_50",
    ]


def test_candidate_detail_is_read_only(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 11,
            "user_id": 1,
            "candidate_type": "prompt",
            "risk_level": "low",
            "status": "pending_validation",
        }
    )

    response = client.get("/api/internal/evolution/candidates/11")

    assert response.status_code == 200
    assert response.json()["id"] == 11
    assert repository.business_writes == 0


def test_approve_candidate_records_manual_approval(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 12,
            "user_id": 1,
            "candidate_type": "prompt",
            "risk_level": "medium",
            "status": "waiting_approval",
        }
    )

    response = client.post(
        "/api/internal/evolution/candidates/12/approve",
        json={"manual_note": "looks good", "apply_after_approval": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["approved_by"] == 1
    assert payload["manual_note"] == "looks good"
    assert payload["audit_metadata"]["action"] == "approve"
    assert repository.business_writes == 0


def test_high_risk_candidate_cannot_be_auto_applied(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 13,
            "user_id": 1,
            "candidate_type": "backend_patch",
            "risk_level": "high",
            "status": "waiting_approval",
        }
    )

    response = client.post(
        "/api/internal/evolution/candidates/13/approve",
        json={"manual_note": "confirm only", "apply_after_approval": True},
    )

    assert response.status_code == 403
    assert repository.business_writes == 0


def test_high_risk_candidate_can_record_manual_confirmation_without_auto_apply(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 131,
            "user_id": 1,
            "candidate_type": "backend_patch",
            "risk_level": "high",
            "status": "waiting_approval",
        }
    )

    response = client.post(
        "/api/internal/evolution/candidates/131/approve",
        json={"manual_note": "manual confirmation only", "apply_after_approval": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert repository.business_writes == 0


def test_reject_candidate_records_audit_fields(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 14,
            "user_id": 1,
            "candidate_type": "flow_config",
            "risk_level": "medium",
            "status": "waiting_approval",
        }
    )

    response = client.post(
        "/api/internal/evolution/candidates/14/reject",
        json={"reason": "too risky", "manual_note": "defer"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["rejected_by"] == 1
    assert response.json()["audit_metadata"]["action"] == "reject"


def test_rerun_validation_creates_validation_run(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 15,
            "user_id": 1,
            "candidate_type": "prompt",
            "risk_level": "low",
            "status": "pending_validation",
        }
    )

    response = client.post(
        "/api/internal/evolution/candidates/15/rerun-validation",
        json={"reason": "refresh samples", "sample_count": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_id"] == 15
    assert payload["validation_type"] == "manual_rerun"
    assert payload["status"] == "pending"
    assert payload["audit_metadata"]["action"] == "rerun_validation"
    assert repository.validation_runs[0]["sample_count"] == 10


def test_rollback_candidate_calls_rollback_service(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 16,
            "user_id": 1,
            "candidate_type": "prompt",
            "risk_level": "low",
            "status": "approved",
            "rollback_point": "bundle-previous",
        }
    )

    response = client.post(
        "/api/internal/evolution/candidates/16/rollback",
        json={"reason": "post validation failed", "manual_note": "rollback now"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"
    assert response.json()["rolled_back_by"] == 1
    assert response.json()["audit_metadata"]["action"] == "rollback"


def test_frontend_suggestion_cannot_be_approved_or_auto_applied(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.candidates.append(
        {
            "id": 17,
            "user_id": 1,
            "candidate_type": "frontend_suggestion",
            "risk_level": "high",
            "status": "waiting_approval",
        }
    )

    approve = client.post(
        "/api/internal/evolution/candidates/17/approve",
        json={"apply_after_approval": True},
    )
    handled = client.post(
        "/api/internal/evolution/frontend-suggestions/17/mark-handled",
        json={"manual_note": "copied to frontend task"},
    )
    regenerated = client.post(
        "/api/internal/evolution/frontend-suggestions/17/request-regeneration",
        json={"manual_note": "needs safer patch draft"},
    )

    assert approve.status_code == 403
    assert handled.status_code == 200
    assert handled.json()["status"] == "frontend_handled"
    assert handled.json()["handled_by"] == 1
    assert regenerated.status_code == 200
    assert regenerated.json()["status"] == "regeneration_requested"
    assert regenerated.json()["requested_by"] == 1
    assert repository.business_writes == 0


def test_no_public_evolution_interfaces(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, _repository = evolution_client

    response = client.get("/api/evolution/summary")
    apply_run = client.post("/api/internal/evolution/runs/1/apply")

    assert response.status_code == 404
    assert apply_run.status_code == 404


def test_audit_events_can_be_filtered(
    evolution_client: tuple[TestClient, _FakeEvolutionRepository],
) -> None:
    client, repository = evolution_client
    repository.audit_events.append(
        {
            "id": 1,
            "event_type": "candidate_approved",
            "run_id": 1,
            "candidate_id": 12,
            "actor_user_id": 1,
            "metadata": {"reason": "ok"},
        }
    )

    response = client.get(
        "/api/internal/evolution/audit-events",
        params={"candidate_id": 12, "event_type": "candidate_approved"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["event_type"] == "candidate_approved"


class _FakeEvolutionRepository:
    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.candidates: list[dict[str, Any]] = []
        self.version_bundles: list[dict[str, Any]] = []
        self.validation_runs: list[dict[str, Any]] = []
        self.audit_events: list[dict[str, Any]] = []
        self.business_writes = 0

    def list_evolution_runs(
        self,
        *,
        user_id: int,
        trigger_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            run
            for run in self.runs[:limit]
            if run["user_id"] == user_id
            and (trigger_type is None or run["trigger_type"] == trigger_type)
            and (status is None or run.get("status") == status)
        ]

    def create_evolution_run(self, **kwargs: Any) -> dict[str, Any]:
        run = {
            "id": len(self.runs) + 1,
            "status": "pending",
            **kwargs,
        }
        self.runs.append(run)
        return run

    def approve_evolution_candidate(self, **kwargs: Any) -> dict[str, Any]:
        candidate = self._candidate_by_id(int(kwargs["candidate_id"]))
        candidate.update(
            {
                "status": "approved",
                "approval_status": "approved",
                "approved_by": kwargs["approved_by"],
                "manual_note": kwargs.get("manual_note"),
                "audit_metadata": kwargs["audit_metadata"],
            }
        )
        if kwargs.get("apply_after_approval"):
            self.business_writes += 1
        return candidate

    def reject_evolution_candidate(self, **kwargs: Any) -> dict[str, Any]:
        candidate = self._candidate_by_id(int(kwargs["candidate_id"]))
        candidate.update(
            {
                "status": "rejected",
                "approval_status": "rejected",
                "rejected_by": kwargs["rejected_by"],
                "manual_note": kwargs.get("manual_note"),
                "reason": kwargs.get("reason"),
                "audit_metadata": kwargs["audit_metadata"],
            }
        )
        return candidate

    def rerun_evolution_candidate_validation(self, **kwargs: Any) -> dict[str, Any]:
        validation_run = {
            "id": len(self.validation_runs) + 1,
            **kwargs,
        }
        self.validation_runs.append(validation_run)
        return validation_run

    def rollback_evolution_candidate(self, **kwargs: Any) -> dict[str, Any]:
        candidate = self._candidate_by_id(int(kwargs["candidate_id"]))
        candidate.update(
            {
                "status": "rolled_back",
                "rolled_back_by": kwargs["rolled_back_by"],
                "manual_note": kwargs.get("manual_note"),
                "reason": kwargs.get("reason"),
                "audit_metadata": kwargs["audit_metadata"],
            }
        )
        return candidate

    def mark_evolution_frontend_suggestion_handled(self, **kwargs: Any) -> dict[str, Any]:
        candidate = self._candidate_by_id(int(kwargs["candidate_id"]))
        candidate.update(
            {
                "status": "frontend_handled",
                "handled_by": kwargs["handled_by"],
                "manual_note": kwargs.get("manual_note"),
                "audit_metadata": kwargs["audit_metadata"],
            }
        )
        return candidate

    def request_evolution_frontend_suggestion_regeneration(self, **kwargs: Any) -> dict[str, Any]:
        candidate = self._candidate_by_id(int(kwargs["candidate_id"]))
        candidate.update(
            {
                "status": "regeneration_requested",
                "requested_by": kwargs["requested_by"],
                "manual_note": kwargs.get("manual_note"),
                "audit_metadata": kwargs["audit_metadata"],
            }
        )
        return candidate

    def list_evolution_candidates(
        self,
        *,
        user_id: int,
        status: str | None = None,
        risk_level: str | None = None,
        candidate_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            candidate
            for candidate in self.candidates[:limit]
            if candidate.get("user_id") in {None, user_id}
            and (status is None or candidate.get("status") == status)
            and (risk_level is None or candidate.get("risk_level") == risk_level)
            and (candidate_type is None or candidate.get("candidate_type") == candidate_type)
        ]

    def get_evolution_candidate(
        self,
        *,
        candidate_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate["id"] == candidate_id and candidate.get("user_id") in {None, user_id}
            ),
            None,
        )

    def list_evolution_version_bundles(
        self,
        *,
        user_id: int,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            bundle
            for bundle in self.version_bundles[:limit]
            if status is None or bundle.get("status") == status
        ]

    def list_evolution_validation_runs(
        self,
        *,
        user_id: int,
        candidate_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            run
            for run in self.validation_runs[:limit]
            if (candidate_id is None or run.get("candidate_id") == candidate_id)
            and (status is None or run.get("status") == status)
        ]

    def list_evolution_audit_events(
        self,
        *,
        user_id: int,
        run_id: int | None = None,
        candidate_id: int | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return [
            event
            for event in self.audit_events[:limit]
            if event.get("actor_user_id") in {None, user_id}
            and (run_id is None or event.get("run_id") == run_id)
            and (candidate_id is None or event.get("candidate_id") == candidate_id)
            and (event_type is None or event.get("event_type") == event_type)
        ]

    def _candidate_by_id(self, candidate_id: int) -> dict[str, Any]:
        candidate = self.get_evolution_candidate(candidate_id=candidate_id, user_id=1)
        assert candidate is not None
        return candidate


class _SummaryRepository:
    def __init__(self) -> None:
        self.quality_signal_user_id: int | None = None

    def list_evolution_runs(self, *, user_id: int | None, limit: int) -> list[Any]:
        return []

    def list_evolution_candidates(self, *, user_id: int | None, limit: int) -> list[Any]:
        return []

    def list_evolution_version_bundles(self, *, user_id: int | None, limit: int) -> list[Any]:
        return []

    def list_quality_signals(self, *, user_id: int | None, limit: int) -> list[Any]:
        self.quality_signal_user_id = user_id
        return [
            SimpleNamespace(
                id=1,
                user_id=user_id,
                interview_id=10,
                signal_type="interview_completed",
            )
        ]
