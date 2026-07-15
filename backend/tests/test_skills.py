from __future__ import annotations

from typing import Any

from app.services.interviews import InterviewService
from app.skills.catalog import (
    answer_quality_probe,
    collaboration_conflict_checker,
    expectation_alignment_checker,
    hr_motivation_probe,
    management_signal_probe,
    resume_project_deepener,
    stability_risk_probe,
    technical_depth_probe,
    technical_tradeoff_checker,
)
from app.skills.registry import DEFAULT_SKILL_REGISTRY
from app.skills.runner import DEFAULT_SKILL_RUNNER
from app.skills.selector import select_skills
from app.skills.types import SkillContext
from test_interview import FakeInterviewRepository, FakeLLMClient


def test_skill_registry_contains_common_and_round_specific_skills() -> None:
    definitions = DEFAULT_SKILL_REGISTRY.all()

    assert len(definitions) == 16
    assert sum(1 for item in definitions if item.category == "common") == 4
    assert sum(1 for item in definitions if item.category == "specialized") == 12
    for round_type in ("resume", "technical", "manager", "hr"):
        available = DEFAULT_SKILL_REGISTRY.list_available(round_type, "post_answer")
        names = {item.name for item in available}
        assert "answer_quality_probe" in names
        assert len([item for item in available if item.category == "specialized"]) == 3
        assert all(item.llm_enhanced is False for item in available)


def test_skill_selector_uses_llm_result_but_limits_to_two_known_skills() -> None:
    context = _skill_context(round_type="technical", stage="post_answer")
    candidates = DEFAULT_SKILL_REGISTRY.list_available("technical", "post_answer")

    selected = select_skills(
        context=context,
        candidates=candidates,
        llm_client=_SelectorLLM(),
        max_skills=2,
    )

    assert [item.name for item in selected] == [
        "answer_quality_probe",
        "technical_depth_probe",
    ]
    assert all(item.source == "llm" for item in selected)


def test_skill_selector_respects_valid_empty_llm_selection() -> None:
    context = _skill_context(round_type="technical", stage="post_answer")
    candidates = DEFAULT_SKILL_REGISTRY.list_available("technical", "post_answer")

    selected = select_skills(
        context=context,
        candidates=candidates,
        llm_client=_EmptySelectorLLM(),
        max_skills=2,
    )

    assert selected == []


def test_skill_runner_falls_back_to_deterministic_rule_selection() -> None:
    context = _skill_context(round_type="manager", stage="post_answer")

    bundle = DEFAULT_SKILL_RUNNER.run(context=context, llm_client=object())
    agent_context = bundle.agent_context()

    assert len(bundle.calls) == 2
    assert [call.skill_name for call in bundle.calls] == [
        "answer_quality_probe",
        "impact_result_probe",
    ]
    assert agent_context["results"]
    assert agent_context["results"][0]["metrics"]
    assert agent_context["results"][0]["suggestions"]
    assert all(call.llm_enhanced is False for call in bundle.calls)


def test_answer_quality_probe_detects_generic_answer_semantic_gaps() -> None:
    context = _skill_context(
        round_type="technical",
        stage="post_answer",
        question="为什么选择这个技术方案，如何权衡风险，最后效果怎么样？",
        previous_answer="这个项目我做了很多优化，整体效果还可以，最后也顺利上线了。",
    )

    result = answer_quality_probe(context)
    codes = {signal.code for signal in result.signals}

    assert "vague_or_generic_answer" in codes
    assert "question_focus_unanswered" in codes
    assert "missing_personal_ownership" in codes
    assert result.metrics["missing_question_focus"] == ["reasoning", "technical"]
    assert result.metrics["semantic_coverage"]["covered_count"] < 3


