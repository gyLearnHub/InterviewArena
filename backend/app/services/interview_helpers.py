from datetime import datetime
from typing import Any, cast

from fastapi import status

from app.agents import ROUND_ORDER, ROUND_SPECS, count_questions
from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.repositories.interviews import (
    AnswerReanswerAttemptRecord,
    FeedbackReportRecord,
    InterviewRecord,
    InterviewRepository,
    InterviewRoundRecord,
    QARecord,
    ResumeRecord,
)
from app.schemas.interview import (
    DEFAULT_INTERVIEW_DIFFICULTY,
    DEFAULT_INTERVIEW_EXPERIENCE_MODE,
    DEFAULT_INTERVIEW_GOAL,
    DEFAULT_TIME_LIMIT_MINUTES,
    JOB_DESCRIPTION_MAX_LENGTH,
    AnswerReanswerAttemptResponse,
    FeedbackReportResponse,
    InterviewDifficulty,
    InterviewRoundResponse,
    RoundQuestionResponse,
    TimeLimitMinutes,
)
from app.services.interview_strategy import DIFFICULTY_LABELS, GOAL_LABELS
from app.services.interview_strategy import recommendation_for_score as _recommendation
from app.services.interview_strategy import round_label as _round_label

ACTIVE_ROUND_STATUSES = {"pending", "in_progress"}
FINISHED_ROUND_STATUSES = {"completed", "finished_early"}
ELAPSED_SECONDS_CAP = 300
ACTIVE_QUESTION_STATUS = "active"
TIME_LIMIT_MINUTES = {30, 45, 60}
ROUND_CLOSING_WINDOW_SECONDS = 3 * 60
FINAL_QUESTION_TYPE = "round_final"
FINAL_QUESTION_PREFIX = "这是本轮最后一个问题："

def _require_resume(
    repository: InterviewRepository,
    resume_id: int,
    user_id: int,
    *,
    snapshot: dict[str, Any] | None = None,
) -> Any:
    resume = repository.get_resume_for_user(resume_id, user_id)
    if resume is not None:
        return resume
    if snapshot is not None:
        return ResumeRecord(
            id=resume_id,
            user_id=user_id,
            structured_data=dict(snapshot),
        )
    raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)


def _has_answer_evidence(history: list[QARecord]) -> bool:
    return any(qa.answer is not None and qa.answer.strip() for qa in history)


