from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class RoundSpec:
    round_type: str
    agent_type: str
    system_prompt: str
    min_main_questions: int
    max_main_questions: int
    min_total_questions: int
    max_total_questions: int
    dimensions: list[str]
    core_topics: dict[str, list[str]]


@dataclass(frozen=True)
class AgentQuestion:
    question_type: str
    question: str


class RoundLLMClient(Protocol):
    def generate_question(
        self,
        resume: JSONDict,
        target_position: str,
        qa_history: list[JSONDict],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> JSONDict:
        ...


class EvaluationLLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_payload: JSONDict) -> JSONDict:
        ...
