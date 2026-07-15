from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.skills.types import JSONDict, SkillContext, SkillSignal, SkillSuggestion

MAX_TEXT_SUMMARY_LENGTH = 180


def clamp_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def clip_text(value: Any, limit: int = MAX_TEXT_SUMMARY_LENGTH) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def context_text(context: SkillContext, *, include_resume: bool = False) -> str:
    chunks: list[str] = [
        context.target_position,
        context.job_description,
        context.previous_answer or "",
    ]
    for item in context.qa_history[-4:]:
        chunks.append(str(item.get("question") or ""))
        chunks.append(str(item.get("answer") or ""))
    if include_resume:
        chunks.append(flatten_resume_text(context.resume))
    return clean_text(" ".join(chunks))


def flatten_resume_text(resume: JSONDict) -> str:
    chunks: list[str] = []
    for key in (
        "basic_info",
        "education",
        "work_experience",
        "project_experience",
        "skills",
        "certificates_awards",
    ):
        chunks.append(_flatten_value(resume.get(key)))
    return clean_text(" ".join(chunks))


def _flatten_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_flatten_value(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_value(item) for item in value)
    return str(value)


def matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized = text.casefold()
    return [term for term in terms if term.casefold() in normalized]


def has_number(text: str) -> bool:
    return bool(re.search(r"\d", text))


def token_count(text: str) -> int:
    cleaned = clean_text(text)
    if not cleaned:
        return 0
    latin_tokens = re.findall(r"[A-Za-z0-9_+#.-]+", cleaned)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", cleaned)
    return len(latin_tokens) + max(1, len(chinese_chars) // 2)


def list_entries(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_entries(value: Any) -> list[JSONDict]:
    return [item for item in list_entries(value) if isinstance(item, dict)]


def resume_skills(resume: JSONDict) -> list[str]:
    raw_skills = list_entries(resume.get("skills"))
    skills: list[str] = []
    for item in raw_skills:
        if isinstance(item, str):
            skills.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("skill") or item.get("title")
            if name:
                skills.append(str(name))
        else:
            skills.append(str(item))
    return [skill for skill in (clean_text(item) for item in skills) if skill]


def latest_qa(context: SkillContext) -> JSONDict | None:
    return context.qa_history[-1] if context.qa_history else None


def current_question(context: SkillContext) -> str:
    item = latest_qa(context)
    return clean_text(item.get("question") if item else "")


def current_answer(context: SkillContext) -> str:
    if context.previous_answer:
        return clean_text(context.previous_answer)
    item = latest_qa(context)
    if item and item.get("answer"):
        return clean_text(item.get("answer"))
    return ""


def input_summary(context: SkillContext) -> JSONDict:
    answer = current_answer(context)
    return {
        "round_type": context.round_type,
        "stage": context.stage,
        "question_kind": context.question_kind,
        "target_position": clip_text(context.target_position, 80),
        "qa_count": len(context.qa_history),
        "answer_length": len(answer),
        "resume_keys": sorted(str(key) for key in context.resume.keys())[:12],
        "memory_count": len(context.effective_memories),
    }


def output_summary(
    *,
    signals: list[SkillSignal],
    suggestions: list[SkillSuggestion],
    confidence: float | None,
    metrics: JSONDict | None = None,
) -> JSONDict:
    return {
        "signal_count": len(signals),
        "suggestion_count": len(suggestions),
        "top_signals": [signal.code for signal in signals[:5]],
        "confidence": confidence,
        "metric_keys": sorted(metrics.keys())[:12] if metrics else [],
    }


def make_signal(code: str, severity: str = "info", **evidence: Any) -> SkillSignal:
    severity_value = severity if severity in {"info", "warning", "risk"} else "info"
    return SkillSignal(
        code=code,
        severity=severity_value,  # type: ignore[arg-type]
        evidence={key: value for key, value in evidence.items() if value is not None},
    )


def make_suggestion(
    code: str,
    target: str,
    priority: str = "medium",
    **evidence: Any,
) -> SkillSuggestion:
    priority_value = priority if priority in {"low", "medium", "high"} else "medium"
    return SkillSuggestion(
        code=code,
        target=target,
        priority=priority_value,  # type: ignore[arg-type]
        evidence={key: value for key, value in evidence.items() if value is not None},
    )


def short_summary(prefix: str, signals: list[SkillSignal], metrics: JSONDict) -> str:
    top = ",".join(signal.code for signal in signals[:3]) or "none"
    return clip_text(
        f"{prefix}; signals={top}; metrics={','.join(sorted(metrics)[:4])}", 160
    )
