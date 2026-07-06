from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.evolution.audit import record_evolution_audit_event
from app.evolution.risk_classifier import can_apply_after_manual_approval, can_auto_apply_candidate
from app.evolution.validation import validate_candidate


def apply_candidate(
    repository: Any,
    candidate_id: int,
    *,
    auto_validate: bool = True,
    post_validate: bool = True,
    manual_approval: bool = False,
    scope_type: str = "global",
    scope_key: str | None = None,
    validation_sample_count: int = 0,
    regression_scope: dict[str, Any] | None = None,
) -> Any:
    candidate = repository.get_evolution_candidate(candidate_id=candidate_id, user_id=None)
    if candidate is None:
        raise ValueError("candidate not found")
    if not _can_apply(candidate, manual_approval=manual_approval):
        repository.update_candidate_status(
            candidate.id,
            status="waiting_approval",
            application_result={
                "applied": False,
                "reason": "candidate is not applicable under current approval gate",
                "manual_approval": manual_approval,
            },
        )
        record_evolution_audit_event(
            repository,
            event_type="candidate_apply_rejected_by_gate",
            run_id=getattr(candidate, "run_id", None),
            candidate_id=candidate.id,
            metadata={"manual_approval": manual_approval},
        )
        return None
    if auto_validate:
        validation = validate_candidate(
            repository,
            candidate.id,
            manual_approval=manual_approval,
            sample_count=validation_sample_count,
            regression_scope=regression_scope,
        )
        if getattr(validation, "status", None) != "passed":
            record_evolution_audit_event(
                repository,
                event_type="candidate_apply_validation_blocked",
                run_id=getattr(candidate, "run_id", None),
                candidate_id=candidate.id,
                validation_run_id=getattr(validation, "id", None),
                metadata={"validation_status": getattr(validation, "status", None)},
            )
            return None
    refreshed = repository.get_evolution_candidate(candidate_id=candidate.id, user_id=None)
    if refreshed is not None:
        candidate = refreshed
    if candidate.validation_summary and not candidate.validation_summary.get("can_apply", False):
        repository.update_candidate_status(
            candidate.id,
            status="validation_failed",
            application_result={"applied": False, "reason": "validation gate blocked"},
        )
        record_evolution_audit_event(
            repository,
            event_type="candidate_apply_validation_summary_blocked",
            run_id=getattr(candidate, "run_id", None),
            candidate_id=candidate.id,
            metadata={"validation_summary": candidate.validation_summary},
        )
        return None

    active_bundle = repository.get_active_version_bundle(scope_type=scope_type, scope_key=scope_key)
    if active_bundle is None:
        active_bundle = repository.get_or_create_active_default_version_bundle()
    rollback_point = {
        "previous_bundle_id": active_bundle.id,
        "previous_bundle_key": active_bundle.bundle_key,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "created_at": datetime.utcnow().isoformat(),
    }
    content = _artifact_content(candidate)
    content_hash = _hash(content)
    bundle_key = (
        f"evo-{scope_type}-{scope_key or 'default'}-"
        f"{candidate.candidate_type}-{candidate.id}-{content_hash[:12]}"
    )
    bundle = repository.create_version_bundle(
        bundle_key=bundle_key,
        parent_bundle_id=active_bundle.id,
        scope_type=scope_type,
        scope_key=scope_key,
        status="candidate",
        risk_level=candidate.risk_level,
        content_hash=content_hash,
        diff=candidate.diff,
        validation_summary=candidate.validation_summary or {"status": "passed"},
        rollback_point=rollback_point,
        created_by_run_id=candidate.run_id,
        activated=False,
    )
    repository.create_artifact(
        bundle_id=bundle.id,
        artifact_type=candidate.candidate_type,
        artifact_key=candidate.target_artifact_key or candidate.candidate_type,
        version=bundle.bundle_key,
        content=content,
        content_hash=content_hash,
        diff=candidate.diff,
        risk_level=candidate.risk_level,
    )
    repository.activate_version_bundle(bundle.id)
    record_evolution_audit_event(
        repository,
        event_type="candidate_bundle_applied",
        run_id=candidate.run_id,
        candidate_id=candidate.id,
        version_bundle_id=bundle.id,
        metadata={
            "scope_type": scope_type,
            "scope_key": scope_key,
            "manual_approval": manual_approval,
            "rollback_point": rollback_point,
        },
    )
    if post_validate:
        post_validation = validate_candidate(
            repository,
            candidate.id,
            validation_type="post_apply_static_gate",
            manual_approval=manual_approval,
            sample_count=validation_sample_count,
            regression_scope=regression_scope,
        )
        if getattr(post_validation, "status", None) != "passed":
            from app.evolution.rollback import rollback_candidate

            repository.update_candidate_status(
                candidate.id,
                status="validation_failed",
                rollback_point=rollback_point,
                application_result={
                    "applied": True,
                    "bundle_id": bundle.id,
                    "bundle_key": bundle.bundle_key,
                    "post_validation": "failed",
                    "scope_type": scope_type,
                    "scope_key": scope_key,
                    "manual_approval": manual_approval,
                },
            )
            rollback_candidate(repository, candidate.id, reason="post validation failed")
            record_evolution_audit_event(
                repository,
                event_type="candidate_post_validation_rollback",
                run_id=candidate.run_id,
                candidate_id=candidate.id,
                validation_run_id=getattr(post_validation, "id", None),
                version_bundle_id=bundle.id,
                metadata={"post_validation": "failed"},
            )
            return None
    repository.update_candidate_status(
        candidate.id,
        status="auto_applied" if not manual_approval else "approved",
        rollback_point=rollback_point,
        application_result={
            "applied": True,
            "bundle_id": bundle.id,
            "bundle_key": bundle.bundle_key,
            "post_validation": "passed",
            "scope_type": scope_type,
            "scope_key": scope_key,
            "manual_approval": manual_approval,
        },
    )
    record_evolution_audit_event(
        repository,
        event_type="candidate_apply_completed",
        run_id=candidate.run_id,
        candidate_id=candidate.id,
        version_bundle_id=bundle.id,
        metadata={
            "post_validation": "passed",
            "manual_approval": manual_approval,
            "scope_type": scope_type,
            "scope_key": scope_key,
        },
    )
    return bundle


