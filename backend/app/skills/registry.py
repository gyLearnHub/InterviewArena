from __future__ import annotations

from app.skills.catalog import SKILL_DEFINITIONS
from app.skills.types import SkillDefinition, SkillStage


class SkillRegistry:
    def __init__(self, definitions: tuple[SkillDefinition, ...]) -> None:
        self._definitions = {definition.name: definition for definition in definitions}

    def get(self, name: str) -> SkillDefinition | None:
        return self._definitions.get(name)

    def list_available(
        self, round_type: str, stage: SkillStage
    ) -> list[SkillDefinition]:
        return [
            definition
            for definition in self._definitions.values()
            if round_type in definition.available_rounds and stage in definition.stages
        ]

    def all(self) -> list[SkillDefinition]:
        return list(self._definitions.values())


DEFAULT_SKILL_REGISTRY = SkillRegistry(SKILL_DEFINITIONS)