def test_answer_quality_probe_accepts_specific_answer_evidence() -> None:
    context = _skill_context(
        round_type="technical",
        stage="post_answer",
        question="为什么选择这个技术方案，如何权衡风险，最后效果怎么样？",
        previous_answer=(
            "背景是接口高峰期频繁超时，我负责排查慢查询并重构索引。"
            "因为要权衡写入成本和查询性能，我先做压测验证，最终 P95 延迟降低 35%。"
        ),
    )

    result = answer_quality_probe(context)
    codes = {signal.code for signal in result.signals}

    assert "vague_or_generic_answer" not in codes
    assert "question_focus_unanswered" not in codes
    assert "missing_quantified_result" not in codes
    assert "missing_personal_ownership" not in codes
    assert result.metrics["semantic_coverage"]["covered_count"] >= 4


def test_technical_skills_detect_depth_and_tradeoff_gaps() -> None:
    context = _skill_context(
        round_type="technical",
        stage="post_answer",
        previous_answer=(
            "我做了缓存优化，因为接口有问题，也对比了几个方案，最后上线了。"
        ),
    )

    depth = technical_depth_probe(context)
    tradeoff = technical_tradeoff_checker(context)
    depth_codes = {signal.code for signal in depth.signals}
    tradeoff_codes = {signal.code for signal in tradeoff.signals}

    assert "technical_validation_missing" in depth_codes
    assert "technical_boundary_missing" in depth_codes
    assert "alternative_without_tradeoff_basis" in tradeoff_codes
    assert depth.metrics["technical_coverage"]["covered_count"] >= 2


def test_resume_project_deepener_detects_project_semantic_gap() -> None:
    context = _skill_context(
        round_type="resume",
        stage="pre_question",
        resume={
            "skills": ["Python", "MySQL"],
            "project_experience": [
                {
                    "name": "面试系统",
                    "description": "负责系统开发，最终效率提升。",
                }
            ],
            "work_experience": [],
            "education": [],
        },
    )

    result = resume_project_deepener(context)
    signal = result.signals[0]

    assert signal.code == "project_semantic_gap"
    assert "technical" in signal.evidence["missing"]
    assert "tradeoff" in signal.evidence["missing"]


def test_management_and_collaboration_skills_detect_missing_chain() -> None:
    context = _skill_context(
        round_type="manager",
        stage="post_answer",
        previous_answer="我推进排期，也和产品有分歧，后来沟通对齐后继续做。",
    )

    management = management_signal_probe(context)
    collaboration = collaboration_conflict_checker(context)
    management_codes = {signal.code for signal in management.signals}
    collaboration_codes = {signal.code for signal in collaboration.signals}

    assert "risk_management_missing" in management_codes
    assert "collaboration_result_missing" in collaboration_codes
    assert management.metrics["management_coverage"]["covered_count"] >= 2


def test_hr_skills_detect_stability_and_expectation_gaps() -> None:
    context = _skill_context(
        round_type="hr",
        stage="post_answer",
        previous_answer="我关注成长和长期发展，也比较在意薪资和加班压力。",
        resume={
            "skills": ["Python"],
            "project_experience": [],
            "work_experience": [
                {"company": "A", "title": "开发"},
                {"company": "B", "title": "开发"},
                {"company": "C", "title": "开发"},
                {"company": "D", "title": "开发"},
            ],
            "education": [],
        },
    )

    motivation = hr_motivation_probe(context)
    stability = stability_risk_probe(context)
    expectation = expectation_alignment_checker(context)

    assert "role_alignment_missing" in {signal.code for signal in motivation.signals}
    assert "stability_reason_missing" in {signal.code for signal in stability.signals}
    assert "salary_range_missing" in {signal.code for signal in expectation.signals}


