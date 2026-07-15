from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.skills.types import (
    JSONDict,
    SkillContext,
    SkillDefinition,
    SkillResult,
    SkillSignal,
    SkillStage,
)
from app.skills.utils import (
    clamp_confidence,
    clean_text,
    context_text,
    current_answer,
    current_question,
    dict_entries,
    has_number,
    make_signal,
    make_suggestion,
    matched_terms,
    resume_skills,
    short_summary,
    token_count,
)

ALL_ROUNDS = ("resume", "technical", "manager", "hr")
ALL_STAGES: tuple[SkillStage, ...] = ("pre_question", "post_answer")

RESULT_TERMS = ("提升", "降低", "增长", "减少", "指标", "数据", "成本", "效率", "用户", "收入", "%")
OWNERSHIP_TERMS = ("我负责", "我主导", "我设计", "我推进", "我实现", "我落地", "负责", "主导")
REASONING_TERMS = ("因为", "所以", "取舍", "权衡", "原因", "方案", "对比", "风险", "边界")
AVOIDANCE_TERMS = ("不太清楚", "忘了", "差不多", "应该是", "可能是", "大概", "不确定")
OVERCLAIM_TERMS = ("全部", "完全", "唯一", "最强", "极大", "彻底", "百分百")
CONTEXT_TERMS = ("背景", "目标", "问题", "需求", "场景", "痛点", "挑战", "瓶颈")
ACTION_DETAIL_TERMS = (
    "设计",
    "实现",
    "优化",
    "排查",
    "定位",
    "拆分",
    "推进",
    "协调",
    "验证",
    "复盘",
    "重构",
    "上线",
)
REFLECTION_TERMS = ("复盘", "改进", "经验", "总结", "学到", "下次", "后来", "之后")
VAGUE_QUALITY_TERMS = (
    "很多",
    "一些",
    "比较",
    "还可以",
    "挺好",
    "之类",
    "等等",
    "基本",
    "差不多",
    "大概",
    "可能",
    "感觉",
)
QUESTION_FOCUS_GROUPS = {
    "result": ("结果", "成果", "指标", "影响", "效果", "收益"),
    "reasoning": ("为什么", "原因", "取舍", "权衡", "选择", "风险"),
    "technical": ("技术", "架构", "数据库", "接口", "性能", "并发", "缓存", "索引"),
    "collaboration": ("协作", "沟通", "团队", "冲突", "推进", "跨团队"),
}
ANSWER_FOCUS_GROUPS = {
    "result": RESULT_TERMS + ("效果", "收益", "上线"),
    "reasoning": REASONING_TERMS,
    "technical": (
        "技术",
        "架构",
        "数据库",
        "接口",
        "性能",
        "并发",
        "缓存",
        "索引",
        "事务",
        "延迟",
    ),
    "collaboration": ("协作", "沟通", "团队", "冲突", "推进", "对齐", "跨团队"),
}
TECHNICAL_DEPTH_GROUPS = {
    "root_cause": ("根因", "原因", "瓶颈", "慢查询", "故障", "问题定位"),
    "mechanism": (
        "原理",
        "源码",
        "复杂度",
        "事务",
        "索引",
        "锁",
        "缓存",
        "队列",
        "并发",
        "一致性",
        "隔离",
    ),
    "validation": (
        "压测",
        "监控",
        "日志",
        "指标",
        "p95",
        "qps",
        "rt",
        "耗时",
        "延迟",
        "错误率",
    ),
    "boundary": ("边界", "降级", "兜底", "异常", "失败", "超时", "重试", "幂等"),
    "tradeoff": REASONING_TERMS + ("替代", "相比", "优缺点", "折中"),
}
PROJECT_COVERAGE_GROUPS = {
    "role": OWNERSHIP_TERMS,
    "action": ACTION_DETAIL_TERMS,
    "result": RESULT_TERMS,
    "technical": ANSWER_FOCUS_GROUPS["technical"],
    "challenge": CONTEXT_TERMS + ("难点", "故障", "瓶颈", "冲突"),
    "tradeoff": REASONING_TERMS,
}
MANAGEMENT_COVERAGE_GROUPS = {
    "goal": ("目标", "里程碑", "需求", "优先级", "范围"),
    "plan": ("拆解", "排期", "计划", "分工", "节奏", "推进"),
    "risk": ("风险", "阻塞", "延期", "依赖", "预案", "兜底"),
    "stakeholder": ("团队", "产品", "设计", "测试", "业务", "跨团队", "相关方"),
    "decision": ("决策", "取舍", "权衡", "对齐", "选择"),
    "review": ("复盘", "总结", "改进", "沉淀"),
    "result": RESULT_TERMS,
}
COLLABORATION_COVERAGE_GROUPS = {
    "conflict": ("冲突", "分歧", "争议", "卡点", "阻塞"),
    "alignment": ("沟通", "协作", "对齐", "同步", "共识"),
    "resolution": ("解决", "协调", "推动", "升级", "拆解", "让步", "确认"),
    "result": RESULT_TERMS + ("上线", "交付", "落地"),
}
MOTIVATION_COVERAGE_GROUPS = {
    "role_alignment": ("岗位", "职责", "业务", "产品", "技术栈", "团队"),
    "career_plan": ("长期", "规划", "发展", "成长", "沉淀", "方向"),
    "value": ("价值", "认可", "兴趣", "喜欢", "成就", "影响"),
    "evidence": ("因为", "之前", "项目", "经历", "负责", "实践"),
}
EXPECTATION_GROUPS = {
    "compensation": ("薪资", "待遇", "base", "奖金", "期望薪资"),
    "location": ("地点", "城市", "通勤", "异地"),
    "remote": ("远程", "居家", "到岗", "现场"),
    "start_time": ("到岗", "入职", "离职", "交接", "时间"),
    "level": ("职级", "级别", "title", "岗位"),
    "team": ("团队", "汇报", "规模", "管理"),
    "workload": ("工作强度", "加班", "节奏", "压力"),
}
STABILITY_POSITIVE_TERMS = ("长期", "稳定", "持续", "沉淀", "成长", "规划", "认可")
STABILITY_REASON_TERMS = ("因为", "原因", "考虑", "希望", "想要", "由于", "所以")


