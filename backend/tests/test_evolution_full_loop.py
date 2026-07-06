from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.agents.registry import ROUND_SPECS
from app.evolution.anonymization import (
    aggregate_anonymized_signals,
    anonymize_signal_for_global_use,
)
from app.evolution.applier import apply_candidate
from app.evolution.candidate_generator import generate_candidates_from_signal
from app.evolution.code_patch import build_backend_patch_candidate
from app.evolution.regression import collect_regression_samples
from app.evolution.risk_classifier import classify_risk
from app.evolution.runtime import resolve_round_spec
from app.evolution.triggers import create_runs_for_quality_signal
from app.evolution.validation import validate_candidate


def test_hard_trigger_creates_deduped_run() -> None:
    repository = _LoopRepository()
    signal = SimpleNamespace(
        id=1,
        user_id=7,
        interview_id=99,
        signal_type="interview_completed",
        severity="critical",
        hard_trigger=True,
        threshold_trigger=False,
        source_refs={"harness": {"failed_hard_rules": 1}},
    )

    create_runs_for_quality_signal(repository, signal)
    create_runs_for_quality_signal(repository, signal)

    assert len(repository.runs) == 1
    assert repository.runs[0].trigger_type == "immediate"


def test_low_risk_prompt_candidate_applies_as_new_version_bundle() -> None:
    repository = _LoopRepository()
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="prompt",
        target_artifact_key="round_question_generation",
        risk_level="low",
        status="pending_validation",
        proposal={"action": "increase_evidence"},
        diff={"prompt_hint": "ask for evidence"},
        impact_scope={"scope": "question_generation"},
        root_cause={"category": "low_score"},
        approval_status="not_required",
    )

    bundle = apply_candidate(repository, candidate.id)

    assert bundle is not None
    assert repository.candidates[candidate.id].status == "auto_applied"
    assert repository.active_bundle_id == bundle.id
    assert repository.artifacts[0]["artifact_type"] == "prompt"
    assert any(
        event["event_type"] == "candidate_apply_completed"
        for event in repository.audit_events
    )


def test_applied_prompt_changes_new_runtime_behavior_and_rollback_restores() -> None:
    repository = _LoopRepository()
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="prompt",
        target_artifact_key="round_question_generation",
        risk_level="low",
        status="pending_validation",
        proposal={"action": "increase_evidence"},
        diff={"prompt_hint": "必须追问候选人给出量化证据。"},
        impact_scope={"scope": "question_generation"},
        root_cause={"category": "low_score"},
        approval_status="not_required",
    )

    bundle = apply_candidate(repository, candidate.id)
    assert bundle is not None
    effective = resolve_round_spec(
        repository,
        version_bundle_id=repository.active_bundle_id,
        base_spec=ROUND_SPECS["technical"],
    )
    assert "必须追问候选人给出量化证据" in effective.system_prompt

    from app.evolution.rollback import rollback_candidate

    assert rollback_candidate(repository, candidate.id, reason="verify rollback") is True
    assert any(event["event_type"] == "candidate_rolled_back" for event in repository.audit_events)
    restored = resolve_round_spec(
        repository,
        version_bundle_id=repository.active_bundle_id,
        base_spec=ROUND_SPECS["technical"],
    )
    assert "必须追问候选人给出量化证据" not in restored.system_prompt


def test_harness_blocker_prevents_auto_apply() -> None:
    repository = _LoopRepository()
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="prompt",
        target_artifact_key="round_question_generation",
        risk_level="low",
        status="pending_validation",
        proposal={"action": "change_prompt"},
        diff={"prompt_hint": "draft"},
        impact_scope={"scope": "question_generation"},
        root_cause={"category": "harness_failure"},
        approval_status="not_required",
    )

    assert apply_candidate(repository, candidate.id) is None
    assert repository.candidates[candidate.id].status == "waiting_approval"
    assert repository.validation_runs[0].status == "blocked"


def test_frontend_and_backend_patch_candidates_are_not_auto_applicable() -> None:
    assert classify_risk(candidate_type="frontend_suggestion", proposal={}, diff={}) == "high"
    patch = build_backend_patch_candidate(
        run_id=1,
        target_artifact_key="backend/app/services/example.py",
        patch_draft="Add a null guard only.",
        root_cause={"category": "null_guard"},
        test_result={"status": "passed", "command": "pytest backend/tests/test_example.py"},
        replay_result={"status": "passed", "replay_run_ids": [1]},
    )

    assert patch["candidate_type"] == "backend_patch"
    assert patch["status"] == "waiting_approval"
    assert patch["risk_level"] == "low"
    assert patch["proposal"]["will_modify_files"] is False
    assert patch["proposal"]["evidence_package"]["test_result"]["status"] == "passed"


