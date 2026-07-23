from dataclasses import replace
from datetime import datetime
from typing import Any, Literal, Protocol

from fastapi import status

from app.core.errors import AppError, ErrorCode
from app.repositories.history import (
    FeedbackReportRecord,
    HistoryInterviewRecord,
    HistoryQARecord,
    HistoryRoundRecord,
    ReportListRecord,
)
from app.repositories.users import UserRecord
from app.schemas.history import (
    FeedbackReportSummary,
    HistoryDetail,
    HistoryListItem,
    HistoryListResponse,
    HistoryQAItem,
    HistoryRound,
    ReportListItem,
    ReportListResponse,
    ReportQualitySummary,
    ReportRoundScoreSource,
    ResumeSummary,
)
from app.services.interview_strategy import round_label as _round_label
from app.services.short_term_memory_store import ShortTermMemoryStoreError


class HistoryRepositoryProtocol(Protocol):
    def list_by_user(self, user_id: int) -> list[HistoryInterviewRecord]:
        ...

    def list_interviews_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        status_filter: str | None = None,
    ) -> list[HistoryInterviewRecord]:
        ...

    def list_reports_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        score_filter: str | None = None,
        sort: str = "recent",
    ) -> list[ReportListRecord]:
        ...

    def get_by_id(self, interview_id: int) -> HistoryInterviewRecord | None:
        ...

    def get_by_id_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> HistoryInterviewRecord | None:
        ...

    def delete_by_id_for_user(self, interview_id: int, user_id: int) -> bool:
        ...

    def delete_all_by_user(self, user_id: int) -> int:
        ...

    def list_interview_ids_by_user(self, user_id: int) -> list[int]:
        ...


class ShortTermMemoryStoreProtocol(Protocol):
    def delete(self, user_id: int, interview_id: int) -> bool:
        ...

    def delete_many(self, user_id: int, interview_ids: list[int]) -> int:
        ...


class HistoryService:
    def __init__(
        self,
        history_repository: HistoryRepositoryProtocol,
        short_term_memory_store: ShortTermMemoryStoreProtocol | None = None,
    ) -> None:
        self.history_repository = history_repository
        self.short_term_memory_store = short_term_memory_store

    def list_history_page(
        self,
        current_user: UserRecord,
        *,
        limit: int,
        offset: int,
        query: str = "",
        status_filter: Literal["created", "in_progress", "finished"] | None = None,
    ) -> HistoryListResponse:
        page_size = _page_size(limit)
        page_offset = max(offset, 0)
        records = self.history_repository.list_interviews_by_user(
            current_user.id,
            limit=page_size + 1,
            offset=page_offset,
            query=query,
            status_filter=status_filter,
        )
        items = [
            _to_list_item(record)
            for record in records[:page_size]
            if record.user_id == current_user.id
        ]
        next_offset = page_offset + page_size if len(records) > page_size else None
        return HistoryListResponse(items=items, next_offset=next_offset)

    def list_reports(self, current_user: UserRecord) -> list[ReportListItem]:
        records = self.history_repository.list_reports_by_user(current_user.id)
        return [_to_report_item(record) for record in records if record.user_id == current_user.id]

    def list_reports_page(
        self,
        current_user: UserRecord,
        *,
        limit: int,
        offset: int,
        query: str = "",
        score_filter: Literal["high", "middle"] | None = None,
        sort: Literal["recent", "score-desc", "score-asc"] = "recent",
    ) -> ReportListResponse:
        page_size = _page_size(limit)
        page_offset = max(offset, 0)
        records = self.history_repository.list_reports_by_user(
            current_user.id,
            limit=page_size + 1,
            offset=page_offset,
            query=query,
            score_filter=score_filter,
            sort=sort,
        )
        items = [
            _to_report_item(record)
            for record in records[:page_size]
            if record.user_id == current_user.id
        ]
        next_offset = page_offset + page_size if len(records) > page_size else None
        return ReportListResponse(items=items, next_offset=next_offset)

    def get_detail(self, interview_id: int, current_user: UserRecord) -> HistoryDetail:
        record = self.history_repository.get_by_id_for_user(interview_id, current_user.id)
        if record is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        return _to_detail(record)

    def delete_history_item(self, interview_id: int, current_user: UserRecord) -> None:
        deleted = self.history_repository.delete_by_id_for_user(interview_id, current_user.id)
        if not deleted:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if self.short_term_memory_store is not None:
            try:
                self.short_term_memory_store.delete(current_user.id, interview_id)
            except ShortTermMemoryStoreError as exc:
                raise _short_memory_cleanup_error() from exc

    def clear_history(self, current_user: UserRecord) -> None:
        interview_ids = (
            self.history_repository.list_interview_ids_by_user(current_user.id)
            if self.short_term_memory_store is not None
            else []
        )
        self.history_repository.delete_all_by_user(current_user.id)
        if self.short_term_memory_store is not None and interview_ids:
            try:
                self.short_term_memory_store.delete_many(current_user.id, interview_ids)
            except ShortTermMemoryStoreError as exc:
                raise _short_memory_cleanup_error() from exc


