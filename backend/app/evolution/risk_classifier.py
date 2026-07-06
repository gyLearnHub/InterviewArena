from __future__ import annotations

from typing import Any

AUTO_APPLY_TYPES = {"prompt", "flow_config", "report_template", "business_config"}
NEVER_AUTO_APPLY_TYPES = {"frontend_suggestion", "backend_patch", "harness_rule_candidate"}
HIGH_RISK_KEYWORDS = {
    "database",
    "migration",
    "schema",
    "permission",
    "auth",
    "api_contract",
    "harness_rule",
    "frontend",
    "delete",
}


def classify_risk(
    *,
    candidate_type: str,
    proposal: dict[str, Any] | None = None,
    diff: dict[str, Any] | None = None,
) -> str:
    payload = f"{candidate_type} {proposal or {}} {diff or {}}".casefold()
    if candidate_type == "frontend_suggestion":
        return "high"
    if candidate_type == "harness_rule_candidate":
        return "high"
    if candidate_type == "backend_patch":
        return "medium"
    if candidate_type == "scoring_config":
        return "high"
    if candidate_type == "flow_config" and _contains_any(
        payload,
        {"manual_review", "difficulty", "round_limits", "question_count"},
    ):
        return "medium"
    if any(keyword in payload for keyword in HIGH_RISK_KEYWORDS):
        return "high"
    if candidate_type in AUTO_APPLY_TYPES:
        return "low"
    return "medium"


def can_auto_apply_candidate(candidate_type: str, risk_level: str) -> bool:
    return risk_level == "low" and candidate_type in AUTO_APPLY_TYPES


def can_apply_after_manual_approval(candidate_type: str, risk_level: str) -> bool:
    return risk_level in {"low", "medium"} and candidate_type in AUTO_APPLY_TYPES


def ensure_no_forbidden_auto_apply(candidate: Any) -> None:
    candidate_type = getattr(candidate, "candidate_type", None)
    status = getattr(candidate, "status", None)
    if candidate_type in NEVER_AUTO_APPLY_TYPES and status == "auto_applied":
        raise ValueError(f"{candidate_type} candidates cannot be auto_applied")


def _contains_any(payload: str, keywords: set[str]) -> bool:
    return any(keyword in payload for keyword in keywords)
