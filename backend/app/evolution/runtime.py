from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.agents.types import RoundSpec
from app.repositories.evolution import EvolutionRepository

PROMPT_KEYS_BY_ROUND = {
    "resume": "resume_interviewer.md",
    "technical": "technical_interviewer.md",
    "manager": "manager_interviewer.md",
    "hr": "hr_interviewer.md",
}


def resolve_round_spec(
    repository: Any,
    *,
    version_bundle_id: int | None,
    base_spec: RoundSpec,
) -> RoundSpec:
    artifacts = _effective_artifacts(repository, version_bundle_id)
    prompt = resolve_prompt(
        repository,
        version_bundle_id=version_bundle_id,
        prompt_key=PROMPT_KEYS_BY_ROUND.get(base_spec.round_type, base_spec.round_type),
        base_prompt=base_spec.system_prompt,
        aliases={"round_question_generation", base_spec.round_type},
    )
    limits = _round_limits(artifacts, base_spec.round_type)
    if not limits and prompt == base_spec.system_prompt:
        return base_spec
    min_main = _bounded_int(
        limits.get("min_main_questions"),
        default=base_spec.min_main_questions,
        minimum=1,
        maximum=base_spec.max_main_questions,
    )
    max_main = _bounded_int(
        limits.get("max_main_questions"),
        default=base_spec.max_main_questions,
        minimum=base_spec.min_main_questions,
        maximum=60,
    )
    min_total = _bounded_int(
        limits.get("min_total_questions"),
        default=base_spec.min_total_questions,
        minimum=1,
        maximum=base_spec.max_total_questions,
    )
    max_total = _bounded_int(
        limits.get("max_total_questions"),
        default=base_spec.max_total_questions,
        minimum=base_spec.min_total_questions,
        maximum=80,
    )
    return replace(
        base_spec,
        system_prompt=prompt,
        min_main_questions=min_main,
        max_main_questions=max(min_main, max_main),
        min_total_questions=min_total,
        max_total_questions=max(min_total, max_total),
    )


def resolve_prompt(
    repository: Any,
    *,
    version_bundle_id: int | None,
    prompt_key: str,
    base_prompt: str,
    aliases: set[str] | None = None,
) -> str:
    alias_set = {prompt_key, *(aliases or set())}
    additions: list[str] = []
    for artifact in _effective_artifacts(repository, version_bundle_id):
        artifact_type = _get(artifact, "artifact_type")
        artifact_key = _get(artifact, "artifact_key")
        if artifact_type not in {"prompt", "report_template"}:
            continue
        if artifact_key not in alias_set and artifact_key != "all":
            continue
        content = _dict(_get(artifact, "content"))
        diff = _dict(_get(artifact, "diff"))
        full_prompt = _text(content.get("prompt_text"))
        if full_prompt:
            return full_prompt
        appendix = (
            _text(content.get("prompt_appendix"))
            or _text(content.get("prompt_hint"))
            or _text(diff.get("prompt_hint"))
            or _text(diff.get("add_guardrail"))
        )
        if appendix:
            additions.append(appendix)
    if not additions:
        return base_prompt
    return f"{base_prompt}\n\n# 自动进化补充约束\n" + "\n".join(
        f"- {item}" for item in additions
    )


def resolve_report_template_notes(
    repository: Any,
    *,
    version_bundle_id: int | None,
) -> dict[str, Any]:
    notes: dict[str, Any] = {}
    for artifact in _effective_artifacts(repository, version_bundle_id):
        if _get(artifact, "artifact_type") != "report_template":
            continue
        content = _dict(_get(artifact, "content"))
        diff = _dict(_get(artifact, "diff"))
        for key in ("reference_note_hint", "quality_guardrail", "report_appendix"):
            value = content.get(key) or diff.get(key) or diff.get("add_guardrail")
            if value:
                notes[key] = value
    return notes


def _round_limits(artifacts: list[Any], round_type: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for artifact in artifacts:
        if _get(artifact, "artifact_type") != "flow_config":
            continue
        content = _dict(_get(artifact, "content"))
        diff = _dict(_get(artifact, "diff"))
        candidate = _dict(content.get("round_limits")).get(round_type)
        if isinstance(candidate, dict):
            merged.update(candidate)
        if _get(artifact, "artifact_key") in {round_type, "interview_rounds", "round_limits"}:
            merged.update(
                {key: value for key, value in content.items() if key.endswith("questions")}
            )
            merged.update({key: value for key, value in diff.items() if key.endswith("questions")})
    return merged


def _effective_artifacts(repository: Any, version_bundle_id: int | None) -> list[Any]:
    if version_bundle_id is None:
        return []
    method = getattr(repository, "list_effective_artifacts", None)
    if callable(method):
        return list(method(version_bundle_id))
    evolution_repository = _evolution_repository(repository)
    if evolution_repository is None:
        return []
    return evolution_repository.list_effective_artifacts(version_bundle_id)


def _evolution_repository(repository: Any) -> EvolutionRepository | None:
    if isinstance(repository, EvolutionRepository):
        return repository
    connection = getattr(repository, "connection", None)
    if connection is None:
        return None
    return EvolutionRepository(connection)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _get(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)