def _short_memory_cleanup_error() -> AppError:
    return AppError(
        ErrorCode.BUSINESS_ERROR,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        message="短期记忆清理暂时失败，请稍后重试删除。",
    )


def _to_list_item(record: HistoryInterviewRecord) -> HistoryListItem:
    return HistoryListItem(
        interview_id=record.id,
        target_position=record.target_position,
        status=record.status,
        overall_status=record.overall_status,
        created_at=record.created_at,
        updated_at=_history_updated_at(record),
        started_at=record.started_at,
        ended_at=record.ended_at,
    )


def _page_size(limit: int) -> int:
    return max(1, min(limit, 100))


def _experience_mode(value: str) -> Literal["training", "simulation"]:
    return "simulation" if value == "simulation" else "training"


def _to_report_item(record: ReportListRecord) -> ReportListItem:
    return ReportListItem(
        interview_id=record.interview_id,
        target_position=record.target_position,
        score=record.score,
        report_reliability_status=record.report_reliability_status,
        created_at=record.created_at,
        used_candidate_memory=record.used_candidate_memory,
    )


def _history_updated_at(record: HistoryInterviewRecord) -> datetime | None:
    return (
        record.ended_at
        or record.last_active_at
        or record.started_at
        or record.created_at
    )


def _to_detail(record: HistoryInterviewRecord) -> HistoryDetail:
    visible_record = replace(record, qa_history=_history_qa_for_detail(record))
    return HistoryDetail(
        interview_id=record.id,
        target_position=record.target_position,
        status=record.status,
        mode=record.mode,
        experience_mode=_experience_mode(record.experience_mode),
        job_description=record.job_description,
        overall_status=record.overall_status,
        rounds=[_to_round(item) for item in visible_record.rounds or []],
        qa_history=[_to_qa_item(item) for item in visible_record.qa_history or []],
        report_quality=_report_quality(visible_record),
        resume=ResumeSummary(
            id=record.resume.id,
            created_at=record.resume.created_at,
            structured_data=record.resume.structured_data,
        ),
        feedback_report=_to_feedback_summary(visible_record),
        started_at=record.started_at,
        ended_at=record.ended_at,
        harness_status=record.harness_status,
        recovery_count=record.recovery_count,
        had_degradation=record.had_degradation,
        last_harness_error=record.last_harness_error,
    )


def _history_qa_for_detail(record: HistoryInterviewRecord) -> list[HistoryQARecord]:
    qa_history = list(record.qa_history or [])
    if record.experience_mode != "simulation":
        return qa_history
    finished_round_ids = {
        item.id
        for item in record.rounds or []
        if item.status in {"completed", "finished_early"}
    }
    interview_finished = record.overall_status in {"finished", "completed"}
    return [
        item
        if item.question_evaluation is None
        or item.round_id in finished_round_ids
        or (item.round_id is None and interview_finished)
        else replace(item, question_evaluation=None)
        for item in qa_history
    ]


