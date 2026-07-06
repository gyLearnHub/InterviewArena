from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.repositories.history import HistoryInterviewRecord
from app.repositories.users import UserRecord
from app.schemas.dashboard import (
    DashboardAbilitySummary,
    DashboardInterviewSummary,
    DashboardReportSummary,
    DashboardScoreTrendPoint,
    DashboardSummary,
    DashboardWeakPointSource,
    DashboardWeakPointSummary,
)


class DashboardHistoryRepositoryProtocol(Protocol):
    def list_by_user(self, user_id: int) -> list[HistoryInterviewRecord]:
        ...

    def get_by_id(self, interview_id: int) -> HistoryInterviewRecord | None:
        ...


class DashboardMemoryRepositoryProtocol(Protocol):
    def count_active_candidate_memories(self, user_id: int) -> int:
        ...


class DashboardMemoryTaskRepositoryProtocol(Protocol):
    def count_summary_tasks_by_status(self, user_id: int) -> dict[str, int]:
        ...


@dataclass
class _WeakPointCandidate:
    title: str
    suggestion: str | None
    severity: str
    source: DashboardWeakPointSource
    evidence: list[str]
    updated_at: datetime | None


LOW_INFORMATION_REPORT_WEAKNESSES = {
    "部分能力维度仍需结合后续面试继续验证。",
}
LOW_INFORMATION_REPORT_SUGGESTIONS = {
    "复盘每轮回答，补充更具体的项目证据、技术取舍和结果数据。",
}


class DashboardService:
    def __init__(
        self,
        history_repository: DashboardHistoryRepositoryProtocol,
        memory_repository: DashboardMemoryRepositoryProtocol | None = None,
        memory_task_repository: DashboardMemoryTaskRepositoryProtocol | None = None,
    ) -> None:
        self.history_repository = history_repository
        self.memory_repository = memory_repository
        self.memory_task_repository = memory_task_repository

    def get_summary(self, current_user: UserRecord) -> DashboardSummary:
        records = [
            record
            for record in self.history_repository.list_by_user(current_user.id)
            if record.user_id == current_user.id
        ]
        report_records = [record for record in records if record.feedback_report is not None]
        latest_interview_record = max(
            records,
            key=lambda record: (record.started_at or record.created_at, record.id),
            default=None,
        )
        latest_report_record = max(
            report_records,
            key=_report_sort_key,
            default=None,
        )
        detailed_records = self._recent_detailed_records(records)
        personalized_feedback_used = any(
            bool(record.feedback_report and record.feedback_report.used_candidate_memory)
            for record in report_records
        )
        memory_status, candidate_memory_count = self._memory_state(
            current_user=current_user,
            personalized_feedback_used=personalized_feedback_used,
        )

        return DashboardSummary(
            interview_count=len(records),
            report_count=len(report_records),
            personalized_feedback_used=personalized_feedback_used,
            memory_status=memory_status,
            candidate_memory_count=candidate_memory_count,
            latest_interview=(
                _to_interview_summary(latest_interview_record)
                if latest_interview_record is not None
                else None
            ),
            latest_report=(
                _to_report_summary(latest_report_record)
                if latest_report_record is not None
                else None
            ),
            score_trend=_to_score_trend(report_records),
            score_delta=_score_delta(report_records),
            abilities=(
                _to_ability_summaries(latest_report_record)
                if latest_report_record is not None
                else []
            ),
            weak_points=_to_weak_point_summaries(detailed_records),
        )

    def _memory_state(
        self,
        *,
        current_user: UserRecord,
        personalized_feedback_used: bool,
    ) -> tuple[str, int]:
        if not getattr(current_user, "memory_enabled", True):
            return "disabled", 0
        try:
            candidate_memory_count = (
                self.memory_repository.count_active_candidate_memories(current_user.id)
                if self.memory_repository is not None
                else 0
            )
            task_counts = (
                self.memory_task_repository.count_summary_tasks_by_status(current_user.id)
                if self.memory_task_repository is not None
                else {}
            )
        except Exception:
            return "unavailable", 0

        if personalized_feedback_used:
            return "enabled", candidate_memory_count
        if candidate_memory_count > 0:
            return "ready", candidate_memory_count
        active_task_statuses = ("pending", "processing", "retry_wait")
        if any(task_counts.get(status, 0) > 0 for status in active_task_statuses):
            return "summarizing", candidate_memory_count
        if task_counts.get("failed", 0) > 0:
            return "failed", candidate_memory_count
        return "accumulating", candidate_memory_count

    def _recent_detailed_records(
        self,
        records: list[HistoryInterviewRecord],
    ) -> list[HistoryInterviewRecord]:
        detailed_records: list[HistoryInterviewRecord] = []
        recent_records = sorted(records, key=_activity_sort_key, reverse=True)[:5]
        for record in recent_records:
            detailed_record = self.history_repository.get_by_id(record.id)
            detailed_records.append(detailed_record or record)
        return detailed_records


