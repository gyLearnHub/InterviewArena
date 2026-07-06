from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from app.evolution import scheduler as scheduler_module
from app.evolution.scheduler import run_daily_inspection, run_scheduled_daily_inspection_once
from app.evolution.triggers import build_daily_inspection_trigger, build_manual_trigger


def test_build_manual_trigger_keeps_audit_fields() -> None:
    trigger = build_manual_trigger(
        trigger_type="manual",
        trigger_reason="developer requested inspection",
        sample_count=3,
        data_scope={"interview_ids": [1, 2, 3]},
        anonymization_status="anonymized",
        audit_metadata={"ticket": "EVO-1"},
    )

    assert trigger.trigger_type == "manual"
    assert trigger.trigger_reason == "developer requested inspection"
    assert trigger.sample_count == 3
    assert trigger.data_scope == {"interview_ids": [1, 2, 3]}
    assert trigger.anonymization_status == "anonymized"
    assert trigger.audit_metadata == {"ticket": "EVO-1"}


def test_build_manual_trigger_supports_internal_trigger_types() -> None:
    for trigger_type in ["immediate", "sample_10", "sample_50"]:
        trigger = build_manual_trigger(
            trigger_type=trigger_type,
            trigger_reason="quality signal matched",
        )

        assert trigger.trigger_type == trigger_type


def test_build_manual_trigger_rejects_blank_reason() -> None:
    with pytest.raises(ValueError):
        build_manual_trigger(trigger_type="manual", trigger_reason=" ")


def test_daily_inspection_trigger_records_sample_scope() -> None:
    trigger = build_daily_inspection_trigger(
        trigger_reason="daily manual check",
        sample_count=10,
        sample_scope={"window": "24h"},
    )

    assert trigger.trigger_type == "daily_inspection"
    assert trigger.data_scope == {
        "inspection_type": "daily",
        "sample_scope": {"window": "24h"},
    }


def test_run_daily_inspection_creates_run_record() -> None:
    repository = _FakeEvolutionRepository()

    result = run_daily_inspection(
        repository,
        user_id=1,
        trigger_reason="daily manual check",
        sample_count=10,
        sample_scope={"window": "24h"},
        anonymization_status="aggregated_anonymized",
        audit_metadata={"source": "test"},
    )

    assert result["id"] == 1
    assert repository.runs[0]["trigger_type"] == "daily_inspection"
    assert repository.runs[0]["trigger_reason"] == "daily manual check"
    assert repository.runs[0]["sample_count"] == 10
    assert repository.runs[0]["anonymization_status"] == "aggregated_anonymized"
    assert repository.runs[0]["data_scope"]["sample_scope"] == {"window": "24h"}


def test_scheduled_daily_inspection_runs_once_per_day_at_configured_hour() -> None:
    repository = _FakeEvolutionRepository()
    repository.completed_signal_count = 12

    skipped, last_run_date = run_scheduled_daily_inspection_once(
        repository,
        now=datetime(2026, 7, 4, 23, 30),
        last_run_date=None,
        inspection_hour=0,
    )
    first, last_run_date = run_scheduled_daily_inspection_once(
        repository,
        now=datetime(2026, 7, 5, 0, 1),
        last_run_date=last_run_date,
        inspection_hour=0,
    )
    second, last_run_date = run_scheduled_daily_inspection_once(
        repository,
        now=datetime(2026, 7, 5, 0, 30),
        last_run_date=last_run_date,
        inspection_hour=0,
    )

    assert skipped is None
    assert first is not None
    assert second is None
    assert repository.runs[0]["trigger_type"] == "daily_inspection"
    assert repository.runs[0]["sample_count"] == 12
    assert repository.runs[0]["audit_metadata"]["source"] == "evolution_daily_scheduler"