def _to_feedback_summary(record: HistoryInterviewRecord) -> FeedbackReportSummary | None:
    feedback_report = record.feedback_report
    if feedback_report is None:
        return None
    return FeedbackReportSummary(
        score=feedback_report.score,
        weaknesses=feedback_report.weaknesses,
        suggestions=feedback_report.suggestions,
        recommendation=feedback_report.recommendation,
        round_scores=feedback_report.round_scores,
        strengths=feedback_report.strengths,
        ability_analysis=feedback_report.ability_analysis,
        job_match=feedback_report.job_match,
        final_conclusion=feedback_report.final_conclusion,
        confidence=feedback_report.confidence,
        reference_note=feedback_report.reference_note,
        report_reliability_status=feedback_report.report_reliability_status,
        detailed_feedback=_detailed_feedback(record),
    )


def _to_round(round_record: HistoryRoundRecord) -> HistoryRound:
    return HistoryRound(
        id=round_record.id,
        round_type=round_record.round_type,
        status=round_record.status,
        score=round_record.score,
        result=round_record.result,
        summary=round_record.summary,
        started_at=round_record.started_at,
        ended_at=round_record.ended_at,
        elapsed_seconds=_round_elapsed_seconds(round_record),
    )


def _to_qa_item(qa_record: HistoryQARecord) -> HistoryQAItem:
    return HistoryQAItem(
        id=qa_record.id,
        round_id=qa_record.round_id,
        round_type=qa_record.round_type,
        sequence=qa_record.sequence,
        question_type=qa_record.question_type,
        question=qa_record.question,
        answer=qa_record.answer,
        question_kind=qa_record.question_kind,
        parent_question_id=qa_record.parent_question_id,
        created_at=qa_record.created_at,
        question_evaluation=qa_record.question_evaluation,
    )


def _report_quality(record: HistoryInterviewRecord) -> ReportQualitySummary:
    rounds = record.rounds or []
    qa_history = record.qa_history or []
    selected_rounds = [item for item in rounds if item.status != "skipped"]
    completed_rounds = [
        item for item in selected_rounds if item.status in {"completed", "finished_early"}
    ]
    answered_count = sum(1 for item in qa_history if item.answer and item.answer.strip())
    evaluated_count = sum(
        1
        for item in qa_history
        if item.answer
        and item.answer.strip()
        and _question_total_score(item.question_evaluation) is not None
    )
    coverage = int(round(evaluated_count * 100 / answered_count)) if answered_count else 0
    return ReportQualitySummary(
        completed_round_count=len(completed_rounds),
        selected_round_count=len(selected_rounds),
        answered_question_count=answered_count,
        evaluated_question_count=evaluated_count,
        score_coverage_percent=coverage,
        reliability_reasons=_reliability_reasons(
            record=record,
            selected_rounds=selected_rounds,
            answered_count=answered_count,
            evaluated_count=evaluated_count,
        ),
        score_sources=[
            _round_score_source(round_record, qa_history, record.feedback_report)
            for round_record in selected_rounds
        ],
    )


def _detailed_feedback(record: HistoryInterviewRecord) -> dict[str, Any]:
    rounds = record.rounds or []
    qa_history = record.qa_history or []
    round_reviews = [_round_review(round_record, qa_history) for round_record in rounds]
    problem_diagnosis = _problem_diagnosis(record, round_reviews)
    action_plan = _action_plan(problem_diagnosis, record.feedback_report)
    return {
        "problem_diagnosis": problem_diagnosis,
        "round_reviews": round_reviews,
        "action_plan": action_plan,
        "follow_up_questions": _follow_up_questions(problem_diagnosis, round_reviews),
    }