def _to_interview_summary(record: HistoryInterviewRecord) -> DashboardInterviewSummary:
    return DashboardInterviewSummary(
        interview_id=record.id,
        target_position=record.target_position,
        status=record.status,
        score=record.feedback_report.score if record.feedback_report is not None else None,
        started_at=record.started_at,
        ended_at=record.ended_at,
    )


def _to_report_summary(record: HistoryInterviewRecord) -> DashboardReportSummary:
    if record.feedback_report is None:
        raise ValueError("Dashboard report summary requires feedback_report")
    return DashboardReportSummary(
        interview_id=record.id,
        target_position=record.target_position,
        score=record.feedback_report.score,
        created_at=record.feedback_report.created_at,
        used_candidate_memory=record.feedback_report.used_candidate_memory,
        report_reliability_status=record.feedback_report.report_reliability_status,
    )


def _report_sort_key(record: HistoryInterviewRecord) -> tuple[object, int]:
    if record.feedback_report is None:
        return (record.ended_at or record.started_at or record.created_at, record.id)
    return (
        record.feedback_report.created_at
        or record.ended_at
        or record.started_at
        or record.created_at,
        record.id,
    )


def _to_score_trend(records: list[HistoryInterviewRecord]) -> list[DashboardScoreTrendPoint]:
    trend: list[DashboardScoreTrendPoint] = []
    for record in sorted(records, key=_report_sort_key)[-8:]:
        feedback_report = record.feedback_report
        if feedback_report is None:
            continue
        trend.append(
            DashboardScoreTrendPoint(
                interview_id=record.id,
                score=feedback_report.score,
                created_at=(
                    feedback_report.created_at
                    or record.ended_at
                    or record.started_at
                    or record.created_at
                ),
            )
        )
    return trend


def _score_delta(records: list[HistoryInterviewRecord]) -> int | None:
    sorted_records = [
        record
        for record in sorted(records, key=_report_sort_key)
        if record.feedback_report is not None
    ]
    if len(sorted_records) < 2:
        return None
    latest_report = sorted_records[-1].feedback_report
    previous_report = sorted_records[-2].feedback_report
    if latest_report is None or previous_report is None:
        return None
    return latest_report.score - previous_report.score


def _to_ability_summaries(record: HistoryInterviewRecord) -> list[DashboardAbilitySummary]:
    if record.feedback_report is None or not record.feedback_report.round_scores:
        return []

    abilities: list[DashboardAbilitySummary] = []
    for item in record.feedback_report.round_scores:
        round_type = item.get("round_type")
        if not isinstance(round_type, str) or not round_type:
            continue
        abilities.append(
            DashboardAbilitySummary(
                round_type=round_type,
                score=_score_or_none(item.get("score")),
                result=_text_or_none(item.get("result")),
                status=_text_or_none(item.get("status")),
                is_reference_only=bool(item.get("is_reference_only", False)),
            )
        )
    return abilities


