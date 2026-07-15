from __future__ import annotations

from typing import Any

from app.skills.types import JSONDict, SkillContext, SkillDefinition, SkillSelection
from app.skills.utils import clip_text, current_answer, current_question, resume_skills


def select_skills(
    *,
    context: SkillContext,
    candidates: list[SkillDefinition],
    llm_client: Any,
    max_skills: int = 2,
) -> list[SkillSelection]:
    if not candidates or max_skills <= 0:
        return []

    llm_selection = _select_with_llm(
        context=context,
        candidates=candidates,
        llm_client=llm_client,
        max_skills=max_skills,
    )
    if llm_selection is not None:
        return llm_selection[:max_skills]
    return _select_by_rule(
        context=context, candidates=candidates, max_skills=max_skills
    )


def _select_with_llm(
    *,
    context: SkillContext,
    candidates: list[SkillDefinition],
    llm_client: Any,
    max_skills: int,
) -> list[SkillSelection] | None:
    generate_json = getattr(llm_client, "generate_json", None)
    if not callable(generate_json):
        return None

    candidate_names = {candidate.name for candidate in candidates}
    payload = {
        "round_type": context.round_type,
        "stage": context.stage,
        "question_kind": context.question_kind,
        "max_skills": max_skills,
        "context_summary": _selection_context_summary(context),
        "candidate_skills": [
            {
                "name": candidate.name,
                "description": candidate.description,
                "category": candidate.category,
                "llm_enhanced": candidate.llm_enhanced,
            }
            for candidate in candidates
        ],
    }
    try:
        raw = generate_json(_SELECTION_PROMPT, payload)
    except Exception:
        return None
    selected = raw.get("selected_skills")
    if not isinstance(selected, list):
        return None
    results: list[SkillSelection] = []
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name not in candidate_names or name in seen:
            continue
        reason = clip_text(item.get("reason") or "llm_selected", 160)
        results.append(SkillSelection(name=name, reason=reason, source="llm"))
        seen.add(name)
        if len(results) >= max_skills:
            break
    return results


def _select_by_rule(
    *,
    context: SkillContext,
    candidates: list[SkillDefinition],
    max_skills: int,
) -> list[SkillSelection]:
    candidate_by_name = {candidate.name: candidate for candidate in candidates}
    preferred_names = _preferred_skill_names(context)
    selected: list[SkillSelection] = []
    seen: set[str] = set()
    for name in preferred_names:
        if name not in candidate_by_name or name in seen:
            continue
        selected.append(
            SkillSelection(
                name=name,
                reason="rule_selected_for_stage_and_round",
                source="rule",
            )
        )
        seen.add(name)
        if len(selected) >= max_skills:
            return selected

    for candidate in candidates:
        if candidate.name in seen:
            continue
        selected.append(
            SkillSelection(
                name=candidate.name,
                reason="rule_selected_candidate_fallback",
                source="rule",
            )
        )
        if len(selected) >= max_skills:
            break
    return selected


def _preferred_skill_names(context: SkillContext) -> list[str]:
    if context.stage == "pre_question":
        by_round = {
            "resume": "resume_risk_probe",
            "technical": "technical_gap_mapper",
            "manager": "management_signal_probe",
            "hr": "hr_motivation_probe",
        }
        return [
            "context_summary",
            by_round.get(context.round_type, "risk_signal_detector"),
        ]

    answer = current_answer(context)
    if len(answer) < 80:
        common = "answer_quality_probe"
    elif any(term in answer for term in ("不清楚", "可能", "大概", "忘了")):
        common = "risk_signal_detector"
    else:
        common = "followup_question_suggester"
    by_round = {
        "resume": "resume_project_deepener",
        "technical": "technical_depth_probe",
        "manager": "impact_result_probe",
        "hr": "stability_risk_probe",
    }
    return [common, by_round.get(context.round_type, "risk_signal_detector")]


def _selection_context_summary(context: SkillContext) -> JSONDict:
    return {
        "target_position": clip_text(context.target_position, 80),
        "job_description": clip_text(context.job_description, 120),
        "question": clip_text(current_question(context), 120),
        "answer": clip_text(current_answer(context), 160),
        "qa_count": len(context.qa_history),
        "resume_skill_count": len(resume_skills(context.resume)),
        "memory_count": len(context.effective_memories),
    }


_SELECTION_PROMPT = (
    "你是面试 Agent 的 skill 选择器。只返回 JSON，不要解释。"
    "你只能从 candidate_skills 中选择，最多选择 max_skills 个。"
    "skill 只做确定性分析，不能生成大段自然语言。"
    '返回格式：{"selected_skills":[{"name":"...","reason":"..."}]}。'
    '如果没有必要调用，返回 {"selected_skills":[]}。'
)
