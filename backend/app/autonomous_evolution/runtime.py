from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from app.agents.registry import ROUND_SPECS
from app.agents.types import RoundSpec
from app.autonomous_evolution.catalog import bootstrap_artifacts
from app.autonomous_evolution.job_family import JobFamilyClassifier
from app.autonomous_evolution.repository import AutonomousEvolutionRepository

LOGGER = logging.getLogger(__name__)


def prepare_interview_evolution_context(
    *,
    connection: Any,
    llm_client: Any,
    user_id: int,
    interview_id: int,
    target_position: str,
    job_description: str | None,
) -> tuple[str, int] | None:
    try:
        repository = AutonomousEvolutionRepository(connection)
        decision = JobFamilyClassifier(repository, llm_client).classify(
            target_position,
            job_description,
            user_id=user_id,
        )
        bundle = repository.ensure_bootstrap_bundle(
            decision.key,
            bootstrap_artifacts(),
            user_id=user_id,
        )
        repository.assign_interview_context(
            interview_id,
            user_id=user_id,
            job_family_key=decision.key,
            bundle_id=bundle.id,
        )
        limits: dict[str, tuple[int, int]] = {}
        for round_type in ROUND_SPECS:
            spec = resolve_round_spec(connection, bundle.id, round_type)
            limits[round_type] = (spec.max_main_questions, spec.max_total_questions)
        repository.apply_pending_round_limits(
            interview_id,
            user_id=user_id,
            limits=limits,
        )
        repository.record_event(
            event_type="interview_bound_to_bundle",
            bundle_id=bundle.id,
            payload={
                "interview_id": interview_id,
                "job_family_key": decision.key,
                "classification_confidence": decision.confidence,
                "matched_existing": decision.matched_existing,
            },
        )
        return decision.key, bundle.id
    except Exception:
        LOGGER.exception(
            "failed to bind interview %s to an autonomous evolution bundle",
            interview_id,
        )
        return None


def prepare_interview_evolution_context_task(
    *,
    user_id: int,
    interview_id: int,
    target_position: str,
    job_description: str | None,
) -> None:
    try:
        from app.core.config import get_settings
        from app.db.mysql import mysql_connection
        from app.services.llm import get_llm_client

        if not get_settings().evolution_enabled:
            return
        with mysql_connection() as connection:
            prepare_interview_evolution_context(
                connection=connection,
                llm_client=get_llm_client(),
                user_id=user_id,
                interview_id=interview_id,
                target_position=target_position,
                job_description=job_description,
            )
    except Exception:
        LOGGER.exception(
            "failed to run background autonomous evolution binding for interview %s",
            interview_id,
        )


def resolve_round_spec(
    connection: Any,
    bundle_id: int | None,
    round_type: str,
) -> RoundSpec:
    base = ROUND_SPECS[round_type]
    if bundle_id is None:
        return base
    try:
        repository = AutonomousEvolutionRepository(connection)
        prompt = repository.get_artifact(bundle_id, f"interviewer.{round_type}")
        flow = repository.get_artifact(bundle_id, "flow.rounds")
        prompt_text = str((prompt.content if prompt else {}).get("text") or base.system_prompt)
        flow_config = (flow.content if flow else {}).get("config") or {}
        round_config = flow_config.get(round_type) or {}
        return replace(
            base,
            system_prompt=prompt_text,
            min_main_questions=_bounded_int(
                round_config.get("min_main_questions"),
                base.min_main_questions,
                1,
                40,
            ),
            max_main_questions=_bounded_int(
                round_config.get("max_main_questions"),
                base.max_main_questions,
                1,
                40,
            ),
            min_total_questions=_bounded_int(
                round_config.get("min_total_questions"),
                base.min_total_questions,
                1,
                40,
            ),
            max_total_questions=_bounded_int(
                round_config.get("max_total_questions"),
                base.max_total_questions,
                1,
                40,
            ),
            dimensions=_string_list(round_config.get("dimensions")) or base.dimensions,
            core_topics=_topic_map(round_config.get("core_topics")) or base.core_topics,
        )
    except Exception:
        LOGGER.exception("failed to resolve evolved round spec for %s", round_type)
        return base


def resolve_prompt(
    connection: Any,
    bundle_id: int | None,
    artifact_key: str,
    fallback: str,
) -> str:
    if bundle_id is None:
        return fallback
    try:
        artifact = AutonomousEvolutionRepository(connection).get_artifact(
            bundle_id,
            artifact_key,
        )
        value = (artifact.content if artifact else {}).get("text")
        return str(value).strip() if isinstance(value, str) and value.strip() else fallback
    except Exception:
        LOGGER.exception("failed to resolve evolved prompt %s", artifact_key)
        return fallback


def resolve_artifact_version(
    connection: Any,
    bundle_id: int | None,
    artifact_key: str,
    fallback_version: str,
) -> str:
    if connection is None or bundle_id is None:
        return fallback_version
    try:
        artifact = AutonomousEvolutionRepository(connection).get_artifact(
            bundle_id,
            artifact_key,
        )
        if artifact is None:
            return fallback_version
        return f"{fallback_version}|b{bundle_id}|{artifact.content_hash[:12]}"[:64]
    except Exception:
        LOGGER.exception("failed to resolve evolved artifact version %s", artifact_key)
        return fallback_version


def resolve_harness_policy(connection: Any, bundle_id: int | None) -> dict[str, Any]:
    if bundle_id is None:
        return {}
    try:
        artifact = AutonomousEvolutionRepository(connection).get_artifact(
            bundle_id,
            "harness.policy",
        )
        config = (artifact.content if artifact else {}).get("config")
        return dict(config) if isinstance(config, dict) else {}
    except Exception:
        LOGGER.exception("failed to resolve evolved Harness policy")
        return {}


def resolve_interview_harness_policy(
    connection: Any,
    interview_id: int,
) -> dict[str, Any]:
    try:
        repository = AutonomousEvolutionRepository(connection)
        bundle = repository.get_interview_bundle(interview_id)
        return resolve_harness_policy(connection, bundle.id if bundle is not None else None)
    except Exception:
        LOGGER.exception(
            "failed to resolve evolved Harness policy for interview %s",
            interview_id,
        )
        return {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, result))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _topic_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _string_list(items)
        for key, items in value.items()
        if str(key).strip() and _string_list(items)
    }