def _qa_history(
    qa_records: list[QARecord],
    answer_override: dict[int, str] | None = None,
    evaluation_by_qa_id: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    overrides = answer_override or {}
    evaluations = evaluation_by_qa_id or {}
    history: list[dict[str, Any]] = []
    for qa in qa_records:
        item = {
            "id": qa.id,
            "sequence": qa.sequence,
            "question_type": qa.question_type,
            "question": qa.question,
            "answer": overrides.get(qa.sequence, qa.answer),
            "question_kind": qa.question_kind,
            "question_status": qa.question_status,
            "parent_question_id": qa.parent_question_id,
            "regenerated_from_question_id": qa.regenerated_from_question_id,
        }
        evaluation = evaluations.get(qa.id)
        if evaluation is not None:
            item["evaluation_follow_up"] = evaluation
        history.append(item)
    return history


def _merge_generation_history(
    audit_history: list[QARecord],
    active_history_payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payload_by_id = {
        int(item["id"]): item for item in active_history_payload if isinstance(item.get("id"), int)
    }
    return [payload_by_id.get(qa.id, _qa_history([qa])[0]) for qa in audit_history]


def _normalize_selected_rounds(selected_rounds: list[str] | None) -> list[str]:
    values = list(ROUND_ORDER) if selected_rounds is None else selected_rounds
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if item not in ROUND_SPECS or item in seen:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        seen.add(item)
        normalized.append(item)
    if not normalized:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return normalized


def _normalize_interview_goal(value: str) -> str:
    goal = (value or DEFAULT_INTERVIEW_GOAL).strip()
    if goal not in GOAL_LABELS:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return goal


def _normalize_interview_difficulty(value: str) -> str:
    difficulty = (value or DEFAULT_INTERVIEW_DIFFICULTY).strip()
    if difficulty not in DIFFICULTY_LABELS:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return difficulty


def _normalize_experience_mode(value: str) -> str:
    experience_mode = (value or DEFAULT_INTERVIEW_EXPERIENCE_MODE).strip()
    if experience_mode not in {"training", "simulation"}:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return experience_mode


def _normalize_time_limit_minutes(value: int) -> int:
    if value not in TIME_LIMIT_MINUTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return value


def _normalize_practice_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return text[:500]


def _normalize_optional_practice_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text[:500] if text else None


def _practice_rounds(interview: InterviewRecord, round_type: str | None) -> list[str]:
    if round_type is not None:
        if round_type not in ROUND_SPECS:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        return [round_type]
    return _normalize_selected_rounds(interview.selected_rounds)


def _practice_job_description(
    *,
    original_job_description: str | None,
    weakness: str,
    suggestion: str | None,
    round_type: str | None,
) -> str:
    parts = [
        "【专项再练】",
        f"本次面试来源于历史报告的薄弱项：{weakness}",
    ]
    if suggestion:
        parts.append(f"改进建议：{suggestion}")
    if round_type:
        parts.append(f"优先围绕{_round_label(round_type)}相关能力追问。")
    parts.append("请面试官优先验证该薄弱项是否补齐，并根据回答质量继续追问。")
    if original_job_description:
        parts.extend(["", "原岗位 JD：", original_job_description.strip()])
    return "\n".join(parts)[:JOB_DESCRIPTION_MAX_LENGTH]


def _round_rows(
    interview_id: int,
    selected_rounds: list[str],
    *,
    specs: dict[str, Any] | None = None,
    difficulty: str = DEFAULT_INTERVIEW_DIFFICULTY,
    time_limit_minutes: int = DEFAULT_TIME_LIMIT_MINUTES,
) -> list[dict[str, Any]]:
    selected = set(selected_rounds)
    rows: list[dict[str, Any]] = []
    row_order = [
        *selected_rounds,
        *[item for item in ROUND_ORDER if item not in selected],
    ]
    for round_type in row_order:
        spec = (specs or ROUND_SPECS)[round_type]
        rows.append(
            {
                "interview_id": interview_id,
                "agent_type": spec.agent_type,
                "round_type": round_type,
                "status": "pending" if round_type in selected else "skipped",
                "min_main_questions": 0,
                "max_main_questions": spec.max_main_questions,
                "min_total_questions": 0,
                "max_total_questions": spec.max_total_questions,
                "difficulty": difficulty,
                "time_limit_minutes": time_limit_minutes,
            }
        )
    return rows


def _ordered_rounds(
    interview: InterviewRecord,
    rounds: list[InterviewRoundRecord],
) -> list[InterviewRoundRecord]:
    selected_order = interview.selected_rounds or list(ROUND_ORDER)
    order = {round_type: index for index, round_type in enumerate(selected_order)}
    skipped_order = {round_type: len(order) + index for index, round_type in enumerate(ROUND_ORDER)}
    return sorted(
        rounds,
        key=lambda item: order.get(item.round_type, skipped_order.get(item.round_type, len(order))),
    )


def _round_response(
    round_record: InterviewRoundRecord,
    interview: InterviewRecord | None = None,
) -> InterviewRoundResponse:
    elapsed_seconds = _round_elapsed_seconds(round_record, interview, datetime.utcnow())

    return InterviewRoundResponse(
        id=round_record.id,
        round_type=round_record.round_type,
        status=round_record.status,
        score=round_record.score,
        result=round_record.result,
        summary=round_record.summary,
        started_at=round_record.started_at,
        ended_at=round_record.ended_at,
        elapsed_seconds=elapsed_seconds,
        difficulty=cast(InterviewDifficulty, round_record.difficulty),
        time_limit_minutes=cast(TimeLimitMinutes, round_record.time_limit_minutes),
        execution_status=round_record.execution_status,
        retry_count=round_record.retry_count,
    )


def _round_question_response(qa: QARecord) -> RoundQuestionResponse:
    if qa.round_id is None:
        raise AppError(ErrorCode.BUSINESS_ERROR, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return RoundQuestionResponse(
        id=qa.id,
        round_id=qa.round_id,
        sequence=qa.sequence,
        question_kind=qa.question_kind,
        question_status=qa.question_status,
        parent_question_id=qa.parent_question_id,
        regenerated_from_question_id=qa.regenerated_from_question_id,
        question_type=qa.question_type,
        question=qa.question,
        is_last_question=_is_final_question(qa),
    )


def _feedback_report_response(
    report: FeedbackReportRecord,
    detailed_feedback: dict[str, Any] | None = None,
) -> FeedbackReportResponse:
    return FeedbackReportResponse(
        interview_id=report.interview_id,
        score=report.score,
        weaknesses=report.weaknesses,
        suggestions=report.suggestions,
        recommendation=report.recommendation,
        round_scores=report.round_scores,
        strengths=report.strengths,
        ability_analysis=report.ability_analysis,
        job_match=report.job_match,
        final_conclusion=report.final_conclusion,
        confidence=report.confidence,
        reference_note=report.reference_note,
        used_candidate_memory=report.used_candidate_memory,
        report_reliability_status=getattr(report, "report_reliability_status", "normal"),
        detailed_feedback=detailed_feedback,
    )


def _answer_evaluation_response(
    qa: QARecord,
    round_record: InterviewRoundRecord,
    question_score: Any | None,
) -> dict[str, Any]:
    if question_score is not None:
        payload = dict(question_score.model_dump())
        payload.update(
            {
                "question_id": qa.id,
                "round_id": qa.round_id,
                "status": "succeeded",
            }
        )
        return payload
    return _fallback_answer_evaluation(qa, round_record)


def _active_round_answer_evaluation(
    interview: InterviewRecord,
    answer_evaluation: dict[str, Any],
) -> dict[str, Any] | None:
    if interview.experience_mode == "simulation":
        return None
    return answer_evaluation


def _reanswer_attempt_response(
    attempt: AnswerReanswerAttemptRecord,
    original_evaluation: dict[str, Any] | None,
    *,
    fallback_qa: QARecord | None = None,
    round_record: InterviewRoundRecord | None = None,
) -> AnswerReanswerAttemptResponse:
    evaluation = attempt.evaluation
    if evaluation is None and fallback_qa is not None and round_record is not None:
        evaluation = _fallback_answer_evaluation(
            QARecord(**{**fallback_qa.__dict__, "answer": attempt.answer}),
            round_record,
        )
        evaluation["reanswer_attempt_id"] = attempt.id
    evaluation = evaluation or {
        "question_id": attempt.question_id,
        "reanswer_attempt_id": attempt.id,
        "status": "fallback",
        "total_score": None,
        "dimension_scores": [],
        "strengths": [],
        "issues": [],
        "evidence": [],
        "should_follow_up": False,
        "follow_up_direction": None,
    }
    return AnswerReanswerAttemptResponse(
        id=attempt.id,
        attempt_number=attempt.attempt_number,
        answer=attempt.answer,
        evaluation=evaluation,
        score_delta=_score_delta(original_evaluation, evaluation),
        created_at=attempt.created_at,
    )


def _score_delta(
    original_evaluation: dict[str, Any] | None,
    new_evaluation: dict[str, Any] | None,
) -> int | None:
    original_score = (original_evaluation or {}).get("total_score")
    new_score = (new_evaluation or {}).get("total_score")
    if isinstance(original_score, bool) or isinstance(new_score, bool):
        return None
    if not isinstance(original_score, (int, float)) or not isinstance(new_score, (int, float)):
        return None
    return int(round(new_score - original_score))


def _fallback_answer_evaluation(
    qa: QARecord,
    round_record: InterviewRoundRecord,
) -> dict[str, Any]:
    answer = (qa.answer or "").strip()
    issues: list[str] = []
    strengths: list[str] = []

    if len(answer) < 40:
        issues.append("回答偏短，可以补充背景、行动和结果。")
    if not any(ch.isdigit() for ch in answer) and not _contains_any(
        answer,
        ("提升", "降低", "增长", "减少", "用户", "耗时", "成本", "指标", "数据"),
    ):
        issues.append("可以补充量化结果或影响范围。")
    if not _contains_any(
        answer,
        ("我负责", "我主导", "我设计", "我推进", "我的", "负责", "落地", "实现"),
    ):
        issues.append("可以更明确说明你本人承担的动作。")
    if not _contains_any(
        answer,
        ("取舍", "原因", "因为", "所以", "权衡", "方案", "对比", "风险", "边界"),
    ):
        issues.append("可以补充技术取舍、原因或边界条件。")

    if answer:
        strengths.append("回答已经提供了可继续追问的基础信息。")
    if answer and not issues:
        strengths.append("回答结构较完整，可以继续保持具体证据。")

    return {
        "question_id": qa.id,
        "round_id": qa.round_id,
        "round_type": round_record.round_type,
        "status": "fallback",
        "total_score": None,
        "dimension_scores": [],
        "strengths": strengths[:2],
        "issues": issues[:4],
        "evidence": [answer[:120]] if answer else [],
        "should_follow_up": bool(issues),
        "follow_up_direction": issues[0] if issues else None,
    }


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    normalized = value.lower()
    return any(marker.lower() in normalized for marker in markers)


def _is_final_question(qa: QARecord) -> bool:
    return qa.question_type == FINAL_QUESTION_TYPE


def _with_final_question_notice(question_type: str, question: str) -> tuple[str, str]:
    text = question.strip()
    if not text.startswith(FINAL_QUESTION_PREFIX):
        text = f"{FINAL_QUESTION_PREFIX}{text}"
    return FINAL_QUESTION_TYPE, text


def _final_round_question(
    round_type: str,
    resume_data: dict[str, Any] | None = None,
    history: list[QARecord] | None = None,
) -> str:
    uncovered_projects = _uncovered_projects(resume_data or {}, history or [])
    if round_type == "resume" and len(uncovered_projects) == 1:
        return (
            f"{FINAL_QUESTION_PREFIX}我们切换到简历中的「{uncovered_projects[0]}」。"
            "请说明这个项目的背景、你的具体职责和最能证明结果的一项产出。"
        )
    if round_type == "resume" and uncovered_projects:
        project_list = "、".join(f"「{title}」" for title in uncovered_projects)
        return (
            f"{FINAL_QUESTION_PREFIX}请依次简要补充尚未覆盖的项目：{project_list}。"
            "每个项目说明背景、你的具体职责和一项结果。"
        )
    focus = {
        "resume": (
            "请从整份简历中选择最能证明岗位匹配度的一项经历，"
            "补充一个此前没有说到的关键事实。"
        ),
        "technical": "请总结你解决复杂技术问题时最重要的判断原则，并结合一个具体例子说明。",
        "manager": "请用一个具体案例总结你推动目标落地时最关键的行动和结果。",
        "hr": "请简要说明你选择这个岗位的核心原因，以及你希望在其中获得怎样的成长。",
    }.get(round_type, "请补充一个最能代表你岗位能力、此前尚未提到的关键事实。")
    return f"{FINAL_QUESTION_PREFIX}{focus}"


def _uncovered_projects(
    resume_data: dict[str, Any],
    history: list[QARecord],
) -> list[str]:
    projects = resume_data.get("project_experience")
    if not isinstance(projects, list):
        return []
    questions = " ".join(item.question for item in history)
    normalized_questions = "".join(char for char in questions.casefold() if char.isalnum())
    uncovered: list[str] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        title = next(
            (
                str(project.get(key) or "").strip()
                for key in ("name", "project_name", "title")
                if str(project.get(key) or "").strip()
            ),
            "",
        )
        normalized_title = "".join(char for char in title.casefold() if char.isalnum())
        if normalized_title and normalized_title not in normalized_questions:
            uncovered.append(title)
    return uncovered


def _answer_action_for_question(qa: QARecord) -> str:
    return "follow_up" if qa.question_kind == "follow_up" else "next_question"


def _qa_state_item(
    qa: QARecord,
    question_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": qa.id,
        "round_id": qa.round_id,
        "sequence": qa.sequence,
        "question_type": qa.question_type,
        "question": qa.question,
        "is_last_question": _is_final_question(qa),
        "answer": qa.answer,
        "question_kind": qa.question_kind,
        "question_status": qa.question_status,
        "parent_question_id": qa.parent_question_id,
        "regenerated_from_question_id": qa.regenerated_from_question_id,
        "created_at": qa.created_at,
    }
    if question_evaluation is not None:
        payload["question_evaluation"] = question_evaluation
    return payload


def _next_question_kind(
    current_qa: QARecord,
    history: list[QARecord],
    round_record: InterviewRoundRecord,
    follow_up_recommended: bool | None = None,
) -> str:
    counts = count_questions(history)
    if counts["total"] >= round_record.max_total_questions:
        return "main"
    if current_qa.question_kind == "main" and counts["main"] >= round_record.max_main_questions:
        return "follow_up"
    has_follow_up = any(qa.parent_question_id == current_qa.id for qa in history)
    if current_qa.question_kind == "main" and not has_follow_up:
        if follow_up_recommended is False:
            return "main"
        return "follow_up"
    if follow_up_recommended is True and current_qa.question_kind == "main":
        return "follow_up"
    return "main"


def _parent_answer(history: list[QARecord], qa: QARecord) -> str | None:
    if qa.parent_question_id is None:
        return None
    parent = next((item for item in history if item.id == qa.parent_question_id), None)
    return parent.answer if parent is not None else None


def _elapsed_seconds(interview: InterviewRecord, now: datetime) -> int:
    if interview.last_active_at is None or interview.overall_status != "in_progress":
        return interview.elapsed_seconds
    delta = int((now - interview.last_active_at).total_seconds())
    if delta <= 0:
        return interview.elapsed_seconds
    return interview.elapsed_seconds + min(delta, ELAPSED_SECONDS_CAP)


def _elapsed_seconds_uncapped(interview: InterviewRecord, now: datetime) -> int:
    if interview.last_active_at is None or interview.overall_status != "in_progress":
        return interview.elapsed_seconds
    delta = int((now - interview.last_active_at).total_seconds())
    if delta <= 0:
        return interview.elapsed_seconds
    return interview.elapsed_seconds + delta


def _round_elapsed_seconds(
    round_record: InterviewRoundRecord,
    interview: InterviewRecord | None,
    now: datetime,
) -> int:
    if round_record.started_at is None:
        return 0
    ended_at = round_record.ended_at
    if ended_at is None and round_record.status == "in_progress":
        if interview is not None and interview.overall_status == "paused":
            ended_at = interview.last_active_at
        else:
            ended_at = now
    if ended_at is None:
        return 0
    return max(0, int((ended_at - round_record.started_at).total_seconds()))


def _round_remaining_seconds(
    round_record: InterviewRoundRecord,
    interview: InterviewRecord | None,
    now: datetime,
) -> int:
    limit_seconds = max(0, int(round_record.time_limit_minutes or 45) * 60)
    return max(0, limit_seconds - _round_elapsed_seconds(round_record, interview, now))


def _overall_report(
    interview_id: int,
    rounds: list[InterviewRoundRecord],
    is_reference_only: bool,
) -> dict[str, Any]:
    scored_rounds = [
        round_record
        for round_record in rounds
        if round_record.status in FINISHED_ROUND_STATUSES and round_record.score is not None
    ]
    score = (
        int(sum(round_record.score or 0 for round_record in scored_rounds) / len(scored_rounds))
        if scored_rounds
        else 0
    )
    recommendation = "建议进入下一轮" if is_reference_only else _recommendation(score)
    round_scores = [
        {
            "round_type": round_record.round_type,
            "score": round_record.score,
            "result": round_record.result,
            "is_reference_only": round_record.is_reference_only,
            "status": round_record.status,
        }
        for round_record in rounds
    ]
    reference_note = "面试提前结束，评价仅供参考。" if is_reference_only else None
    return {
        "interview_id": interview_id,
        "score": score,
        "weaknesses": ["部分能力维度仍需结合后续面试继续验证。"],
        "suggestions": ["复盘每轮回答，补充更具体的项目证据、技术取舍和结果数据。"],
        "recommendation": recommendation,
        "round_scores": round_scores,
        "strengths": ["已完成轮次中存在可验证的岗位相关证据。"] if score >= 60 else [],
        "reference_note": reference_note,
    }


def _report_reliability_status(
    interview: InterviewRecord,
    report: dict[str, Any],
    finish_type: str,
) -> str:
    if interview.harness_status == "failed":
        return "unavailable"
    if finish_type == "early" or interview.had_degradation or interview.recovery_count > 0:
        return "reference_only"
    if report.get("reference_note"):
        return "reference_only"
    return "normal"
