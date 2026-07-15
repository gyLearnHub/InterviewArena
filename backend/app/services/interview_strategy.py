from typing import Any

from app.repositories.interviews import InterviewRecord, InterviewRoundRecord

GOAL_LABELS = {
    "internship": "实习",
    "campus": "校招",
    "big_tech": "冲刺大厂",
}
DIFFICULTY_LABELS = {
    "easy": "简单",
    "normal": "普通",
    "pressure": "压力",
}
ROUND_LABELS = {
    "resume": "简历面",
    "technical": "技术面",
    "manager": "主管面",
    "hr": "HR 面",
}
GOAL_GUIDANCE = {
    "internship": "关注基础掌握、学习潜力、项目真实性和岗位理解。",
    "campus": "平衡基础能力、项目深度、工程意识和沟通协作。",
    "big_tech": "提高追问深度，关注系统性思考、边界条件、权衡和稳定表达。",
}
DIFFICULTY_GUIDANCE = {
    "easy": "提问清晰友好，允许候选人逐步展开，追问以补充证据为主。",
    "normal": "按真实校招节奏推进，保持适中追问和覆盖面。",
    "pressure": "提高追问密度和标准，加入边界、反例、取舍和抗压表达观察。",
}


def round_label(round_type: str | None) -> str:
    normalized = str(round_type or "")
    return ROUND_LABELS.get(normalized, normalized)


def recommendation_for_score(score: int) -> str:
    if score >= 85:
        return "强烈建议录用"
    if score >= 75:
        return "建议录用"
    if score >= 65:
        return "谨慎录用"
    if score >= 60:
        return "暂缓决定"
    return "不建议录用"


def interview_strategy_payload(
    interview: InterviewRecord,
    round_record: InterviewRoundRecord | None = None,
    *,
    remaining_seconds: int | None = None,
    closing_window_seconds: int = 180,
) -> dict[str, Any]:
    goal = interview.interview_goal if interview.interview_goal in GOAL_LABELS else "campus"
    configured_difficulty = (
        round_record.difficulty if round_record is not None else interview.difficulty
    )
    difficulty = configured_difficulty if configured_difficulty in DIFFICULTY_LABELS else "normal"
    time_limit = int(
        round_record.time_limit_minutes
        if round_record is not None
        else interview.time_limit_minutes or 45
    )
    is_closing = remaining_seconds is not None and remaining_seconds <= closing_window_seconds
    return {
        "goal": goal,
        "goal_label": GOAL_LABELS[goal],
        "goal_guidance": GOAL_GUIDANCE[goal],
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS[difficulty],
        "difficulty_guidance": DIFFICULTY_GUIDANCE[difficulty],
        "time_limit_minutes": time_limit,
        "remaining_seconds": remaining_seconds,
        "closing_window_seconds": closing_window_seconds,
        "is_closing_stage": is_closing,
        "time_guidance": (
            "已进入最后3分钟，只完成当前话题或提出简短收尾问题，不再展开新的长追问。"
            if is_closing
            else "结合剩余时间、回答质量和覆盖面调整追问深度，保证话题连贯并留出自然收尾时间。"
        ),
        "question_count_policy": "每轮题量由 Agent 根据回答质量、覆盖面和剩余时间动态判定。",
    }