def test_validation_records_complete_gate_evidence_package() -> None:
    repository = _LoopRepository()
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="prompt",
        target_artifact_key="round_question_generation",
        risk_level="low",
        status="pending_validation",
        proposal={"action": "increase_evidence"},
        diff={"prompt_hint": "ask for evidence"},
        impact_scope={"scope": "question_generation"},
        root_cause={"category": "low_score"},
        approval_status="not_required",
    )

    validation = validate_candidate(repository, candidate.id)

    assert validation.status == "passed"
    assert validation.hard_rule_result["status"] == "passed"
    assert validation.schema_result["status"] == "passed"
    assert validation.api_contract_result["status"] == "passed"
    assert validation.details["evidence_package"]["rollback_plan"]["candidate_id"] == candidate.id


def test_candidate_generation_covers_v3_2_quality_reason_codes() -> None:
    signal = SimpleNamespace(
        id=1,
        user_id=7,
        interview_id=99,
        signal_type="interview_completed",
        severity="warning",
        hard_trigger=False,
        threshold_trigger=True,
        metrics={
            "score": 72,
            "report_reliability_status": "normal",
            "trigger_reason_codes": [
                "question_repeat",
                "job_match_low",
                "follow_up_quality_low",
                "report_vague",
                "interface_degradation",
            ],
            "question_quality": {"repeat_count": 2, "repeat_rate": 0.4},
            "job_match": {"match_score": 0.1},
            "follow_up_quality": {"quality_score": 0.0},
            "report_quality": {"vagueness_score": 0.8},
            "harness_summary": {"failed_hard_rules": 0, "failed_traces": 0},
        },
        source_refs={},
    )

    candidates = generate_candidates_from_signal(signal)
    types = [item["candidate_type"] for item in candidates]
    root_categories = {item["root_cause"]["category"] for item in candidates}

    assert "backend_patch" in types
    assert "prompt" in types
    assert "report_template" in types
    assert {"question_repetition", "job_match_low", "follow_up_quality", "report_quality"}.issubset(
        root_categories
    )
    assert next(item for item in candidates if item["candidate_type"] == "backend_patch")[
        "proposal"
    ]["will_modify_files"] is False


def test_candidate_generation_covers_frontend_and_hard_signal_drafts() -> None:
    signal = SimpleNamespace(
        id=2,
        user_id=7,
        interview_id=100,
        signal_type="interview_completed",
        severity="critical",
        hard_trigger=True,
        threshold_trigger=True,
        metrics={
            "score": 82,
            "trigger_reason_codes": [
                "llm_output_format_error",
                "report_structure_missing",
                "user_or_developer_thumbs_down",
                "agent_overreach",
                "interface_degradation_blocked",
            ],
            "harness_quality": {
                "llm_output_format_error_count": 1,
                "negative_feedback_count": 1,
                "agent_overreach_count": 1,
            },
            "report_quality": {"missing_sections": ["strengths"]},
            "behavior": {"long_no_response": True},
            "harness_summary": {"failed_hard_rules": 0, "failed_traces": 0},
        },
        source_refs={},
    )

    candidates = generate_candidates_from_signal(signal)
    types = [item["candidate_type"] for item in candidates]
    frontend = next(item for item in candidates if item["candidate_type"] == "frontend_suggestion")

    assert "frontend_suggestion" in types
    assert "report_template" in types
    assert "prompt" in types
    assert "harness_rule_candidate" in types
    assert frontend["risk_level"] == "high"
    assert frontend["status"] == "waiting_approval"
    assert frontend["diff"]["auto_apply"] is False


def test_validation_blocks_declared_global_regressions() -> None:
    repository = _LoopRepository()
    repository.quality_signals.append(
        SimpleNamespace(
            metrics={
                "score": 80,
                "question_quality": {"repeat_rate": 0.1, "max_similarity": 0.2},
                "report_quality": {"vagueness_score": 0.1},
            },
            severity="info",
            signal_type="interview_completed",
            hard_trigger=False,
            threshold_trigger=False,
        )
    )
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="prompt",
        target_artifact_key="round_question_generation",
        risk_level="low",
        status="pending_validation",
        proposal={"action": "loosen_generation", "repeat_rate_delta": 0.2},
        diff={"allow_repeat": True},
        impact_scope={"scope": "question_generation"},
        root_cause={"category": "quality_regression"},
        approval_status="not_required",
    )

    validation = validate_candidate(repository, candidate.id)

    assert validation.status == "blocked"
    assert validation.repeat_rate_diff["status"] == "blocked"
    assert repository.candidates[candidate.id].status == "waiting_approval"