def _round_review(
    round_record: HistoryRoundRecord,
    qa_history: list[HistoryQARecord],
) -> dict[str, Any]:
    summary = round_record.summary or {}
    round_qa = [item for item in qa_history if item.round_id == round_record.id]
    question_issues = [
        issue
        for item in round_qa
        for issue in _string_list((item.question_evaluation or {}).get("issues"))
    ]
    question_evidence = [
        evidence
        for item in round_qa
        for evidence in _string_list((item.question_evaluation or {}).get("evidence"))
    ]
    follow_ups = [
        str((item.question_evaluation or {}).get("follow_up_direction"))
        for item in round_qa
        if (item.question_evaluation or {}).get("follow_up_direction")
    ]
    issues = _dedupe_strings([
        *_string_list(summary.get("main_issues") or summary.get("weaknesses")),
        *question_issues,
    ])
    suggestions = _dedupe_strings([
        *_string_list(summary.get("suggestions")),
        *follow_ups,
    ])
    return {
        "round_type": round_record.round_type,
        "status": round_record.status,
        "score": _round_summary_score(round_record),
        "result": round_record.result or summary.get("result"),
        "strengths": _string_list(summary.get("strengths")),
        "issues": issues[:6],
        "evidence": _dedupe_strings([
            *_string_list(summary.get("evidence")),
            *question_evidence,
            *[item.question for item in round_qa if item.answer],
        ])[:6],
        "suggestions": suggestions[:5],
        "answered_question_count": sum(
            1 for item in round_qa if item.answer and item.answer.strip()
        ),
        "evaluated_question_count": sum(1 for item in round_qa if item.question_evaluation),
        "is_reference_only": round_record.is_reference_only
        or bool(summary.get("is_reference_only")),
    }


