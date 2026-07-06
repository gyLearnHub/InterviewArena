from __future__ import annotations

import math
import re
from typing import Any

from app.evolution.analyzer import analyze_run
from app.evolution.triggers import create_runs_for_quality_signal
from app.repositories.evolution import EvolutionRepository
from app.repositories.interviews import (
    FeedbackReportRecord,
    InterviewRecord,
    InterviewRoundRecord,
    QARecord,
)


def record_interview_completion_quality_signal(
    *,
    repository: Any,
    interview: InterviewRecord,
    rounds: list[InterviewRoundRecord],
    qa_history: list[QARecord],
    report: FeedbackReportRecord,
    harness_summary: dict[str, Any] | None = None,
) -> Any:
    evolution_repository = _evolution_repository(repository)
    if evolution_repository is None:
        return None
    summary = harness_summary
    if summary is None:
        summary = evolution_repository.get_interview_harness_summary(interview.id)
    payload = build_interview_completion_quality_signal(
        interview=interview,
        rounds=rounds,
        qa_history=qa_history,
        report=report,
        harness_summary=summary,
    )
    create_signal = getattr(
        evolution_repository,
        "create_quality_signal_idempotent",
        evolution_repository.create_quality_signal,
    )
    signal = create_signal(**payload)
    _run_follow_up(repository=evolution_repository, signal=signal)
    return signal


def build_interview_completion_quality_signal(
    *,
    interview: InterviewRecord,
    rounds: list[InterviewRoundRecord],
    qa_history: list[QARecord],
    report: FeedbackReportRecord,
    harness_summary: dict[str, Any],
) -> dict[str, Any]:
    answered_count = sum(1 for qa in qa_history if qa.answer)
    active_count = sum(1 for qa in qa_history if qa.question_status == "active")
    inactive_count = max(0, len(qa_history) - active_count)
    completed_round_count = sum(
        1 for item in rounds if item.status in {"completed", "finished_early"}
    )
    failed_hard_rules = int(harness_summary.get("failed_hard_rules") or 0)
    failed_traces = int(harness_summary.get("failed_traces") or 0)
    harness_metrics = _harness_quality_metrics(harness_summary)
    question_metrics = _question_quality_metrics(qa_history)
    match_metrics = _job_match_metrics(interview, qa_history)
    difficulty_metrics = _difficulty_metrics(rounds, report.score)
    follow_up_metrics = _follow_up_metrics(qa_history)
    report_metrics = _report_quality_metrics(report)
    scoring_metrics = _scoring_evidence_metrics(rounds, qa_history, report)
    behavior_metrics = _behavior_metrics(
        interview=interview,
        qa_history=qa_history,
        answered_count=answered_count,
        active_count=active_count,
        inactive_count=inactive_count,
        completed_round_count=completed_round_count,
        round_count=len(rounds),
    )
    hard_reason_codes: list[str] = []
    threshold_reason_codes: list[str] = []
    if failed_hard_rules > 0:
        hard_reason_codes.append("harness_hard_rule_failed")
    if failed_traces > 0:
        hard_reason_codes.append("harness_trace_failed")
    if interview.harness_status == "failed":
        hard_reason_codes.append("harness_status_failed")
    if harness_metrics["llm_output_format_error_count"] > 0:
        hard_reason_codes.append("llm_output_format_error")
    if harness_metrics["blocking_degradation_count"] > 0:
        hard_reason_codes.append("interface_degradation_blocked")
    if harness_metrics["negative_feedback_count"] > 0:
        hard_reason_codes.append("user_or_developer_thumbs_down")
    if harness_metrics["agent_overreach_count"] > 0:
        hard_reason_codes.append("agent_overreach")
    if scoring_metrics["empty_answer_high_score"]:
        hard_reason_codes.append("empty_answer_high_score")
    if scoring_metrics["missing_scoring_evidence"]:
        hard_reason_codes.append("scoring_missing_evidence")
    if report_metrics["structure_missing"]:
        hard_reason_codes.append("report_structure_missing")
    if interview.had_degradation:
        threshold_reason_codes.append("interface_degradation")
    if harness_metrics["degradation_count"] > 0:
        threshold_reason_codes.append("interface_degradation")
    if report.report_reliability_status != "normal":
        threshold_reason_codes.append("report_reliability_degraded")
    if report.score < 60:
        threshold_reason_codes.append("low_score")
    if question_metrics["repeat_count"] > 0:
        threshold_reason_codes.append("question_repeat")
    if question_metrics["max_similarity"] >= 0.82:
        threshold_reason_codes.append("question_similarity_high")
    if match_metrics["match_score"] < 0.25:
        threshold_reason_codes.append("job_match_low")
    if difficulty_metrics["difficulty_anomaly"]:
        threshold_reason_codes.append("difficulty_anomaly")
    if follow_up_metrics["quality_score"] < 0.4:
        threshold_reason_codes.append("follow_up_quality_low")
    if report_metrics["vagueness_score"] >= 0.55:
        threshold_reason_codes.append("report_vague")
    if behavior_metrics["candidate_dropoff"]:
        threshold_reason_codes.append("candidate_dropoff")
    if behavior_metrics["long_no_response"]:
        threshold_reason_codes.append("long_no_response")
    hard_trigger = bool(hard_reason_codes)
    threshold_trigger = bool(threshold_reason_codes)
    severity = _severity(
        hard_trigger=hard_trigger,
        threshold_trigger=threshold_trigger,
        score=report.score,
    )
    return {
        "user_id": interview.user_id,
        "interview_id": interview.id,
        "version_bundle_id": interview.version_bundle_id,
        "job_family": _job_family(interview.target_position),
        "signal_type": "interview_completed",
        "severity": severity,
        "metrics": {
            "score": report.score,
            "question_count": interview.question_count,
            "active_question_count": active_count,
            "answered_count": answered_count,
            "inactive_question_count": inactive_count,
            "round_count": len(rounds),
            "completed_round_count": completed_round_count,
            "report_reliability_status": report.report_reliability_status,
            "harness_summary": harness_summary,
            "harness_quality": harness_metrics,
            "question_quality": question_metrics,
            "job_match": match_metrics,
            "difficulty": difficulty_metrics,
            "follow_up_quality": follow_up_metrics,
            "report_quality": report_metrics,
            "scoring_evidence": scoring_metrics,
            "behavior": behavior_metrics,
            "hard_reason_codes": hard_reason_codes,
            "threshold_reason_codes": threshold_reason_codes,
            "trigger_reason_codes": [*hard_reason_codes, *threshold_reason_codes],
        },
        "hard_trigger": hard_trigger,
        "threshold_trigger": threshold_trigger,
        "source_refs": {
            "interview_id": interview.id,
            "version_bundle_id": interview.version_bundle_id,
            "feedback_report": {"interview_id": report.interview_id},
            "harness": harness_summary,
        },
    }


