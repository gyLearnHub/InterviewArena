from __future__ import annotations

from typing import Any


def build_run_audit_metadata(
    *,
    source: str,
    user_id: int | None = None,
    validation_result: dict[str, Any] | None = None,
    application_result: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(extra or {})
    metadata.update(
        {
            "source": source,
            "triggered_by_user_id": user_id,
            "validation_result": validation_result or {},
            "application_result": application_result or {},
        }
    )
    return metadata


def build_data_scope(
    *,
    scope_type: str,
    sample_count: int,
    anonymized: bool,
    source_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scope_type": scope_type,
        "sample_count": sample_count,
        "anonymized": anonymized,
        "source_refs": dict(source_refs or {}),
    }


def record_evolution_audit_event(
    repository: Any,
    *,
    event_type: str,
    run_id: int | None = None,
    candidate_id: int | None = None,
    validation_run_id: int | None = None,
    version_bundle_id: int | None = None,
    actor_user_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    record_method = getattr(repository, "record_evolution_audit_event", None)
    if callable(record_method):
        record_method(
            event_type=event_type,
            run_id=run_id,
            candidate_id=candidate_id,
            validation_run_id=validation_run_id,
            version_bundle_id=version_bundle_id,
            actor_user_id=actor_user_id,
            metadata=metadata or {},
        )
        return
    if run_id is not None:
        merge_method = getattr(repository, "merge_evolution_run_audit_metadata", None)
        if callable(merge_method):
            merge_method(
                run_id,
                {
                    f"audit_event_{event_type}": {
                        "event_type": event_type,
                        "candidate_id": candidate_id,
                        "validation_run_id": validation_run_id,
                        "version_bundle_id": version_bundle_id,
                        "actor_user_id": actor_user_id,
                        "metadata": metadata or {},
                    }
                },
            )