def _problem_diagnosis(
    record: HistoryInterviewRecord,
    round_reviews: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    report = record.feedback_report
    items: list[dict[str, Any]] = []
    for review in round_reviews:
        score = review.get("score")
        issues = _string_list(review.get("issues"))
        if not issues and isinstance(score, int) and score >= 70:
            continue
        issue_title = issues[0] if issues else "证据覆盖不足"
        title = f"{_round_label(str(review.get('round_type')))}：{issue_title}"
        severity = "high" if not isinstance(score, int) or score < 60 else "medium"
        items.append({
            "title": title,
            "severity": severity,
            "evidence": _string_list(review.get("evidence"))[:3] or ["该轮缺少足够可验证证据。"],
            "impact": f"影响对{_round_label(str(review.get('round_type')))}相关能力的可信判断。",
            "suggestion": (
                _string_list(review.get("suggestions"))[0]
                if _string_list(review.get("suggestions"))
                else "补充更具体的背景、行动、结果、技术取舍和量化数据。"
            ),
        })
    for risk in _string_list(report.weaknesses if report else []):
        items.append({
            "title": risk,
            "severity": "medium",
            "evidence": ["来自最终总评的主要不足。"],
            "impact": "可能影响岗位匹配度和最终录用建议。",
            "suggestion": "结合对应轮次问答补充可验证案例，并在下次面试中主动说明。",
        })
    if not items:
        items.append({
            "title": "暂未发现严重短板，但仍需补充高质量证据",
            "severity": "low",
            "evidence": ["已完成轮次未暴露明显高风险问题。"],
            "impact": "当前报告可用于复盘，但高阶能力仍需要更多题目验证。",
            "suggestion": "继续准备技术细节、失败复盘、协作推进和量化结果。",
        })
    return _dedupe_dicts(items, "title")[:6]


def _action_plan(
    problem_diagnosis: list[dict[str, Any]],
    report: FeedbackReportRecord | None,
) -> list[dict[str, Any]]:
    suggestions = _string_list(report.suggestions if report else [])
    items = [
        {
            "title": "优先修复报告中的高影响问题",
            "priority": "high",
            "steps": [
                problem_diagnosis[0]["suggestion"] if problem_diagnosis else "复盘本次主要不足。",
                "为每个薄弱点准备一个具体项目案例。",
                "回答时补充量化结果、个人贡献和复盘结论。",
            ],
            "expected_outcome": "提升下一次面试中问题回答的证据密度和可信度。",
        }
    ]
    for suggestion in suggestions[:3]:
        items.append({
            "title": suggestion,
            "priority": "medium",
            "steps": [
                "把建议拆成一个可练习的问题清单。",
                "准备 2 分钟结构化回答，覆盖背景、行动和结果。",
                "用本次报告中的问题逐条校验是否已经补齐。",
            ],
            "expected_outcome": "让改进建议落到可执行的面试准备动作。",
        })
    return _dedupe_dicts(items, "title")[:5]


def _follow_up_questions(
    problem_diagnosis: list[dict[str, Any]],
    round_reviews: list[dict[str, Any]],
) -> list[str]:
    questions = [
        f"针对“{item['title']}”，请补充一个具体案例、你的行动和最终结果。"
        for item in problem_diagnosis[:4]
    ]
    for review in round_reviews:
        if _string_list(review.get("issues")):
            questions.append(
                f"{_round_label(str(review.get('round_type')))}的薄弱点是“{_string_list(review.get('issues'))[0]}”，下次你会如何回答？"
            )
    if not questions:
        questions.append("请选择一个最能体现岗位能力的项目，说明关键决策、技术取舍和量化收益。")
    return _dedupe_strings(questions)[:6]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_dicts(values: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        item_key = str(value.get(key) or "")
        if item_key and item_key not in seen:
            seen.add(item_key)
            result.append(value)
    return result


def _round_score_source(
    round_record: HistoryRoundRecord,
    qa_history: list[HistoryQARecord],
    feedback_report: FeedbackReportRecord | None,
) -> ReportRoundScoreSource:
    round_questions = [item for item in qa_history if item.round_id == round_record.id]
    answered_count = sum(1 for item in round_questions if item.answer and item.answer.strip())
    evaluated_count = sum(
        1
        for item in round_questions
        if item.answer
        and item.answer.strip()
        and _question_total_score(item.question_evaluation) is not None
    )
    final_score = _final_round_score(round_record.round_type, feedback_report)
    summary_score = _round_summary_score(round_record)
    if final_score is not None:
        source = "final_report"
        score = final_score
    elif round_record.score is not None:
        source = "round_summary"
        score = round_record.score
    elif summary_score is not None:
        source = "round_summary"
        score = summary_score
    else:
        source = "none"
        score = None
    return ReportRoundScoreSource(
        round_type=round_record.round_type,
        status=round_record.status,
        score=score,
        source=source,
        answered_question_count=answered_count,
        evaluated_question_count=evaluated_count,
        is_reference_only=round_record.is_reference_only
        or round_record.status in {"finished_early", "cancelled"},
    )


def _reliability_reasons(
    *,
    record: HistoryInterviewRecord,
    selected_rounds: list[HistoryRoundRecord],
    answered_count: int,
    evaluated_count: int,
) -> list[str]:
    reasons: list[str] = []
    report = record.feedback_report
    if report is None:
        reasons.append("未生成总评报告。")
    elif report.report_reliability_status == "unavailable":
        reasons.append("执行校验失败，报告不可用。")
    elif report.report_reliability_status == "reference_only":
        reasons.append("存在提前结束或恢复降级，报告仅供参考。")
    if report is not None and report.confidence == "low":
        reasons.append("总评置信度为低。")
    if record.had_degradation or record.recovery_count > 0:
        reasons.append("面试过程中发生过降级或自动恢复。")
    if any(item.status == "finished_early" or item.is_reference_only for item in selected_rounds):
        reasons.append("至少一轮提前结束。")
    if any(item.status == "cancelled" for item in selected_rounds):
        reasons.append("存在未完成轮次。")
    if answered_count == 0:
        reasons.append("缺少可用于评分的有效回答。")
    elif evaluated_count < answered_count:
        reasons.append("部分有效回答没有题目级评分。")
    if not reasons:
        reasons.append("所有已完成轮次均有可用评分证据。")
    return reasons


def _question_total_score(evaluation: dict[str, object] | None) -> int | None:
    score = evaluation.get("total_score") if evaluation else None
    return int(score) if isinstance(score, (int, float)) else None


def _final_round_score(
    round_type: str,
    feedback_report: FeedbackReportRecord | None,
) -> int | None:
    round_scores = feedback_report.round_scores if feedback_report is not None else None
    for item in round_scores or []:
        if item.get("round_type") == round_type and isinstance(item.get("score"), (int, float)):
            return int(item["score"])
    return None


def _round_summary_score(round_record: HistoryRoundRecord) -> int | None:
    score = round_record.summary.get("score") if round_record.summary else None
    return int(score) if isinstance(score, (int, float)) else None


def _round_elapsed_seconds(round_record: HistoryRoundRecord) -> int:
    if round_record.started_at is None:
        return 0
    ended_at = round_record.ended_at
    if ended_at is None and round_record.status == "in_progress":
        ended_at = datetime.utcnow()
    if ended_at is None:
        return 0
    return max(0, int((ended_at - round_record.started_at).total_seconds()))
