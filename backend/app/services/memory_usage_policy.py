from app.schemas.memory import MemoryRetrievalRequest

AGENT_MEMORY_TYPES = {
    "resume": {
        "resume_key_fact",
        "project_highlight",
        "experience_authenticity",
        "project_follow_up",
        "unresolved_question",
    },
    "technical": {
        "technical_weakness",
        "past_wrong_answer",
        "knowledge_mastery",
        "technical_trend",
        "asked_question",
    },
    "manager": {
        "business_understanding",
        "collaboration",
        "execution",
        "pressure_response",
        "problem_solving",
        "retrospective",
    },
    "hr": {
        "motivation",
        "career_plan",
        "position_preference",
        "stability",
        "expression_style",
        "answer_consistency",
    },
}


class MemoryUsagePolicy:
    def allowed_collections(self, request: MemoryRetrievalRequest) -> list[str]:
        collections = request.collections or [
            "candidate_memories",
            "interviewer_memories",
            "agent_memories",
        ]
        if not request.memory_enabled:
            return []
        return list(collections)

    def allowed_memory_types(self, request: MemoryRetrievalRequest) -> list[str]:
        if request.memory_types:
            return request.memory_types
        if request.agent_type in AGENT_MEMORY_TYPES:
            return sorted(AGENT_MEMORY_TYPES[request.agent_type])
        return []

    def top_k(self, request: MemoryRetrievalRequest) -> int:
        if request.top_k is not None:
            return max(1, min(request.top_k, 10))
        defaults = {
            "new_question": 4,
            "follow_up": 3,
            "feedback": 6,
            "interviewer": 3,
            "agent": 3,
        }
        return defaults.get(request.usage_scene, 4)
