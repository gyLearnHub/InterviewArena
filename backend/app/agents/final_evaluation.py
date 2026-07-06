from __future__ import annotations

from app.agents.types import EvaluationLLMClient, JSONDict
from app.prompts.loader import load_prompt
from app.schemas.evaluation import FinalEvaluationOutput


class FinalEvaluationAgent:
    prompt_file = "final_evaluation.md"

    def __init__(self, llm_client: EvaluationLLMClient) -> None:
        self.llm_client = llm_client

    def evaluate(
        self,
        payload: JSONDict,
        *,
        system_prompt: str | None = None,
    ) -> FinalEvaluationOutput:
        result = self.llm_client.generate_json(
            system_prompt or load_prompt(self.prompt_file),
            payload,
        )
        return FinalEvaluationOutput.model_validate(result)
