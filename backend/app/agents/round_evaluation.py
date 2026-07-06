from __future__ import annotations

from app.agents.types import EvaluationLLMClient, JSONDict
from app.prompts.loader import load_prompt
from app.schemas.evaluation import RoundEvaluationOutput


class RoundEvaluationAgent:
    prompt_file_template = "round_evaluation_{round_type}.md"

    def __init__(self, llm_client: EvaluationLLMClient) -> None:
        self.llm_client = llm_client

    @classmethod
    def prompt_file_for(cls, round_type: str) -> str:
        return cls.prompt_file_template.format(round_type=round_type)

    def evaluate(
        self,
        round_type: str,
        payload: JSONDict,
        *,
        system_prompt: str | None = None,
    ) -> RoundEvaluationOutput:
        result = self.llm_client.generate_json(
            system_prompt or load_prompt(self.prompt_file_for(round_type)),
            payload,
        )
        return RoundEvaluationOutput.model_validate(result)