def _to_weak_point_summaries(
    records: list[HistoryInterviewRecord],
) -> list[DashboardWeakPointSummary]:
    candidates = [
        candidate
        for record in records
        for candidate in [
            *_weak_candidates_from_rounds(record),
            *_weak_candidates_from_report(record),
        ]
    ]
    if not candidates:
        if not records:
            return []
        return [_summarize_weak_point([_insufficient_evidence_candidate(records[0])])]

    grouped: dict[str, list[_WeakPointCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(_weak_point_key(candidate.title), []).append(candidate)

    summaries = [_summarize_weak_point(items) for items in grouped.values()]
    return sorted(
        summaries,
        key=lambda item: (
            _severity_rank(item.severity),
            item.occurrence_count,
            item.updated_at or datetime.min,
        ),
        reverse=True,
    )[:3]


def _weak_candidates_from_report(record: HistoryInterviewRecord) -> list[_WeakPointCandidate]:
    report = record.feedback_report
    if report is None:
        return []

    candidates: list[_WeakPointCandidate] = []
    for index, weakness in enumerate(report.weaknesses[:4]):
        title = weakness.strip()
        if not title:
            continue
        suggestion = report.suggestions[index] if index < len(report.suggestions) else None
        if _is_low_information_report_item(title, suggestion):
            continue
        occurred_at = report.created_at or record.ended_at or record.started_at or record.created_at
        evidence = _dedupe_strings([
            "最终报告将该项列为主要薄弱点。",
            *(_string_list(report.ability_analysis)[:2]),
            *([report.final_conclusion] if report.final_conclusion else []),
        ])[:3]
        candidates.append(
            _WeakPointCandidate(
                title=title,
                suggestion=suggestion,
                severity=_severity_from_score(report.score),
                source=DashboardWeakPointSource(
                    interview_id=record.id,
                    target_position=record.target_position,
                    score=report.score,
                    occurred_at=occurred_at,
                    evidence=evidence,
                ),
                evidence=evidence,
                updated_at=occurred_at,
            )
        )
    return candidates


def _insufficient_evidence_candidate(record: HistoryInterviewRecord) -> _WeakPointCandidate:
    report = record.feedback_report
    completed_rounds = [
        round_record
        for round_record in record.rounds or []
        if round_record.status in {"completed", "finished_early"}
    ]
    latest_round = max(
        completed_rounds,
        key=lambda item: item.ended_at or item.started_at or record.created_at,
        default=None,
    )
    answered_count = sum(
        1
        for item in record.qa_history or []
        if item.answer and item.answer.strip()
    )
    occurred_at = (
        (latest_round.ended_at if latest_round else None)
        or (report.created_at if report else None)
        or record.ended_at
        or record.started_at
        or record.created_at
    )
    evidence = _dedupe_strings([
        f"当前记录有 {answered_count} 条有效回答，暂未提取到更具体的薄弱点证据。",
        *(
            ["最终报告只给出了参考性结论，说明还需要更多完成轮次继续验证。"]
            if report is not None
            else []
        ),
        *(
            [f"{_round_label(latest_round.round_type)}已完成，但轮次总结没有返回明确问题项。"]
            if latest_round is not None
            else ["当前还没有完成轮次可用于稳定分析。"]
        ),
    ])[:3]
    return _WeakPointCandidate(
        title="回答证据仍需补充",
        suggestion="下次至少完整完成一个核心轮次，并在回答中补充项目背景、个人动作、结果指标和技术取舍。",
        severity="medium",
        source=DashboardWeakPointSource(
            interview_id=record.id,
            target_position=record.target_position,
            round_type=latest_round.round_type if latest_round else None,
            score=(latest_round.score if latest_round else report.score if report else None),
            occurred_at=occurred_at,
            evidence=evidence,
        ),
        evidence=evidence,
        updated_at=occurred_at,
    )


def _weak_candidates_from_rounds(record: HistoryInterviewRecord) -> list[_WeakPointCandidate]:
    candidates: list[_WeakPointCandidate] = []
    qa_history = record.qa_history or []
    for round_record in record.rounds or []:
        if round_record.status not in {"completed", "finished_early"}:
            continue
        summary = round_record.summary or {}
        issues = _dedupe_strings([
            *_string_list(summary.get("main_issues")),
            *_string_list(summary.get("weaknesses")),
            *_round_question_issues(round_record.id, qa_history),
        ])
        suggestions = _dedupe_strings([
            *_string_list(summary.get("suggestions")),
            *_round_follow_up_directions(round_record.id, qa_history),
        ])
        evidence = _dedupe_strings([
            *_string_list(summary.get("evidence")),
            *_round_question_evidence(round_record.id, qa_history),
        ])[:3]
        fallback_evidence = [
            f"{_round_label(round_record.round_type)}已完成，轮次总结显示该项需要补强。"
        ]
        for index, issue in enumerate(issues[:3]):
            title = issue.strip()
            if not title:
                continue
            occurred_at = (
                round_record.ended_at
                or record.ended_at
                or record.started_at
                or record.created_at
            )
            source_evidence = evidence or fallback_evidence
            suggestion = (
                suggestions[index]
                if index < len(suggestions)
                else (suggestions[0] if suggestions else None)
            )
            candidates.append(
                _WeakPointCandidate(
                    title=title,
                    suggestion=suggestion,
                    severity=_severity_from_score(round_record.score),
                    source=DashboardWeakPointSource(
                        interview_id=record.id,
                        target_position=record.target_position,
                        round_type=round_record.round_type,
                        score=round_record.score,
                        occurred_at=occurred_at,
                        evidence=source_evidence,
                    ),
                    evidence=source_evidence,
                    updated_at=occurred_at,
                )
            )
    return candidates


def _is_low_information_report_item(title: str, suggestion: str | None) -> bool:
    normalized_title = title.strip()
    normalized_suggestion = (suggestion or "").strip()
    return (
        normalized_title in LOW_INFORMATION_REPORT_WEAKNESSES
        or normalized_suggestion in LOW_INFORMATION_REPORT_SUGGESTIONS
    )


def _summarize_weak_point(items: list[_WeakPointCandidate]) -> DashboardWeakPointSummary:
    ordered_items = sorted(items, key=lambda item: item.updated_at or datetime.min, reverse=True)
    latest = ordered_items[0]
    sources = _dedupe_sources([item.source for item in ordered_items])[:3]
    evidence = _dedupe_strings([
        evidence
        for item in ordered_items
        for evidence in item.evidence
    ])[:4]
    round_labels = _dedupe_strings([
        _round_label(source.round_type)
        for source in sources
        if source.round_type
    ])
    source_positions = _dedupe_strings([source.target_position for source in sources])
    summary = _weak_summary_text(
        occurrence_count=len(items),
        source_count=len(sources),
        positions=source_positions,
        round_labels=round_labels,
    )
    return DashboardWeakPointSummary(
        title=latest.title,
        summary=summary,
        suggestion=latest.suggestion or _first_suggestion(ordered_items),
        severity=max((item.severity for item in items), key=_severity_rank),
        occurrence_count=len(items),
        evidence=evidence,
        sources=sources,
        updated_at=latest.updated_at,
    )


def _weak_summary_text(
    occurrence_count: int,
    source_count: int,
    positions: list[str],
    round_labels: list[str],
) -> str:
    position_text = "、".join(positions[:2]) if positions else "最近面试"
    round_text = "、".join(round_labels[:2])
    if occurrence_count > 1:
        suffix = f"，集中在{round_text}" if round_text else ""
        return f"近 {source_count} 条面试记录反复出现{suffix}，建议优先复盘。"
    suffix = f"的{round_text}" if round_text else ""
    return f"来自{position_text}{suffix}记录，说明该能力还需要补强。"


def _first_suggestion(items: list[_WeakPointCandidate]) -> str | None:
    for item in items:
        if item.suggestion:
            return item.suggestion
    return "复盘对应问答，补充背景、行动、结果、技术取舍和量化数据。"


def _round_question_issues(round_id: int, qa_history: list[Any]) -> list[str]:
    return [
        issue
        for item in qa_history
        if item.round_id == round_id
        for issue in _string_list((item.question_evaluation or {}).get("issues"))
    ]


def _round_question_evidence(round_id: int, qa_history: list[Any]) -> list[str]:
    return [
        evidence
        for item in qa_history
        if item.round_id == round_id
        for evidence in _string_list((item.question_evaluation or {}).get("evidence"))
    ]


def _round_follow_up_directions(round_id: int, qa_history: list[Any]) -> list[str]:
    return [
        str((item.question_evaluation or {}).get("follow_up_direction"))
        for item in qa_history
        if item.round_id == round_id and (item.question_evaluation or {}).get("follow_up_direction")
    ]


def _weak_point_key(value: str) -> str:
    return "".join(value.strip().lower().split())


def _severity_from_score(score: int | None) -> str:
    if score is None or score < 60:
        return "high"
    if score < 75:
        return "medium"
    return "low"


def _severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)


def _dedupe_sources(sources: list[DashboardWeakPointSource]) -> list[DashboardWeakPointSource]:
    result: list[DashboardWeakPointSource] = []
    seen: set[tuple[int, str | None]] = set()
    for source in sources:
        key = (source.interview_id, source.round_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _round_label(round_type: str | None) -> str:
    return {
        "resume": "简历面",
        "technical": "技术面",
        "manager": "主管面",
        "hr": "HR 面",
    }.get(str(round_type or ""), str(round_type or ""))


def _activity_sort_key(record: HistoryInterviewRecord) -> tuple[object, int]:
    return (
        record.last_active_at
        or record.ended_at
        or record.started_at
        or record.created_at,
        record.id,
    )


def _score_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return max(0, min(value, 100))
    if isinstance(value, float):
        return max(0, min(round(value), 100))
    return None


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