def test_interview_service_injects_skill_context_and_records_traces() -> None:
    repository = _TraceRecordingInterviewRepository()
    repository.add_resume(resume_id=1, user_id=1)
    llm_client = _SkillSelectingLLMClient()
    service = InterviewService(
        repository=repository,  # type: ignore[arg-type]
        llm_client=llm_client,  # type: ignore[arg-type]
    )
    interview = service.create_interview(
        user_id=1,
        resume_id=1,
        target_position="后端开发",
        selected_rounds=["technical"],
    )
    round_record = repository.rounds[interview.id][0]

    first_question = service.start_round(1, interview.id, round_record.id)

    assert first_question.question.startswith("问题")
    assert len(repository.skill_call_traces) == 2
    assert {item["stage"] for item in repository.skill_call_traces} == {"pre_question"}
    first_payload = llm_client.question_resume_payloads[-1]
    assert first_payload["_skill_context"]["results"]
    assert (
        first_payload["_skill_context"]["selected_skills"][0]["name"]
        == "context_summary"
    )

    service.answer_round_question(
        user_id=1,
        interview_id=interview.id,
        round_id=round_record.id,
        question_id=first_question.id,
        answer="我负责接口设计，因为要兼顾性能和一致性，最终接口耗时降低 30%。",
    )

    assert len(repository.skill_call_traces) == 4
    assert {item["stage"] for item in repository.skill_call_traces} == {
        "pre_question",
        "post_answer",
    }
    latest_payload = llm_client.question_resume_payloads[-1]
    assert latest_payload["_skill_context"]["results"]
    assert latest_payload["_skill_context"]["results"][0]["metrics"]
    assert latest_payload["_skill_context"]["results"][0]["suggestions"]
    assert latest_payload["_skill_context"]["selected_skills"][0]["source"] == "llm"
    assert all(
        "answer" not in trace["input_summary"] for trace in repository.skill_call_traces
    )


class _SelectorLLM:
    def generate_json(
        self, system_prompt: str, user_payload: dict[str, Any]
    ) -> dict[str, Any]:
        assert "skill 选择器" in system_prompt
        assert user_payload["max_skills"] == 2
        return {
            "selected_skills": [
                {"name": "answer_quality_probe", "reason": "需要判断回答质量"},
                {"name": "unknown_skill", "reason": "应被忽略"},
                {"name": "technical_depth_probe", "reason": "需要判断技术深度"},
                {"name": "technical_gap_mapper", "reason": "超过数量上限"},
            ]
        }


class _EmptySelectorLLM:
    def generate_json(
        self, system_prompt: str, user_payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {"selected_skills": []}


class _SkillSelectingLLMClient(FakeLLMClient):
    def generate_json(
        self, system_prompt: str, user_payload: dict[str, Any]
    ) -> dict[str, Any]:
        if "candidate_skills" not in user_payload:
            return {"selected_skills": []}
        candidates = {item["name"] for item in user_payload["candidate_skills"]}
        preferred = [
            "context_summary",
            "technical_gap_mapper",
            "answer_quality_probe",
            "technical_depth_probe",
        ]
        selected = [
            {"name": name, "reason": "test_selected"}
            for name in preferred
            if name in candidates
        ][:2]
        return {"selected_skills": selected}


class _TraceRecordingInterviewRepository(FakeInterviewRepository):
    def __init__(self) -> None:
        super().__init__()
        self.skill_call_traces: list[dict[str, Any]] = []

    def create_skill_call_trace(self, **kwargs: Any) -> int:
        self.skill_call_traces.append(kwargs)
        return len(self.skill_call_traces)


def _skill_context(
    round_type: str,
    stage: str,
    *,
    question: str = "请说明一次接口优化。",
    previous_answer: str | None = None,
    resume: dict[str, Any] | None = None,
) -> SkillContext:
    if stage == "post_answer" and previous_answer is None:
        previous_answer = "我负责接口设计，因为需要权衡性能和一致性，最终响应耗时降低 30%。"
    return SkillContext(
        user_id=1,
        interview_id=1,
        round_id=1,
        round_type=round_type,
        stage=stage,  # type: ignore[arg-type]
        target_position="后端开发",
        job_description="负责接口、数据库和系统稳定性。",
        resume=resume
        or {
            "skills": ["Python", "MySQL"],
            "project_experience": [
                {
                    "name": "面试系统",
                    "role": "后端开发",
                    "result": "响应时间降低 30%",
                }
            ],
            "work_experience": [],
            "education": [],
        },
        qa_history=[
            {
                "question_type": "technical",
                "question": question,
                "answer": previous_answer,
                "question_kind": "main",
            }
        ]
        if previous_answer
        else [],
        previous_answer=previous_answer,
        question_kind="main",
    )