def _severity(*, hard_trigger: bool, threshold_trigger: bool, score: int) -> str:
    if hard_trigger:
        return "critical"
    if threshold_trigger or score < 60:
        return "warning"
    return "info"


def _job_family(target_position: str) -> str:
    return target_position.strip()[:128] or "unknown"


def _question_quality_metrics(qa_history: list[QARecord]) -> dict[str, Any]:
    questions = [
        _normalize_text(qa.question)
        for qa in qa_history
        if qa.question_status == "active"
    ]
    non_empty = [item for item in questions if item]
    repeat_count = max(0, len(non_empty) - len(set(non_empty)))
    max_similarity = 0.0
    for index, question in enumerate(non_empty):
        for other in non_empty[index + 1 :]:
            max_similarity = max(max_similarity, _similarity(question, other))
    repeat_rate = repeat_count / len(non_empty) if non_empty else 0.0
    return {
        "question_count": len(non_empty),
        "repeat_count": repeat_count,
        "repeat_rate": round(repeat_rate, 4),
        "max_similarity": round(max_similarity, 4),
    }


def _job_match_metrics(interview: InterviewRecord, qa_history: list[QARecord]) -> dict[str, Any]:
    source_terms = _keywords(
        " ".join(
            item
            for item in [
                interview.target_position,
                interview.job_description or "",
            ]
            if item
        )
    )
    if not source_terms:
        return {"match_score": 1.0, "matched_terms": [], "source_term_count": 0}
    question_text = " ".join(_normalize_text(qa.question) for qa in qa_history)
    matched_terms = sorted(term for term in source_terms if term in question_text)
    score = len(matched_terms) / len(source_terms)
    return {
        "match_score": round(score, 4),
        "matched_terms": matched_terms[:20],
        "source_term_count": len(source_terms),
    }