def context_summary(context: SkillContext) -> SkillResult:
    skills = resume_skills(context.resume)
    answer = current_answer(context)
    qa_count = len(context.qa_history)
    metrics = {
        "qa_count": qa_count,
        "answered_count": sum(1 for item in context.qa_history if item.get("answer")),
        "skill_count": len(skills),
        "project_count": len(dict_entries(context.resume.get("project_experience"))),
        "work_count": len(dict_entries(context.resume.get("work_experience"))),
        "answer_tokens": token_count(answer),
        "memory_count": len(context.effective_memories),
    }
    signals: list[SkillSignal] = []
    if qa_count == 0:
        signals.append(make_signal("opening_context", "info"))
    if metrics["answer_tokens"] and metrics["answer_tokens"] < 30:
        signals.append(make_signal("short_current_answer", "warning"))
    if not skills:
        signals.append(make_signal("resume_skills_missing", "warning"))
    suggestions = [
        make_suggestion("use_compact_context", "question_focus", "medium"),
    ]
    confidence = clamp_confidence(
        0.62 + min(0.2, qa_count * 0.02) + min(0.1, len(skills) * 0.01)
    )
    return _result(
        "context_summary", "context metrics", signals, metrics, suggestions, confidence
    )


def answer_quality_probe(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    question = current_question(context)
    answer_tokens = token_count(answer)
    answer_has_number = has_number(answer)
    ownership_terms = matched_terms(answer, OWNERSHIP_TERMS)
    result_terms = matched_terms(answer, RESULT_TERMS)
    reasoning_terms = matched_terms(answer, REASONING_TERMS)
    context_terms = matched_terms(answer, CONTEXT_TERMS)
    action_terms = matched_terms(answer, ACTION_DETAIL_TERMS)
    reflection_terms = matched_terms(answer, REFLECTION_TERMS)
    vague_terms = matched_terms(answer, VAGUE_QUALITY_TERMS)
    semantic_coverage = _semantic_coverage(
        context_terms=context_terms,
        action_terms=action_terms or ownership_terms,
        result_terms=result_terms,
        reasoning_terms=reasoning_terms,
        reflection_terms=reflection_terms,
    )
    missing_question_focus = _missing_question_focus(question, answer)
    metrics = {
        "answer_length": len(answer),
        "answer_tokens": answer_tokens,
        "has_number": answer_has_number,
        "ownership_terms": ownership_terms,
        "result_terms": result_terms,
        "reasoning_terms": reasoning_terms,
        "context_terms": context_terms,
        "action_terms": action_terms,
        "reflection_terms": reflection_terms,
        "vague_terms": vague_terms,
        "semantic_coverage": semantic_coverage,
        "missing_question_focus": missing_question_focus,
    }
    signals: list[SkillSignal] = []
    if context.stage == "post_answer" and answer_tokens < 35:
        signals.append(make_signal("answer_too_short", "warning", tokens=answer_tokens))
    if answer and vague_terms and (len(vague_terms) >= 2 or not answer_has_number):
        signals.append(
            make_signal("vague_or_generic_answer", "warning", terms=vague_terms[:5])
        )
    if missing_question_focus:
        signals.append(
            make_signal(
                "question_focus_unanswered",
                "warning" if len(missing_question_focus) > 1 else "info",
                missing_focus=missing_question_focus,
            )
        )
    if answer and answer_tokens >= 35 and semantic_coverage["covered_count"] < 3:
        signals.append(
            make_signal(
                "low_semantic_coverage",
                "warning",
                missing_dimensions=semantic_coverage["missing"][:4],
            )
        )
    if answer and not answer_has_number and not result_terms:
        signals.append(make_signal("missing_quantified_result", "warning"))
    if answer and not ownership_terms:
        signals.append(make_signal("missing_personal_ownership", "warning"))
    if answer and ownership_terms and not action_terms:
        signals.append(make_signal("missing_action_detail", "warning"))
    if answer and not reasoning_terms:
        signals.append(make_signal("missing_reasoning_or_tradeoff", "info"))
    if answer and answer_tokens >= 35 and not context_terms:
        signals.append(make_signal("missing_context_or_goal", "info"))
    suggestions = [
        make_suggestion("ask_for_action_result", "followup_direction", "high")
        if signals
        else make_suggestion(
            "continue_with_deeper_probe", "followup_direction", "medium"
        )
    ]
    confidence = clamp_confidence(0.55 + min(0.25, answer_tokens / 240))
    return _result(
        "answer_quality_probe",
        "answer quality metrics",
        signals,
        metrics,
        suggestions,
        confidence,
    )


def followup_question_suggester(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    question = current_question(context)
    quality = answer_quality_probe(context)
    signals = [
        make_signal(
            "followup_candidate", "info", question_type=_last_question_type(context)
        ),
    ]
    metrics = {
        "answer_tokens": token_count(answer),
        "question_tokens": token_count(question),
        "quality_signal_codes": [signal.code for signal in quality.signals],
    }
    suggestions = []
    for signal in quality.signals[:3]:
        target = {
            "answer_too_short": "ask_for_concrete_example",
            "vague_or_generic_answer": "ask_for_specific_evidence",
            "question_focus_unanswered": "ask_to_answer_question_focus",
            "low_semantic_coverage": "ask_for_context_action_result",
            "missing_quantified_result": "ask_for_metric_or_impact",
            "missing_personal_ownership": "ask_for_personal_action",
            "missing_action_detail": "ask_for_action_detail",
            "missing_reasoning_or_tradeoff": "ask_for_decision_reason",
            "missing_context_or_goal": "ask_for_context_or_goal",
        }.get(signal.code, "ask_for_evidence")
        suggestions.append(make_suggestion(signal.code, target, "high"))
    if not suggestions:
        suggestions.append(
            make_suggestion(
                "deepen_current_topic", "ask_boundary_or_next_level", "medium"
            )
        )
    confidence = clamp_confidence(0.58 + min(0.18, len(suggestions) * 0.06))
    return _result(
        "followup_question_suggester",
        "followup direction candidates",
        signals,
        metrics,
        suggestions,
        confidence,
    )


def risk_signal_detector(context: SkillContext) -> SkillResult:
    text = context_text(context, include_resume=context.stage == "pre_question")
    avoidance = matched_terms(text, AVOIDANCE_TERMS)
    overclaim = matched_terms(text, OVERCLAIM_TERMS)
    signals: list[SkillSignal] = []
    if avoidance:
        signals.append(
            make_signal("uncertainty_or_avoidance", "risk", terms=avoidance[:5])
        )
    if overclaim:
        signals.append(
            make_signal("possible_overclaim", "warning", terms=overclaim[:5])
        )
    if _repeated_short_answers(context):
        signals.append(make_signal("repeated_short_answers", "warning"))
    metrics = {
        "avoidance_terms": avoidance,
        "overclaim_terms": overclaim,
        "recent_answer_lengths": [
            len(clean_text(item.get("answer")))
            for item in context.qa_history[-4:]
            if item.get("answer")
        ],
    }
    suggestions = [
        make_suggestion("request_verifiable_detail", "followup_direction", "high")
        if signals
        else make_suggestion("no_major_risk_signal", "question_focus", "low")
    ]
    confidence = clamp_confidence(
        0.5 + min(0.25, len(signals) * 0.12) + min(0.1, len(text) / 2000)
    )
    return _result(
        "risk_signal_detector",
        "risk pattern scan",
        signals,
        metrics,
        suggestions,
        confidence,
    )


def resume_risk_probe(context: SkillContext) -> SkillResult:
    resume = context.resume
    projects = dict_entries(resume.get("project_experience"))
    work = dict_entries(resume.get("work_experience"))
    education = dict_entries(resume.get("education"))
    skills = resume_skills(resume)
    signals: list[SkillSignal] = []
    if not projects:
        signals.append(make_signal("project_experience_missing", "risk"))
    if not work:
        signals.append(make_signal("work_experience_missing", "warning"))
    if not education:
        signals.append(make_signal("education_missing", "warning"))
    if len(skills) > 18:
        signals.append(
            make_signal("too_many_skill_claims", "warning", count=len(skills))
        )
    weak_projects = [
        _item_title(item, index)
        for index, item in enumerate(projects)
        if not _has_any_field(
            item, ("role", "responsibility", "result", "achievement", "description")
        )
    ]
    unquantified_results = [
        _item_title(item, index)
        for index, item in enumerate(projects)
        if matched_terms(clean_text(item), RESULT_TERMS) and not has_number(clean_text(item))
    ]
    if weak_projects:
        signals.append(
            make_signal("project_detail_sparse", "warning", projects=weak_projects[:5])
        )
    if unquantified_results:
        signals.append(
            make_signal(
                "resume_result_unquantified",
                "warning",
                projects=unquantified_results[:5],
            )
        )
    metrics = {
        "project_count": len(projects),
        "work_count": len(work),
        "education_count": len(education),
        "skill_count": len(skills),
        "sparse_project_count": len(weak_projects),
        "unquantified_result_count": len(unquantified_results),
    }
    suggestions = [make_suggestion("verify_resume_claim", "resume_followup", "high")]
    return _result(
        "resume_risk_probe",
        "resume claim risk scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.58),
    )


def resume_project_deepener(context: SkillContext) -> SkillResult:
    projects = dict_entries(context.resume.get("project_experience"))
    candidates: list[JSONDict] = []
    for index, project in enumerate(projects):
        text = clean_text(project)
        coverage = _coverage_from_groups(text, PROJECT_COVERAGE_GROUPS)
        missing = _missing_markers(
            text,
            {
                "role": OWNERSHIP_TERMS,
                "result": RESULT_TERMS,
                "tradeoff": REASONING_TERMS,
            },
        )
        if missing or coverage["covered_count"] < 4:
            candidates.append(
                {
                    "project": _item_title(project, index),
                    "missing": sorted(set([*missing, *coverage["missing"]]))[:6],
                    "covered": coverage["covered"],
                    "covered_count": coverage["covered_count"],
                }
            )
    signals = [
        make_signal(
            "project_semantic_gap",
            "warning" if candidate["covered_count"] < 3 else "info",
            **candidate,
        )
        for candidate in candidates[:4]
    ]
    metrics = {
        "project_count": len(projects),
        "candidate_count": len(candidates),
        "coverage_dimensions": list(PROJECT_COVERAGE_GROUPS),
    }
    suggestions = [
        make_suggestion(
            "deepen_project_claim", "resume_project", "high", project=item["project"]
        )
        for item in candidates[:2]
    ] or [make_suggestion("rotate_project_topic", "resume_project", "medium")]
    return _result(
        "resume_project_deepener",
        "project deepening candidates",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.56),
    )


def resume_timeline_checker(context: SkillContext) -> SkillResult:
    items = [
        *dict_entries(context.resume.get("education")),
        *dict_entries(context.resume.get("work_experience")),
        *dict_entries(context.resume.get("project_experience")),
    ]
    missing_dates = [
        _item_title(item, index)
        for index, item in enumerate(items)
        if not _contains_date(clean_text(item))
    ]
    signals = [
        make_signal("timeline_date_missing", "warning", item=item)
        for item in missing_dates[:5]
    ]
    metrics = {
        "timeline_item_count": len(items),
        "missing_date_count": len(missing_dates),
    }
    suggestions = [
        make_suggestion("ask_timeline_detail", "resume_timeline", "medium", item=item)
        for item in missing_dates[:2]
    ] or [make_suggestion("timeline_looks_complete", "resume_timeline", "low")]
    return _result(
        "resume_timeline_checker",
        "timeline field scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.54),
    )


def technical_depth_probe(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    depth_terms = matched_terms(
        answer,
        ("原理", "源码", "复杂度", "事务", "索引", "并发", "一致性", "缓存", "瓶颈", "架构"),
    )
    coverage = _coverage_from_groups(answer, TECHNICAL_DEPTH_GROUPS)
    answer_tokens = token_count(answer)
    depth_term_count = len(depth_terms)
    metrics = {
        "answer_tokens": answer_tokens,
        "depth_term_count": depth_term_count,
        "has_number": has_number(answer),
        "technical_coverage": coverage,
    }
    signals: list[SkillSignal] = []
    if context.stage == "post_answer" and depth_term_count == 0:
        signals.append(make_signal("technical_depth_insufficient", "warning"))
    if answer and answer_tokens >= 35 and coverage["covered_count"] < 3:
        signals.append(
            make_signal(
                "technical_depth_dimensions_missing",
                "warning",
                missing_dimensions=coverage["missing"][:4],
            )
        )
    if answer and depth_terms and "validation" in coverage["missing"]:
        signals.append(make_signal("technical_validation_missing", "warning"))
    if answer and depth_terms and "boundary" in coverage["missing"]:
        signals.append(make_signal("technical_boundary_missing", "info"))
    if answer_tokens > 80 and depth_term_count >= 2:
        signals.append(
            make_signal(
                "ready_for_deeper_technical_probe", "info", terms=depth_terms[:5]
            )
        )
    suggestions = [
        make_suggestion("increase_depth", "technical_next_question", "high")
        if not signals or signals[0].code == "ready_for_deeper_technical_probe"
        else make_suggestion(
            "ask_foundation_first", "technical_next_question", "medium"
        )
    ]
    return _result(
        "technical_depth_probe",
        "technical depth metrics",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.57),
    )


def technical_gap_mapper(context: SkillContext) -> SkillResult:
    text = context_text(context)
    domains = {
        "database": ("mysql", "sql", "索引", "事务", "隔离", "锁"),
        "network": ("http", "tcp", "网络", "协议", "连接"),
        "os": ("进程", "线程", "内存", "调度", "锁"),
        "algorithm": ("算法", "复杂度", "排序", "搜索", "数据结构"),
        "system_design": ("架构", "缓存", "队列", "限流", "一致性", "扩展"),
        "llm_app": ("rag", "agent", "prompt", "embedding", "向量", "检索"),
    }
    matched = {name: matched_terms(text, terms) for name, terms in domains.items()}
    empty_domains = [name for name, terms in matched.items() if not terms]
    signals = [
        make_signal("technical_topic_gap", "info", topic=topic)
        for topic in empty_domains[:4]
    ]
    metrics = {
        "matched_topics": [name for name, terms in matched.items() if terms],
        "gap_topics": empty_domains,
    }
    suggestions = [
        make_suggestion("cover_technical_gap", topic, "medium")
        for topic in empty_domains[:2]
    ] or [make_suggestion("deepen_matched_topic", "technical_followup", "medium")]
    return _result(
        "technical_gap_mapper",
        "technical topic coverage",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.52),
    )