def test_scheduled_daily_inspection_analyzes_latest_quality_signal() -> None:
    repository = _FakeEvolutionRepository()
    repository.completed_signal_count = 1
    repository.quality_signals.append(
        SimpleNamespace(
            id=9,
            user_id=1,
            interview_id=99,
            signal_type="interview_completed",
            severity="critical",
            hard_trigger=True,
            threshold_trigger=False,
            metrics={"harness_summary": {"failed_hard_rules": 1}},
            source_refs={"harness": {"failed_hard_rules": 1}},
        )
    )

    run, _last_run_date = run_scheduled_daily_inspection_once(
        repository,
        now=datetime(2026, 7, 5, 0, 1),
        last_run_date=None,
        inspection_hour=0,
    )

    assert run is not None
    assert repository.runs[0]["status"] == "completed"
    assert (
        repository.runs[0]["audit_metadata"]["validation_result"]["candidate_count"]
        == len(repository.candidates)
    )
    assert repository.candidates[0]["run_id"] == run["id"]
    assert repository.candidates[0]["candidate_type"] == "harness_rule_candidate"
    assert repository.candidates[0]["status"] == "waiting_approval"


def test_scheduled_daily_inspection_does_not_reanalyze_failed_deduped_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FakeEvolutionRepository()
    repository.completed_signal_count = 1
    analyze_calls: list[int] = []

    def fail_after_candidate(repo: _FakeEvolutionRepository, run_id: int) -> None:
        analyze_calls.append(run_id)
        repo.create_candidate(
            run_id=run_id,
            candidate_type="harness_rule_candidate",
            target_artifact_key="harness.rules",
            risk_level="high",
            status="waiting_approval",
            proposal={},
            diff={},
            impact_scope={},
            root_cause={},
        )
        repo.update_evolution_run_status(
            run_id,
            status="failed",
            completed=True,
            error_message="boom",
        )
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "analyze_run", fail_after_candidate)
    now = datetime(2026, 7, 5, 0, 1)
    with pytest.raises(RuntimeError):
        run_scheduled_daily_inspection_once(
            repository,
            now=now,
            last_run_date=None,
            inspection_hour=0,
        )

    run, last_run_date = run_scheduled_daily_inspection_once(
        repository,
        now=now,
        last_run_date=None,
        inspection_hour=0,
    )

    assert run is not None
    assert last_run_date == now.date()
    assert analyze_calls == [1]
    assert len(repository.candidates) == 1


class _FakeEvolutionRepository:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []
        self.candidates: list[dict[str, object]] = []
        self.quality_signals: list[object] = []
        self.completed_signal_count = 0

    def create_evolution_run(self, **kwargs: object) -> dict[str, object]:
        key = (
            kwargs["trigger_type"],
            kwargs["trigger_reason"],
            kwargs.get("scope_type"),
            kwargs.get("scope_key"),
            repr(kwargs.get("data_scope")),
        )
        existing = next((run for run in self.runs if run["dedupe_key"] == key), None)
        if existing is not None:
            return existing
        run = {"id": len(self.runs) + 1, "status": "pending", "dedupe_key": key, **kwargs}
        self.runs.append(run)
        return run

    def get_evolution_run(self, run_id: int) -> dict[str, object] | None:
        return next((run for run in self.runs if run["id"] == run_id), None)

    def update_evolution_run_status(
        self,
        run_id: int,
        *,
        status: str,
        error_message: str | None = None,
        completed: bool = False,
    ) -> None:
        del completed
        run = self.get_evolution_run(run_id)
        assert run is not None
        run["status"] = status
        run["error_message"] = error_message

    def merge_evolution_run_audit_metadata(
        self,
        run_id: int,
        metadata: dict[str, object],
    ) -> None:
        run = self.get_evolution_run(run_id)
        assert run is not None
        audit_metadata = dict(run.get("audit_metadata") or {})
        audit_metadata.update(metadata)
        run["audit_metadata"] = audit_metadata

    def list_quality_signals(self, *, limit: int = 100) -> list[object]:
        return self.quality_signals[:limit]

    def create_candidate(self, **kwargs: object) -> dict[str, object]:
        candidate = {"id": len(self.candidates) + 1, **kwargs}
        self.candidates.append(candidate)
        return candidate

    def count_completed_quality_signals(self) -> int:
        return self.completed_signal_count
