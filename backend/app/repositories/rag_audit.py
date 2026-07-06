import json
from typing import Any


class RagAuditRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create(
        self,
        *,
        request_id: str,
        user_id: int | None,
        interview_id: int | None,
        round_id: int | None,
        agent_type: str | None,
        usage_scene: str,
        original_intent: str | None,
        rewritten_query: str | None,
        candidate_memory_ids: list[int],
        injected_memory_ids: list[int],
        scores: dict[str, Any],
        timings: dict[str, Any],
        fallback_reason: str | None,
        embedding_version: str | None,
        reranker_version: str | None,
        prompt_version: str | None,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rag_audit_logs (
                    request_id, user_id, interview_id, round_id, agent_type, usage_scene,
                    original_intent, rewritten_query, candidate_memory_ids, injected_memory_ids,
                    scores, timings, hit_count, fallback_reason, embedding_version,
                    reranker_version, prompt_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    request_id,
                    user_id,
                    interview_id,
                    round_id,
                    agent_type,
                    usage_scene,
                    original_intent,
                    rewritten_query,
                    json.dumps(candidate_memory_ids),
                    json.dumps(injected_memory_ids),
                    json.dumps(scores, ensure_ascii=False),
                    json.dumps(timings, ensure_ascii=False),
                    len(injected_memory_ids),
                    fallback_reason,
                    embedding_version,
                    reranker_version,
                    prompt_version,
                ),
            )