def test_medium_risk_flow_config_applies_only_after_manual_approval() -> None:
    repository = _LoopRepository()
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="flow_config",
        target_artifact_key="technical",
        risk_level="medium",
        status="waiting_approval",
        proposal={"action": "manual_review_difficulty_distribution", "max_total_questions": 6},
        diff={"max_total_questions": 6},
        impact_scope={"scope": "interview_flow"},
        root_cause={"category": "difficulty_anomaly"},
        approval_status="pending",
    )

    assert apply_candidate(repository, candidate.id, manual_approval=False) is None
    repository.candidates[candidate.id].approval_status = "approved"
    bundle = apply_candidate(repository, candidate.id, manual_approval=True)

    assert bundle is not None
    assert repository.candidates[candidate.id].status == "approved"
    assert repository.artifacts[-1]["artifact_type"] == "flow_config"


def test_apply_candidate_records_requested_regression_sample_count() -> None:
    repository = _LoopRepository()
    candidate = repository.create_candidate(
        run_id=1,
        candidate_type="prompt",
        target_artifact_key="round_question_generation",
        risk_level="low",
        status="pending_validation",
        proposal={"action": "increase_evidence"},
        diff={"prompt_hint": "ask for evidence"},
        impact_scope={"scope": "question_generation"},
        root_cause={"category": "low_score"},
        approval_status="not_required",
    )

    bundle = apply_candidate(
        repository,
        candidate.id,
        validation_sample_count=50,
        regression_scope={"sample_window": "latest_50"},
    )

    assert bundle is not None
    assert repository.validation_runs[0].sample_count == 50
    assert repository.validation_runs[0].details["regression_scope"]["sample_window"] == "latest_50"


def test_regression_samples_keep_required_metadata_without_raw_content() -> None:
    repository = _LoopRepository()
    repository.quality_signals.append(
        SimpleNamespace(
            id=9,
            version_bundle_id=3,
            job_family="backend",
            metrics={
                "score": 76,
                "question_type": "system_design",
                "question": "raw question",
                "answer": "raw answer",
            },
            severity="warning",
            signal_type="interview_completed",
            hard_trigger=False,
            threshold_trigger=True,
        )
    )

    samples = collect_regression_samples(repository, requested_sample_count=10)
    regression_sample = samples["regression_samples"][0]

    assert regression_sample["sample_id"] == "quality-signal-9"
    assert regression_sample["job_category"] == "backend"
    assert regression_sample["question_type"] == "system_design"
    assert regression_sample["quality_label"] == "warning"
    assert regression_sample["expected_rule_result"] == "soft_rule_warning_allowed"
    assert regression_sample["expected_score_range"] == {"min": 66, "max": 86}
    assert "question" not in samples["signals"][0]["metrics"]
    assert "answer" not in samples["signals"][0]["metrics"]


def test_flow_config_runtime_keeps_question_limits_consistent() -> None:
    repository = _LoopRepository()
    bundle = repository.create_version_bundle(
        bundle_key="flow-test",
        parent_bundle_id=1,
        scope_type="global",
        scope_key=None,
        status="active",
        risk_level="low",
        content_hash="hash",
        diff={},
        validation_summary={},
        rollback_point=None,
        created_by_run_id=1,
        activated=True,
    )
    repository.create_artifact(
        bundle_id=bundle.id,
        artifact_type="flow_config",
        artifact_key="technical",
        version=bundle.bundle_key,
        content={"min_total_questions": 30, "max_total_questions": 10},
        content_hash="hash",
        diff={},
        risk_level="low",
    )

    effective = resolve_round_spec(
        repository,
        version_bundle_id=bundle.id,
        base_spec=ROUND_SPECS["technical"],
    )

    assert effective.min_total_questions == 30
    assert effective.max_total_questions == 30


def test_global_anonymization_strips_raw_interview_content() -> None:
    signal = {
        "id": 1,
        "signal_type": "interview_completed",
        "severity": "warning",
        "job_family": "backend",
        "metrics": {
            "score": 55,
            "question": "raw question",
            "answer": "raw answer",
            "nested": {"resume": {"name": "Alice"}, "score": 1},
        },
    }

    sanitized = anonymize_signal_for_global_use(signal)

    assert "question" not in sanitized["metrics"]
    assert "answer" not in sanitized["metrics"]
    assert "resume" not in sanitized["metrics"]["nested"]
    assert sanitized["metrics"]["score"] == 55


