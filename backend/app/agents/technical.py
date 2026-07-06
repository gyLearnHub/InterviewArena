from app.agents.base import BaseRoundAgent
from app.agents.types import RoundLLMClient


class TechnicalInterviewAgent(BaseRoundAgent):
    def __init__(self, llm_client: RoundLLMClient) -> None:
        from app.agents.registry import ROUND_SPECS

        super().__init__(ROUND_SPECS["technical"], llm_client)