def _can_apply(candidate: Any, *, manual_approval: bool) -> bool:
    if can_auto_apply_candidate(candidate.candidate_type, candidate.risk_level):
        return True
    return (
        manual_approval
        and candidate.approval_status == "approved"
        and can_apply_after_manual_approval(candidate.candidate_type, candidate.risk_level)
    )


def _artifact_content(candidate: Any) -> dict[str, Any]:
    proposal = dict(getattr(candidate, "proposal", {}) or {})
    diff = dict(getattr(candidate, "diff", {}) or {})
    content: dict[str, Any] = {
        "candidate_id": candidate.id,
        "candidate_type": candidate.candidate_type,
        "proposal": proposal,
        "diff": diff,
    }
    if candidate.candidate_type == "prompt":
        content["prompt_appendix"] = (
            proposal.get("prompt_appendix")
            or proposal.get("prompt_hint")
            or diff.get("prompt_appendix")
            or diff.get("prompt_hint")
        )
    elif candidate.candidate_type == "report_template":
        content["quality_guardrail"] = diff.get("add_guardrail") or proposal.get("reason")
        content["report_appendix"] = proposal.get("report_appendix") or diff.get("report_appendix")
    elif candidate.candidate_type == "flow_config":
        for key in (
            "round_limits",
            "min_main_questions",
            "max_main_questions",
            "min_total_questions",
            "max_total_questions",
        ):
            if key in proposal:
                content[key] = proposal[key]
            if key in diff:
                content[key] = diff[key]
    elif candidate.candidate_type == "business_config":
        content["business_config"] = {
            **dict(proposal.get("business_config") or {}),
            **dict(diff.get("business_config") or {}),
        }
    return content


def _hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