def _difficulty_metrics(rounds: list[InterviewRoundRecord], score: int) -> dict[str, Any]:
    scored = [item.score for item in rounds if item.score is not None]
    round_scores = [int(item) for item in scored]
    average_score = sum(round_scores) / len(round_scores) if round_scores else float(score)
    score_variance = (
        sum((item - average_score) ** 2 for item in round_scores) / len(round_scores)
        if round_scores
        else 0.0
    )
    total_min_questions = sum(
        item.min_total_questions for item in rounds if item.status != "skipped"
    )
    total_max_questions = sum(
        item.max_total_questions for item in rounds if item.status != "skipped"
    )
    difficulty_anomaly = (
        average_score >= 92
        or average_score <= 45
        or score_variance >= 500
        or total_min_questions > total_max_questions
    )
    return {
        "average_score": round(average_score, 2),
        "score_variance": round(score_variance, 2),
        "expected_min_questions": total_min_questions,
        "expected_max_questions": total_max_questions,
        "difficulty_anomaly": difficulty_anomaly,
    }


def _follow_up_metrics(qa_history: list[QARecord]) -> dict[str, Any]:
    main_count = sum(1 for qa in qa_history if qa.question_kind == "main")
    follow_up_count = sum(1 for qa in qa_history if qa.question_kind == "follow_up")
    answered_main = [
        qa
        for qa in qa_history
        if qa.question_kind == "main" and qa.answer and len(qa.answer.strip()) >= 20
    ]
    ratio = follow_up_count / max(1, main_count)
    quality_score = 1.0
    if answered_main and follow_up_count == 0:
        quality_score = 0.0
    elif main_count:
        quality_score = min(1.0, ratio * 2.0)
    return {
        "main_count": main_count,
        "follow_up_count": follow_up_count,
        "follow_up_ratio": round(ratio, 4),
        "quality_score": round(quality_score, 4),
    }


def _report_quality_metrics(report: FeedbackReportRecord) -> dict[str, Any]:
    report_text = " ".join(
        [
            " ".join(report.weaknesses or []),
            " ".join(report.suggestions or []),
            " ".join(report.strengths or []),
            " ".join(report.ability_analysis or []),
            report.job_match or "",
            report.final_conclusion or "",
        ]
    )
    normalized = _normalize_text(report_text)
    generic_hits = sum(
        1
        for phrase in (
            "继续提升",
            "加强学习",
            "综合能力",
            "部分能力",
            "需要进一步",
            "建议复盘",
            "结合实际",
        )
        if phrase in report_text
    )
    length_penalty = 1.0 if len(normalized) < 80 else 0.0
    vagueness_score = min(1.0, generic_hits * 0.18 + length_penalty * 0.45)
    missing_sections = _missing_report_sections(report)
    return {
        "text_length": len(normalized),
        "generic_phrase_count": generic_hits,
        "vagueness_score": round(vagueness_score, 4),
        "missing_sections": missing_sections,
        "structure_missing": bool(missing_sections),
    }


def _missing_report_sections(report: FeedbackReportRecord) -> list[str]:
    required_sections = {
        "weaknesses": report.weaknesses,
        "suggestions": report.suggestions,
        "strengths": report.strengths,
        "ability_analysis": report.ability_analysis,
        "job_match": report.job_match,
        "final_conclusion": report.final_conclusion,
    }
    missing: list[str] = []
    for section, value in required_sections.items():
        if isinstance(value, list):
            if not any(str(item).strip() for item in value):
                missing.append(section)
        elif value is None or not str(value).strip():
            missing.append(section)
    return missing


def _scoring_evidence_metrics(
    rounds: list[InterviewRoundRecord],
    qa_history: list[QARecord],
    report: FeedbackReportRecord,
) -> dict[str, Any]:
    short_answer_count = sum(
        1
        for qa in qa_history
        if qa.answer is not None and len(qa.answer.strip()) <= 3
    )
    empty_answer_high_score = short_answer_count > 0 and report.score >= 75
    evidence_round_count = 0
    for round_record in rounds:
        summary = round_record.summary or {}
        if any(key in summary for key in ("evidence", "evidence_refs", "strengths", "weaknesses")):
            evidence_round_count += 1
    missing_scoring_evidence = bool(rounds) and evidence_round_count == 0 and report.score >= 70
    return {
        "short_answer_count": short_answer_count,
        "empty_answer_high_score": empty_answer_high_score,
        "evidence_round_count": evidence_round_count,
        "missing_scoring_evidence": missing_scoring_evidence,
    }


