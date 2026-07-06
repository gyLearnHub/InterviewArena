from __future__ import annotations

from typing import Any

from app.evolution.audit import record_evolution_audit_event


def rollback_candidate(repository: Any, candidate_id: int, *, reason: str) -> bool:
    candidate = repository.get_evolution_candidate(candidate_id=candidate_id, user_id=None)
    if candidate is None:
        raise ValueError("candidate not found")
    rollback_point = candidate.rollback_point or {}
    previous_bundle_id = rollback_point.get("previous_bundle_id")
    if previous_bundle_id is None:
        repository.update_candidate_status(
            candidate.id,
            status="rolled_back",
            application_result={"rolled_back": False, "reason": "no rollback point"},
            manual_note=reason,
        )
        record_evolution_audit_event(
            repository,
            event_type="candidate_rollback_failed",
            run_id=getattr(candidate, "run_id", None),
            candidate_id=candidate.id,
            metadata={"reason": reason, "failure": "no rollback point"},
        )
        return False
    repository.activate_version_bundle(int(previous_bundle_id))
    repository.update_candidate_status(
        candidate.id,
        status="rolled_back",
        application_result={
            "rolled_back": True,
            "reason": reason,
            "restored_bundle_id": previous_bundle_id,
        },
        manual_note=reason,
    )
    record_evolution_audit_event(
        repository,
        event_type="candidate_rolled_back",
        run_id=getattr(candidate, "run_id", None),
        candidate_id=candidate.id,
        version_bundle_id=int(previous_bundle_id),
        metadata={"reason": reason, "rollback_point": rollback_point},
    )
    return True