def test_anonymized_aggregate_keeps_quality_metrics_without_raw_content() -> None:
    aggregate = aggregate_anonymized_signals(
        [
            {
                "id": 1,
                "signal_type": "interview_completed",
                "severity": "warning",
                "metrics": {
                    "score": 55,
                    "question": "raw question",
                    "answer": "raw answer",
                    "question_quality": {"repeat_rate": 0.5, "max_similarity": 0.9},
                    "report_quality": {"vagueness_score": 0.7},
                    "job_match": {"match_score": 0.1},
                },
            }
        ]
    )

    assert aggregate["aggregate_metrics"]["average_repeat_rate"] == 0.5
    assert aggregate["aggregate_metrics"]["report_vague_rate"] == 1.0
    assert "question" not in aggregate["signals"][0]["metrics"]
    assert "question_quality" in aggregate["signals"][0]["metrics"]


class _LoopRepository:
    def __init__(self) -> None:
        self.runs: list[Any] = []
        self.candidates: dict[int, Any] = {}
        self.validation_runs: list[Any] = []
        self.quality_signals: list[Any] = []
        self.bundles: dict[int, Any] = {
            1: SimpleNamespace(
                id=1,
                bundle_key="global-default-v3.2-bootstrap",
                status="active",
            )
        }
        self.active_bundle_id = 1
        self.artifacts: list[dict[str, Any]] = []
        self.audit_events: list[dict[str, Any]] = []

    def count_completed_quality_signals(self) -> int:
        return 1

    def create_evolution_run(self, **kwargs: Any) -> Any:
        key = (kwargs["trigger_type"], kwargs["trigger_reason"], kwargs.get("scope_key"))
        existing = next((run for run in self.runs if run.dedupe_key == key), None)
        if existing is not None:
            return existing
        run = SimpleNamespace(id=len(self.runs) + 1, dedupe_key=key, **kwargs)
        self.runs.append(run)
        return run

    def get_active_version_bundle(self, **_kwargs: Any) -> Any:
        return self.bundles[self.active_bundle_id]

    def get_or_create_active_default_version_bundle(self) -> Any:
        return self.bundles[self.active_bundle_id]

    def create_candidate(self, **kwargs: Any) -> Any:
        candidate_id = len(self.candidates) + 1
        candidate = SimpleNamespace(
            id=candidate_id,
            validation_summary=None,
            rollback_point=None,
            application_result=None,
            **kwargs,
        )
        self.candidates[candidate_id] = candidate
        return candidate

    def get_evolution_candidate(self, *, candidate_id: int, user_id: int | None = None) -> Any:
        del user_id
        return self.candidates.get(candidate_id)

    def update_candidate_status(self, candidate_id: int, **kwargs: Any) -> None:
        candidate = self.candidates[candidate_id]
        for key, value in kwargs.items():
            if value is not None:
                setattr(candidate, key, value)

    def create_validation_run(self, **kwargs: Any) -> Any:
        validation = SimpleNamespace(id=len(self.validation_runs) + 1, **kwargs)
        self.validation_runs.append(validation)
        return validation

    def create_version_bundle(self, **kwargs: Any) -> Any:
        bundle_id = len(self.bundles) + 1
        bundle = SimpleNamespace(id=bundle_id, **kwargs)
        self.bundles[bundle_id] = bundle
        return bundle

    def create_artifact(self, **kwargs: Any) -> int:
        self.artifacts.append(kwargs)
        return len(self.artifacts)

    def activate_version_bundle(self, bundle_id: int) -> None:
        self.active_bundle_id = bundle_id

    def record_evolution_audit_event(self, **kwargs: Any) -> Any:
        event = {"id": len(self.audit_events) + 1, **kwargs}
        self.audit_events.append(event)
        return SimpleNamespace(**event)

    def list_effective_artifacts(self, bundle_id: int) -> list[dict[str, Any]]:
        chain: list[int] = []
        current_id: int | None = bundle_id
        while current_id is not None and current_id not in chain:
            chain.append(current_id)
            current = self.bundles[current_id]
            current_id = getattr(current, "parent_bundle_id", None)
        by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for current in reversed(chain):
            for artifact in self.artifacts:
                if artifact["bundle_id"] == current:
                    by_key[(artifact["artifact_type"], artifact["artifact_key"])] = artifact
        return list(by_key.values())

    def list_quality_signals(self, *, limit: int = 100, **_kwargs: Any) -> list[Any]:
        return self.quality_signals[:limit]
