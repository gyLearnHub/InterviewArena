from typing import Any

from app.core.errors import safe_error_code
from app.schemas.memory import MemoryRetrievalRequest

PROMPT_VERSION = "memory-query-rewriter-v1"


class MemoryQueryRewriter:
    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def rewrite(self, request: MemoryRetrievalRequest) -> tuple[str, str | None]:
        if request.query_text and request.query_text.strip():
            return request.query_text.strip(), None
        if self.llm_client is not None:
            try:
                payload = self.llm_client.generate_json(
                    "你是 Memory Query Rewriter。只返回 JSON，字段为 query_text。",
                    request.model_dump(),
                )
                query_text = payload.get("query_text")
                if isinstance(query_text, str) and query_text.strip():
                    return query_text.strip(), None
            except Exception as exc:
                return self._template_query(request), safe_error_code(exc)
        return self._template_query(request), "template_rewriter"

    def _template_query(self, request: MemoryRetrievalRequest) -> str:
        scene_hint = {
            "new_question": "历史薄弱点 已问题目 岗位目标",
            "follow_up": "当前题目 当前回答 相关项目经历 未解决问题",
            "feedback": "本场表现 历史薄弱点 改进趋势",
            "interviewer": "评分标准 提问风格 追问策略",
            "agent": "提问效果 评分校准 协作异常",
        }.get(request.usage_scene, "")
        parts = [request.intent, scene_hint, request.agent_type or ""]
        return " ".join(part for part in parts if part)
