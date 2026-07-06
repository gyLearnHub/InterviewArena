from __future__ import annotations

from typing import Any

from app.evolution.code_patch import build_backend_patch_candidate
from app.evolution.risk_classifier import can_auto_apply_candidate, classify_risk


def generate_candidates_from_signal(signal: Any) -> list[dict[str, Any]]:
    signal_dict = _as_dict(signal)
    metrics = dict(signal_dict.get("metrics") or {})
    harness_summary = dict(metrics.get("harness_summary") or {})
    reason_codes = set(metrics.get("trigger_reason_codes") or [])
    candidates: list[dict[str, Any]] = []
    if signal_dict.get("hard_trigger") or harness_summary.get("failed_hard_rules", 0) > 0:
        candidates.append(
            _candidate(
                candidate_type="harness_rule_candidate",
                target_artifact_key="harness_eval_config",
                proposal={
                    "action": "manual_review_harness_failure",
                    "reason": "Harness hard rule or execution failure detected.",
                },
                diff={"draft": "manual review required before changing Harness rules"},
                impact_scope={"interview_id": signal_dict.get("interview_id")},
                root_cause={
                    "category": "harness_failure",
                    "evidence": harness_summary,
                },
            )
        )
    if _has_any(
        reason_codes,
        {
            "interface_degradation",
            "interface_degradation_blocked",
            "harness_trace_failed",
            "harness_status_failed",
        },
    ):
        candidates.append(
            _strip_run_id(
                build_backend_patch_candidate(
                    run_id=0,
                    target_artifact_key="backend/harness_runtime_guard",
                    patch_draft=(
                        "Draft: add a bounded fallback/null guard around the failing Harness "
                        "runtime path and preserve the existing API response contract."
                    ),
                    root_cause={
                        "category": "runtime_stability",
                        "reason_codes": sorted(reason_codes),
                        "harness_summary": harness_summary,
                    },
                    impact_scope={
                        "scope": "backend_draft_only",
                        "interview_id": signal_dict.get("interview_id"),
                    },
                )
            )
        )
    if "llm_output_format_error" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="prompt",
                target_artifact_key="structured_output_guardrails",
                proposal={
                    "action": "strengthen_llm_output_format",
                    "reason": "LLM 输出格式错误导致解析或校验失败。",
                    "validation_plan": [
                        "json_output_replay",
                        "hard_rule_check",
                        "api_contract_check",
                    ],
                    "prompt_hint": "回答必须只输出可解析 JSON，不附加解释性文本。",
                },
                diff={"prompt_hint": "strict JSON-only output guardrail"},
                impact_scope={"scope": "llm_output_parsing"},
                root_cause={
                    "category": "llm_output_format_error",
                    "metrics": dict(metrics.get("harness_quality") or {}),
                },
            )
        )
    if _has_any(reason_codes, {"empty_answer_high_score", "scoring_missing_evidence"}):
        candidates.append(
            _candidate(
                candidate_type="scoring_config",
                target_artifact_key="scoring_evidence_guardrails",
                proposal={
                    "action": "manual_review_scoring_evidence",
                    "reason": "评分可信度触发：空答高分或评分缺少证据。",
                    "validation_plan": [
                        "check_empty_answer_high_score",
                        "check_scoring_evidence_presence",
                        "compare_score_distribution",
                    ],
                },
                diff={
                    "draft": "require explicit answer evidence before high-score conclusions",
                    "api_contract": "unchanged",
                },
                impact_scope={"scope": "scoring", "interview_id": signal_dict.get("interview_id")},
                root_cause={
                    "category": "scoring_trust",
                    "metrics": dict(metrics.get("scoring_evidence") or {}),
                },
            )
        )
    if "report_structure_missing" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="report_template",
                target_artifact_key="final_report_structure",
                proposal={
                    "action": "require_complete_report_sections",
                    "reason": "报告结构缺失，无法满足完整评分报告输出。",
                    "validation_plan": ["report_section_check", "compare_report_quality"],
                    "report_appendix": "报告必须包含优势、短板、能力分析、岗位匹配和最终结论。",
                },
                diff={"report_appendix": "require complete report section coverage"},
                impact_scope={"scope": "report_generation"},
                root_cause={
                    "category": "report_structure_missing",
                    "metrics": dict(metrics.get("report_quality") or {}),
                },
            )
        )
    if _has_any(reason_codes, {"question_repeat", "question_similarity_high"}):
        candidates.append(
            _candidate(
                candidate_type="prompt",
                target_artifact_key="round_question_generation",
                proposal={
                    "action": "strengthen_question_deduplication",
                    "reason": "问题重复或相似度过高。",
                    "validation_plan": ["compare_repeat_rate", "harness_replay"],
                    "prompt_hint": "生成新问题前显式检查已问问题，避免语义重复。",
                },
                diff={"prompt_hint": "avoid questions that duplicate prior question intent"},
                impact_scope={"scope": "question_generation"},
                root_cause={
                    "category": "question_repetition",
                    "metrics": dict(metrics.get("question_quality") or {}),
                },
            )
        )
    if "job_match_low" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="prompt",
                target_artifact_key="round_question_generation",
                proposal={
                    "action": "increase_job_alignment",
                    "reason": "问题与岗位、JD 或简历匹配度不足。",
                    "validation_plan": ["compare_job_match", "harness_replay"],
                    "prompt_hint": "每个主问题必须绑定岗位目标、JD 关键词或简历证据之一。",
                },
                diff={"prompt_hint": "anchor each question to job/JD/resume evidence"},
                impact_scope={"scope": "question_generation"},
                root_cause={
                    "category": "job_match_low",
                    "metrics": dict(metrics.get("job_match") or {}),
                },
            )
        )
    if "difficulty_anomaly" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="flow_config",
                target_artifact_key="interview_rounds",
                proposal={
                    "action": "manual_review_difficulty_distribution",
                    "reason": "难度分布或评分方差异常。",
                    "validation_plan": ["compare_score_distribution", "latest_50_regression"],
                },
                diff={"config_review": "review round question limits and difficulty mix"},
                impact_scope={"scope": "interview_flow"},
                root_cause={
                    "category": "difficulty_anomaly",
                    "metrics": dict(metrics.get("difficulty") or {}),
                },
            )
        )
    if "follow_up_quality_low" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="prompt",
                target_artifact_key="round_question_generation",
                proposal={
                    "action": "strengthen_follow_up_policy",
                    "reason": "追问比例或追问质量不足。",
                    "validation_plan": ["compare_follow_up_quality", "harness_replay"],
                    "prompt_hint": "当回答包含项目、取舍或结果时，优先追问证据和边界条件。",
                },
                diff={"prompt_hint": "ask evidence-focused follow-ups after substantial answers"},
                impact_scope={"scope": "follow_up_generation"},
                root_cause={
                    "category": "follow_up_quality",
                    "metrics": dict(metrics.get("follow_up_quality") or {}),
                },
            )
        )
    if _has_any(
        reason_codes,
        {
            "candidate_dropoff",
            "long_no_response",
            "user_or_developer_thumbs_down",
            "interface_degradation_blocked",
        },
    ):
        candidates.append(
            _candidate(
                candidate_type="frontend_suggestion",
                target_artifact_key="frontend/interview_flow_state",
                proposal={
                    "action": "draft_frontend_recovery_and_feedback_patch",
                    "reason": "用户行为或反馈显示前端状态、等待或恢复体验需要人工检查。",
                    "validation_plan": [
                        "manual_frontend_review",
                        "playwright_state_check",
                        "no_auto_apply",
                    ],
                    "will_modify_files": False,
                },
                diff={
                    "patch_draft": (
                        "Draft only: add clearer loading, retry, no-response and recovery states "
                        "for the interview flow without changing API contracts."
                    ),
                    "auto_apply": False,
                },
                impact_scope={"scope": "frontend_draft_only"},
                root_cause={
                    "category": "frontend_user_experience",
                    "reason_codes": sorted(reason_codes),
                    "metrics": {
                        "behavior": dict(metrics.get("behavior") or {}),
                        "harness_quality": dict(metrics.get("harness_quality") or {}),
                    },
                },
            )
        )
    if "agent_overreach" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="harness_rule_candidate",
                target_artifact_key="agent_boundary_rules",
                proposal={
                    "action": "manual_review_agent_boundary",
                    "reason": "Agent 越权属于职责边界高风险问题，只能生成候选和影响分析。",
                    "validation_plan": [
                        "agent_boundary_review",
                        "latest_50_regression",
                        "manual_approval_required",
                    ],
                },
                diff={"draft": "manual review required before changing agent boundary rules"},
                impact_scope={"scope": "agent_boundary"},
                root_cause={
                    "category": "agent_overreach",
                    "metrics": dict(metrics.get("harness_quality") or {}),
                },
            )
        )
    reliability = metrics.get("report_reliability_status")
    if reliability and reliability != "normal" or "report_vague" in reason_codes:
        candidates.append(
            _candidate(
                candidate_type="report_template",
                target_artifact_key="final_report_reliability",
                proposal={
                    "action": "strengthen_reference_note",
                    "reason": "报告可靠性降级或报告内容空泛。",
                    "validation_plan": ["compare_report_quality", "harness_replay"],
                },
                diff={"add_guardrail": "surface reliability evidence in final report prompts"},
                impact_scope={"scope": "report_generation"},
                root_cause={
                    "category": "report_quality",
                    "status": reliability,
                    "metrics": dict(metrics.get("report_quality") or {}),
                },
            )
        )
    if int(metrics.get("score") or 0) < 60:
        candidates.append(
            _candidate(
                candidate_type="prompt",
                target_artifact_key="round_question_generation",
                proposal={
                    "action": "increase_evidence_seeking",
                    "reason": "Low score interview should collect clearer job-related evidence.",
                    "validation_plan": ["compare_report_quality", "compare_score_distribution"],
                },
                diff={"prompt_hint": "ask for concrete project evidence and tradeoffs"},
                impact_scope={"scope": "question_generation"},
                root_cause={"category": "low_score", "score": metrics.get("score")},
            )
        )
    if not candidates and signal_dict.get("threshold_trigger"):
        candidates.append(
            _candidate(
                candidate_type="business_config",
                target_artifact_key="quality_thresholds",
                proposal={
                    "action": "inspect_threshold",
                    "reason": (
                        "Threshold trigger was raised but no specific root cause was isolated."
                    ),
                },
                diff={"config_review": "no automatic behavior change"},
                impact_scope={"scope": "quality_monitoring"},
                root_cause={"category": "insufficient_evidence"},
            )
        )
    return candidates


def _candidate(
    *,
    candidate_type: str,
    target_artifact_key: str,
    proposal: dict[str, Any],
    diff: dict[str, Any],
    impact_scope: dict[str, Any],
    root_cause: dict[str, Any],
) -> dict[str, Any]:
    risk_level = classify_risk(candidate_type=candidate_type, proposal=proposal, diff=diff)
    return {
        "candidate_type": candidate_type,
        "target_artifact_key": target_artifact_key,
        "risk_level": risk_level,
        "status": "pending_validation"
        if can_auto_apply_candidate(candidate_type, risk_level)
        else "waiting_approval",
        "proposal": proposal,
        "diff": diff,
        "impact_scope": impact_scope,
        "root_cause": root_cause,
        "approval_status": "not_required"
        if can_auto_apply_candidate(candidate_type, risk_level)
        else "pending",
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _has_any(values: set[str], expected: set[str]) -> bool:
    return bool(values & expected)


def _strip_run_id(payload: dict[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    value.pop("run_id", None)
    return value