def _behavior_metrics(
    *,
    interview: InterviewRecord,
    qa_history: list[QARecord],
    answered_count: int,
    active_count: int,
    inactive_count: int,
    completed_round_count: int,
    round_count: int,
) -> dict[str, Any]:
    unanswered_active = max(0, active_count - answered_count)
    candidate_dropoff = (
        interview.overall_status in {"cancelled", "abandoned"}
        or completed_round_count < round_count
        and (unanswered_active > 0 or inactive_count > 0)
    )
    long_no_response = any(
        qa.answer is None and qa.question_status == "active" for qa in qa_history
    )
    return {
        "answered_count": answered_count,
        "unanswered_active_count": unanswered_active,
        "inactive_question_count": inactive_count,
        "candidate_dropoff": candidate_dropoff,
        "long_no_response": long_no_response,
    }


def _harness_quality_metrics(harness_summary: dict[str, Any]) -> dict[str, int]:
    return {
        "llm_output_format_error_count": _summary_count(
            harness_summary,
            (
                "llm_output_format_error_count",
                "output_format_error_count",
                "json_parse_error_count",
                "validation_failed_trace_count",
                "schema_validation_error_count",
            ),
        ),
        "degradation_count": _summary_count(
            harness_summary,
            ("degradation_count", "degraded_trace_count", "api_degradation_count"),
        ),
        "blocking_degradation_count": _summary_count(
            harness_summary,
            (
                "blocking_degradation_count",
                "api_degradation_blocked_count",
                "interface_degradation_blocked_count",
            ),
        ),
        "negative_feedback_count": _summary_count(
            harness_summary,
            (
                "negative_feedback_count",
                "thumbs_down_count",
                "user_thumbs_down_count",
                "developer_thumbs_down_count",
            ),
        ),
        "agent_overreach_count": _summary_count(
            harness_summary,
            ("agent_overreach_count", "agent_boundary_violation_count"),
        ),
    }


def _summary_count(summary: dict[str, Any], keys: tuple[str, ...]) -> int:
    count = 0
    for key in keys:
        try:
            count += int(summary.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return count


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value.casefold())


def _keywords(value: str) -> set[str]:
    normalized = value.casefold()
    ascii_terms = {term for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]{1,}", normalized)}
    cjk_terms = {term for term in re.findall(r"[\u4e00-\u9fff]{2,}", normalized)}
    compact_cjk: set[str] = set()
    for term in cjk_terms:
        if len(term) <= 6:
            compact_cjk.add(term)
        else:
            compact_cjk.update(term[index : index + 4] for index in range(0, len(term) - 3))
    return {term for term in {*ascii_terms, *compact_cjk} if len(term) >= 2}


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_grams = _bigrams(left)
    right_grams = _bigrams(right)
    if not left_grams or not right_grams:
        return 0.0
    overlap = len(left_grams & right_grams)
    denominator = math.sqrt(len(left_grams) * len(right_grams))
    return overlap / denominator if denominator else 0.0


def _bigrams(value: str) -> set[str]:
    if len(value) <= 2:
        return {value}
    return {value[index : index + 2] for index in range(len(value) - 1)}


def _evolution_repository(repository: Any) -> Any | None:
    if isinstance(repository, EvolutionRepository):
        return repository
    if hasattr(repository, "create_quality_signal"):
        return repository
    connection = getattr(repository, "connection", None)
    if connection is None:
        return None
    return EvolutionRepository(connection)


def _run_follow_up(*, repository: Any, signal: Any) -> None:
    try:
        runs = create_runs_for_quality_signal(repository, signal)
        for run in runs:
            run_id = _run_id(run)
            if run_id is not None:
                analyze_run(repository, run_id, signals=[signal])
    except Exception:
        return


def _run_id(run: Any) -> int | None:
    if isinstance(run, dict):
        value = run.get("id")
    else:
        value = getattr(run, "id", None)
    return int(value) if value is not None else None
