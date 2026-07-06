from __future__ import annotations

from typing import Any

from app.evolution.risk_classifier import classify_risk

FORBIDDEN_PATCH_KEYWORDS = {
    "database",
    "migration",
    "auth",
    "permission",
    "api contract",
    "delete data",
}


def build_backend_patch_candidate(
    *,
    run_id: int,
    target_artifact_key: str,
    patch_draft: str,
    root_cause: dict[str, Any],
    impact_scope: dict[str, Any] | None = None,
    test_result: dict[str, Any] | None = None,
    replay_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = patch_draft.casefold()
    forbidden = [item for item in FORBIDDEN_PATCH_KEYWORDS if item in normalized]
    tests = dict(test_result or {})
    replay = dict(replay_result or {})
    has_required_evidence = tests.get("status") == "passed" and replay.get("status") == "passed"
    proposal = {
        "action": "backend_patch_draft_only",
        "patch_draft": patch_draft,
        "forbidden_hits": forbidden,
        "scope_guard": {
            "target_artifact_key": target_artifact_key,
            "forbidden_hits": forbidden,
            "within_backend_small_fix": not forbidden,
        },
        "test_result": tests,
        "replay_result": replay,
        "evidence_package": {
            "test_result": tests,
            "replay_result": replay,
            "root_cause": root_cause,
            "impact_scope": impact_scope or {"scope": "backend_draft_only"},
        },
        "will_modify_files": False,
    }
    risk_level = (
        "high"
        if forbidden
        else "low"
        if has_required_evidence
        else classify_risk(
            candidate_type="backend_patch",
            proposal=proposal,
            diff={"patch_draft": patch_draft},
        )
    )
    return {
        "run_id": run_id,
        "candidate_type": "backend_patch",
        "target_artifact_key": target_artifact_key,
        "risk_level": risk_level,
        "status": "waiting_approval",
        "proposal": proposal,
        "diff": {"patch_draft": patch_draft},
        "impact_scope": impact_scope or {"scope": "backend_draft_only"},
        "root_cause": root_cause,
        "approval_status": "pending",
    }
