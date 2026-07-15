from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.registry import ROUND_ORDER, ROUND_SPECS
from app.prompts.loader import load_prompt


@dataclass(frozen=True)
class ArtifactSeed:
    key: str
    artifact_type: str
    content: dict[str, Any]


def bootstrap_artifacts() -> list[ArtifactSeed]:
    artifacts = [
        ArtifactSeed(
            key=f"interviewer.{round_type}",
            artifact_type="prompt",
            content={"text": ROUND_SPECS[round_type].system_prompt},
        )
        for round_type in ROUND_ORDER
    ]
    artifacts.extend(
        [
            ArtifactSeed(
                key="evaluation.question",
                artifact_type="prompt",
                content={"text": load_prompt("question_evaluation.md")},
            ),
            *[
                ArtifactSeed(
                    key=f"evaluation.round.{round_type}",
                    artifact_type="prompt",
                    content={"text": load_prompt(f"round_evaluation_{round_type}.md")},
                )
                for round_type in ROUND_ORDER
            ],
            ArtifactSeed(
                key="evaluation.final",
                artifact_type="prompt",
                content={"text": load_prompt("final_evaluation.md")},
            ),
            ArtifactSeed(
                key="flow.rounds",
                artifact_type="flow_config",
                content={
                    "config": {
                        round_type: {
                            "min_main_questions": spec.min_main_questions,
                            "max_main_questions": spec.max_main_questions,
                            "min_total_questions": spec.min_total_questions,
                            "max_total_questions": spec.max_total_questions,
                            "dimensions": spec.dimensions,
                            "core_topics": spec.core_topics,
                        }
                        for round_type, spec in ROUND_SPECS.items()
                    }
                },
            ),
            ArtifactSeed(
                key="harness.policy",
                artifact_type="harness_policy",
                content={
                    "config": {
                        "max_retries": 2,
                        "require_json_object": True,
                        "forbid_scoring_memory": True,
                        "checkpoint_required": True,
                        "privacy_gate": True,
                    }
                },
            ),
        ]
    )
    return artifacts


def artifact_manifest() -> list[dict[str, str]]:
    return [
        {"key": item.key, "artifact_type": item.artifact_type}
        for item in bootstrap_artifacts()
    ]
