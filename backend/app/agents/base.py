from __future__ import annotations

from typing import Any

from app.agents.types import AgentQuestion, JSONDict, RoundLLMClient, RoundSpec
from app.repositories.interviews import InterviewRoundRecord, QARecord


class BaseRoundAgent:
    def __init__(self, spec: RoundSpec, llm_client: RoundLLMClient) -> None:
        self.spec = spec
        self.llm_client = llm_client

    def generate_question(
        self,
        resume: JSONDict,
        target_position: str,
        qa_history: list[JSONDict],
        previous_answer: str | None,
        effective_memories: list[JSONDict] | None = None,
        question_kind: str | None = None,
    ) -> AgentQuestion:
        payload = self.llm_client.generate_question(
            resume={
                **resume,
                "_interview_round": self.spec.round_type,
                "_evaluation_dimensions": self.spec.dimensions,
                "_effective_memories": effective_memories or [],
                "_question_strategy": self._question_strategy(qa_history, question_kind),
            },
            target_position=target_position,
            qa_history=qa_history,
            previous_answer=previous_answer,
            system_prompt=self.spec.system_prompt,
        )
        question_type = payload.get("question_type")
        question = payload.get("question")
        if not isinstance(question_type, str) or not question_type.strip():
            question_type = f"{self.spec.round_type}_question"
        if not isinstance(question, str) or not question.strip():
            question = "请结合你的经历继续说明一个最能体现岗位匹配度的案例。"
        if self._should_replace_initial_technical_project_question(
            question_type,
            question,
            qa_history,
        ):
            question_type = self._fallback_question_type(qa_history)
            question = self._fallback_question(qa_history, question_kind or "main")
        if _is_duplicate_question(question, qa_history):
            question_type = self._fallback_question_type(qa_history)
            question = self._fallback_question(qa_history, question_kind or "main")
        return AgentQuestion(question_type=question_type.strip(), question=question.strip())

    def fallback_question(self, qa_history: list[JSONDict], question_kind: str) -> AgentQuestion:
        return AgentQuestion(
            question_type=self._fallback_question_type(qa_history),
            question=self._fallback_question(qa_history, question_kind),
        )

    def should_finish(
        self,
        round_record: InterviewRoundRecord,
        qa_history: list[QARecord],
        latest_question_score: Any | None = None,
    ) -> bool:
        counts = count_questions(qa_history)
        if counts["total"] >= round_record.max_total_questions:
            return True
        if counts["total"] < round_record.min_total_questions:
            return False
        if counts["main"] < round_record.min_main_questions:
            return False
        if not self._has_core_topic_coverage(qa_history):
            return False
        if _score_requires_more_signal(latest_question_score):
            return False
        return True

    def _question_strategy(
        self,
        qa_history: list[JSONDict],
        question_kind: str | None,
    ) -> JSONDict:
        active_history = _active_history_items(qa_history)
        covered_topics = _covered_topics_from_items(self.spec.core_topics, active_history)
        recent_question_types = [
            str(item.get("question_type") or "")
            for item in active_history[-4:]
            if item.get("question_type")
        ]
        return {
            "question_kind": question_kind or "main",
            "min_total_questions": self.spec.min_total_questions,
            "max_total_questions": self.spec.max_total_questions,
            "current_total_questions": len(active_history),
            "current_main_questions": sum(
                1 for item in active_history if item.get("question_kind") == "main"
            ),
            "current_follow_up_questions": sum(
                1 for item in active_history if item.get("question_kind") == "follow_up"
            ),
            "core_topics": list(self.spec.core_topics),
            "covered_core_topics": covered_topics,
            "uncovered_core_topics": [
                topic for topic in self.spec.core_topics if topic not in covered_topics
            ],
            "recent_question_types": recent_question_types,
            "rule_summary": (
                "主问题和追问交叉推进；单个主题连续追问原则上不超过2次；"
                "不得重复已问问题；最低题量前不得结束，最高题量必须结束。"
            ),
        }

    def _has_core_topic_coverage(self, qa_history: list[QARecord]) -> bool:
        history_items = [
            {"question_type": qa.question_type, "question": qa.question}
            for qa in qa_history
        ]
        covered_topics = _covered_topics_from_items(self.spec.core_topics, history_items)
        return len(covered_topics) >= len(self.spec.core_topics)

    def _fallback_question(self, qa_history: list[JSONDict], question_kind: str) -> str:
        covered_topics = _covered_topics_from_items(
            self.spec.core_topics,
            _active_history_items(qa_history),
        )
        uncovered_topics = [topic for topic in self.spec.core_topics if topic not in covered_topics]
        topic = uncovered_topics[0] if uncovered_topics else "另一个核心评价维度"
        if question_kind == "follow_up":
            return f"围绕刚才的回答，请补充一个能验证「{topic}」的具体细节或判断依据。"
        return (
            f"我们切换到「{topic}」。请结合一个不同于前面问题的具体场景，说明你的做法和结果。"
        )

    def _fallback_question_type(self, qa_history: list[JSONDict]) -> str:
        covered_topics = _covered_topics_from_items(
            self.spec.core_topics,
            _active_history_items(qa_history),
        )
        for topic, aliases in self.spec.core_topics.items():
            if topic not in covered_topics and aliases:
                return aliases[0]
        return f"{self.spec.round_type}_question"

    def _should_replace_initial_technical_project_question(
        self,
        question_type: str,
        question: str,
        qa_history: list[JSONDict],
    ) -> bool:
        if self.spec.round_type != "technical" or len(qa_history) >= 2:
            return False
        text = f"{question_type} {question}".lower()
        return "project" in text or "项目" in text

    def summarize(self, qa_history: list[QARecord], is_reference_only: bool) -> JSONDict:
        answered_count = sum(1 for qa in qa_history if qa.answer)
        score = 0
        result = "failed"
        reference_note = "本轮提前结束，评价仅供参考。" if is_reference_only else None
        return {
            "score": score,
            "result": result,
            "dimension_reviews": [
                {"dimension": dimension, "review": "未接入结构化单题评分时不生成保底分。"}
                for dimension in self.spec.dimensions
            ],
            "main_issues": [] if answered_count else ["本轮可用回答较少，评价证据不足。"],
            "suggestions": ["继续补充可量化的项目细节和复盘证据。"],
            "evidence": [qa.question for qa in qa_history if qa.answer][:5],
            "is_reference_only": is_reference_only,
            "reference_note": reference_note,
        }