def technical_tradeoff_checker(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    terms = matched_terms(answer, REASONING_TERMS)
    alternatives = matched_terms(
        answer,
        ("方案A", "方案B", "替代", "相比", "对比", "优缺点", "折中"),
    )
    cost_terms = matched_terms(
        answer,
        ("成本", "复杂度", "维护", "性能", "一致性", "可用性", "安全", "扩展", "上线风险"),
    )
    boundary_terms = matched_terms(answer, TECHNICAL_DEPTH_GROUPS["boundary"])
    signals: list[SkillSignal] = []
    if answer and len(terms) < 2:
        signals.append(make_signal("tradeoff_evidence_missing", "warning"))
    if alternatives:
        signals.append(
            make_signal(
                "alternative_solution_mentioned", "info", terms=alternatives[:5]
            )
        )
    if alternatives and not cost_terms:
        signals.append(make_signal("alternative_without_tradeoff_basis", "warning"))
    if answer and terms and not boundary_terms:
        signals.append(make_signal("boundary_condition_missing", "info"))
    metrics = {
        "reasoning_term_count": len(terms),
        "alternative_term_count": len(alternatives),
        "cost_term_count": len(cost_terms),
        "boundary_term_count": len(boundary_terms),
    }
    suggestions = [
        make_suggestion("ask_technical_tradeoff", "technical_followup", "high")
        if signals
        else make_suggestion("ask_boundary_condition", "technical_followup", "medium")
    ]
    return _result(
        "technical_tradeoff_checker",
        "technical tradeoff scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.55),
    )


def management_signal_probe(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    leadership = matched_terms(
        answer,
        ("协调", "推进", "拆解", "排期", "资源", "风险", "决策", "复盘"),
    )
    ownership = matched_terms(answer, OWNERSHIP_TERMS)
    coverage = _coverage_from_groups(answer, MANAGEMENT_COVERAGE_GROUPS)
    signals: list[SkillSignal] = []
    if leadership:
        signals.append(
            make_signal("management_signal_present", "info", terms=leadership[:5])
        )
    if answer and not ownership:
        signals.append(make_signal("ownership_signal_missing", "warning"))
    if answer and coverage["covered_count"] < 3:
        signals.append(
            make_signal(
                "management_execution_chain_incomplete",
                "warning",
                missing_dimensions=coverage["missing"][:5],
            )
        )
    if answer and "stakeholder" in coverage["missing"]:
        signals.append(make_signal("stakeholder_signal_missing", "info"))
    if answer and "risk" in coverage["missing"]:
        signals.append(make_signal("risk_management_missing", "info"))
    metrics = {
        "leadership_term_count": len(leadership),
        "ownership_term_count": len(ownership),
        "management_coverage": coverage,
    }
    suggestions = [
        make_suggestion("ask_execution_detail", "manager_followup", "medium"),
        make_suggestion("ask_ownership_boundary", "manager_followup", "medium"),
    ]
    return _result(
        "management_signal_probe",
        "management signal scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.56),
    )


def impact_result_probe(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    result_terms = matched_terms(answer, RESULT_TERMS)
    attribution_terms = matched_terms(
        answer,
        ("我负责", "我主导", "我推进", "通过", "带来", "因此", "归因", "来自"),
    )
    signals: list[SkillSignal] = []
    if answer and not has_number(answer):
        signals.append(make_signal("impact_metric_missing", "warning"))
    if result_terms:
        signals.append(
            make_signal("impact_terms_present", "info", terms=result_terms[:5])
        )
    if answer and has_number(answer) and not attribution_terms:
        signals.append(make_signal("metric_attribution_missing", "info"))
    metrics = {
        "has_number": has_number(answer),
        "result_term_count": len(result_terms),
        "attribution_term_count": len(attribution_terms),
    }
    suggestions = [
        make_suggestion("ask_business_metric", "manager_impact", "high")
        if not has_number(answer)
        else make_suggestion("ask_metric_attribution", "manager_impact", "medium")
    ]
    return _result(
        "impact_result_probe",
        "impact result scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.56),
    )


def collaboration_conflict_checker(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    terms = matched_terms(
        answer,
        ("冲突", "分歧", "沟通", "协作", "对齐", "跨部门", "推动", "升级"),
    )
    coverage = _coverage_from_groups(answer, COLLABORATION_COVERAGE_GROUPS)
    signals = []
    if terms:
        signals.append(make_signal("collaboration_or_conflict_signal", "info", terms=terms[:5]))
    else:
        signals.append(make_signal("collaboration_evidence_missing", "warning"))
    if answer and "conflict" in coverage["covered"] and "resolution" in coverage["missing"]:
        signals.append(make_signal("conflict_resolution_missing", "warning"))
    if answer and terms and "result" in coverage["missing"]:
        signals.append(make_signal("collaboration_result_missing", "info"))
    metrics = {
        "collaboration_term_count": len(terms),
        "collaboration_coverage": coverage,
    }
    suggestions = [
        make_suggestion("ask_conflict_resolution", "manager_collaboration", "medium")
    ]
    return _result(
        "collaboration_conflict_checker",
        "collaboration signal scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.54),
    )


def hr_motivation_probe(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    terms = matched_terms(
        answer, ("兴趣", "发展", "成长", "岗位", "行业", "价值", "长期", "规划", "喜欢")
    )
    coverage = _coverage_from_groups(answer, MOTIVATION_COVERAGE_GROUPS)
    signals = []
    if terms:
        signals.append(make_signal("motivation_signal_present", "info", terms=terms[:5]))
    else:
        signals.append(make_signal("motivation_signal_missing", "warning"))
    if answer and terms and "evidence" in coverage["missing"]:
        signals.append(make_signal("motivation_evidence_missing", "warning"))
    if answer and "role_alignment" in coverage["missing"]:
        signals.append(make_signal("role_alignment_missing", "info"))
    metrics = {
        "motivation_term_count": len(terms),
        "motivation_coverage": coverage,
    }
    suggestions = [
        make_suggestion("ask_motivation_evidence", "hr_motivation", "medium")
    ]
    return _result(
        "hr_motivation_probe",
        "motivation signal scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.55),
    )


def stability_risk_probe(context: SkillContext) -> SkillResult:
    text = context_text(context, include_resume=True)
    terms = matched_terms(
        text,
        ("离职", "频繁", "不稳定", "加班", "薪资", "压力", "不适应", "转行"),
    )
    positive_terms = matched_terms(text, STABILITY_POSITIVE_TERMS)
    reason_terms = matched_terms(text, STABILITY_REASON_TERMS)
    work_count = len(dict_entries(context.resume.get("work_experience")))
    signals: list[SkillSignal] = []
    if terms:
        signals.append(make_signal("stability_risk_terms", "risk", terms=terms[:5]))
    if terms and not reason_terms:
        signals.append(make_signal("stability_reason_missing", "warning"))
    if work_count >= 4:
        signals.append(make_signal("many_work_segments", "warning", count=work_count))
    if work_count >= 4 and not positive_terms:
        signals.append(make_signal("stability_commitment_missing", "warning"))
    metrics = {
        "stability_term_count": len(terms),
        "positive_stability_term_count": len(positive_terms),
        "reason_term_count": len(reason_terms),
        "work_count": work_count,
    }
    suggestions = [
        make_suggestion(
            "ask_stability_reason", "hr_stability", "high" if signals else "medium"
        )
    ]
    return _result(
        "stability_risk_probe",
        "stability risk scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.54),
    )


def expectation_alignment_checker(context: SkillContext) -> SkillResult:
    answer = current_answer(context)
    terms = matched_terms(
        answer,
        ("薪资", "地点", "远程", "到岗", "offer", "职级", "团队", "工作强度"),
    )
    coverage = _coverage_from_groups(answer, EXPECTATION_GROUPS)
    signals = []
    if terms:
        signals.append(make_signal("expectation_terms_present", "info", terms=terms[:5]))
    else:
        signals.append(make_signal("expectation_not_yet_covered", "info"))
    if "compensation" in coverage["covered"] and not has_number(answer):
        signals.append(make_signal("salary_range_missing", "warning"))
    if terms and coverage["covered_count"] < 2:
        signals.append(
            make_signal(
                "expectation_detail_sparse",
                "info",
                missing_dimensions=coverage["missing"][:5],
            )
        )
    metrics = {
        "expectation_term_count": len(terms),
        "expectation_coverage": coverage,
    }
    suggestions = [
        make_suggestion("ask_expectation_alignment", "hr_expectation", "medium")
    ]
    return _result(
        "expectation_alignment_checker",
        "expectation alignment scan",
        signals,
        metrics,
        suggestions,
        _confidence(signals, 0.52),
    )


SKILL_DEFINITIONS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        "context_summary",
        "Summarize stable context metrics.",
        "common",
        ALL_ROUNDS,
        ALL_STAGES,
        False,
        context_summary,
    ),
    SkillDefinition(
        "answer_quality_probe",
        "Detect answer quality signals.",
        "common",
        ALL_ROUNDS,
        ("post_answer",),
        False,
        answer_quality_probe,
    ),
    SkillDefinition(
        "followup_question_suggester",
        "Return structured follow-up directions.",
        "common",
        ALL_ROUNDS,
        ("post_answer",),
        False,
        followup_question_suggester,
    ),
    SkillDefinition(
        "risk_signal_detector",
        "Scan uncertainty and risk terms.",
        "common",
        ALL_ROUNDS,
        ALL_STAGES,
        False,
        risk_signal_detector,
    ),
    SkillDefinition(
        "resume_risk_probe",
        "Scan resume claim risk.",
        "specialized",
        ("resume",),
        ALL_STAGES,
        False,
        resume_risk_probe,
    ),
    SkillDefinition(
        "resume_project_deepener",
        "Find project deepening candidates.",
        "specialized",
        ("resume",),
        ALL_STAGES,
        False,
        resume_project_deepener,
    ),
    SkillDefinition(
        "resume_timeline_checker",
        "Check timeline date completeness.",
        "specialized",
        ("resume",),
        ALL_STAGES,
        False,
        resume_timeline_checker,
    ),
    SkillDefinition(
        "technical_depth_probe",
        "Measure technical depth indicators.",
        "specialized",
        ("technical",),
        ALL_STAGES,
        False,
        technical_depth_probe,
    ),
    SkillDefinition(
        "technical_gap_mapper",
        "Map uncovered technical topics.",
        "specialized",
        ("technical",),
        ALL_STAGES,
        False,
        technical_gap_mapper,
    ),
    SkillDefinition(
        "technical_tradeoff_checker",
        "Check tradeoff and boundary evidence.",
        "specialized",
        ("technical",),
        ALL_STAGES,
        False,
        technical_tradeoff_checker,
    ),
    SkillDefinition(
        "management_signal_probe",
        "Detect management and execution signals.",
        "specialized",
        ("manager",),
        ALL_STAGES,
        False,
        management_signal_probe,
    ),
    SkillDefinition(
        "impact_result_probe",
        "Detect impact and metric evidence.",
        "specialized",
        ("manager",),
        ALL_STAGES,
        False,
        impact_result_probe,
    ),
    SkillDefinition(
        "collaboration_conflict_checker",
        "Detect collaboration and conflict signals.",
        "specialized",
        ("manager",),
        ALL_STAGES,
        False,
        collaboration_conflict_checker,
    ),
    SkillDefinition(
        "hr_motivation_probe",
        "Detect motivation signals.",
        "specialized",
        ("hr",),
        ALL_STAGES,
        False,
        hr_motivation_probe,
    ),
    SkillDefinition(
        "stability_risk_probe",
        "Detect stability risk signals.",
        "specialized",
        ("hr",),
        ALL_STAGES,
        False,
        stability_risk_probe,
    ),
    SkillDefinition(
        "expectation_alignment_checker",
        "Detect expectation alignment coverage.",
        "specialized",
        ("hr",),
        ALL_STAGES,
        False,
        expectation_alignment_checker,
    ),
)


def _result(
    name: str,
    prefix: str,
    signals: list[SkillSignal],
    metrics: JSONDict,
    suggestions: list[Any],
    confidence: float,
) -> SkillResult:
    return SkillResult(
        skill_name=name,
        summary=short_summary(prefix, signals, metrics),
        signals=signals,
        metrics=metrics,
        suggestions=suggestions,
        confidence=confidence,
        llm_enhanced=False,
    )


def _confidence(signals: list[SkillSignal], base: float) -> float:
    return clamp_confidence(base + min(0.22, len(signals) * 0.07))


def _last_question_type(context: SkillContext) -> str | None:
    if not context.qa_history:
        return None
    value = context.qa_history[-1].get("question_type")
    return str(value) if value else None


def _repeated_short_answers(context: SkillContext) -> bool:
    lengths = [
        token_count(clean_text(item.get("answer")))
        for item in context.qa_history[-3:]
        if item.get("answer")
    ]
    return len(lengths) >= 2 and all(length < 30 for length in lengths)


def _item_title(item: JSONDict, index: int) -> str:
    for key in ("name", "project_name", "title", "company", "school"):
        if item.get(key):
            return clean_text(item[key])
    return f"item_{index + 1}"


def _has_any_field(item: JSONDict, fields: tuple[str, ...]) -> bool:
    return any(bool(clean_text(item.get(field))) for field in fields)


def _missing_markers(text: str, groups: dict[str, tuple[str, ...]]) -> list[str]:
    return [name for name, terms in groups.items() if not matched_terms(text, terms)]


def _semantic_coverage(
    *,
    context_terms: list[str],
    action_terms: list[str],
    result_terms: list[str],
    reasoning_terms: list[str],
    reflection_terms: list[str],
) -> JSONDict:
    dimensions = {
        "context": bool(context_terms),
        "action": bool(action_terms),
        "result": bool(result_terms),
        "reasoning": bool(reasoning_terms),
        "reflection": bool(reflection_terms),
    }
    covered = [name for name, present in dimensions.items() if present]
    missing = [name for name, present in dimensions.items() if not present]
    return {
        "covered": covered,
        "missing": missing,
        "covered_count": len(covered),
        "dimension_count": len(dimensions),
    }


def _missing_question_focus(question: str, answer: str) -> list[str]:
    if not question or not answer:
        return []
    expected = [
        name
        for name, terms in QUESTION_FOCUS_GROUPS.items()
        if matched_terms(question, terms)
    ]
    missing: list[str] = []
    for name in expected:
        answer_terms = ANSWER_FOCUS_GROUPS.get(name, ())
        if answer_terms and not matched_terms(answer, answer_terms):
            missing.append(name)
    return missing


def _coverage_from_groups(text: str, groups: Mapping[str, tuple[str, ...]]) -> JSONDict:
    matched = {name: matched_terms(text, terms) for name, terms in groups.items()}
    covered = [name for name, terms in matched.items() if terms]
    missing = [name for name, terms in matched.items() if not terms]
    return {
        "covered": covered,
        "missing": missing,
        "covered_count": len(covered),
        "dimension_count": len(groups),
        "matched_terms": {name: terms[:5] for name, terms in matched.items() if terms},
    }


def _contains_date(text: str) -> bool:
    return bool(
        __import__("re").search(
            r"(19|20)\d{2}|至今|present|now", text, flags=__import__("re").I
        )
    )