def count_questions(qa_history: list[QARecord]) -> dict[str, int]:
    active_history = [
        qa for qa in qa_history if getattr(qa, "question_status", "active") == "active"
    ]
    return {
        "main": sum(1 for qa in active_history if qa.question_kind == "main"),
        "follow_up": sum(1 for qa in active_history if qa.question_kind == "follow_up"),
        "total": len(active_history),
    }


def _active_history_items(qa_history: list[JSONDict]) -> list[JSONDict]:
    return [
        item
        for item in qa_history
        if str(item.get("question_status") or "active") == "active"
    ]


def _covered_topics_from_items(
    core_topics: dict[str, list[str]],
    qa_history: list[JSONDict],
) -> list[str]:
    covered: list[str] = []
    for topic, aliases in core_topics.items():
        needles = [topic, *aliases]
        for item in qa_history:
            haystack = f"{item.get('question_type') or ''} {item.get('question') or ''}".lower()
            if any(needle.lower() in haystack for needle in needles):
                covered.append(topic)
                break
    return covered


def _is_duplicate_question(question: str, qa_history: list[JSONDict]) -> bool:
    normalized = _normalize_question(question)
    if not normalized:
        return False
    return any(
        normalized == _normalize_question(str(item.get("question") or ""))
        for item in qa_history
    )


def _normalize_question(question: str) -> str:
    return "".join(char for char in question.lower() if char.isalnum())


def _score_requires_more_signal(latest_question_score: Any | None) -> bool:
    if latest_question_score is None:
        return False
    should_follow_up = _get_score_value(latest_question_score, "should_follow_up")
    total_score = _get_score_value(latest_question_score, "total_score")
    if should_follow_up is True:
        return True
    if isinstance(total_score, int) and total_score < 60:
        return True
    return False


def _get_score_value(score: Any, key: str) -> Any:
    if isinstance(score, dict):
        return score.get(key)
    return getattr(score, key, None)
