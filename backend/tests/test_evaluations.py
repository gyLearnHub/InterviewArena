import inspect
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.final_evaluation import FinalEvaluationAgent
from app.agents.question_evaluation import QuestionEvaluationAgent
from app.agents.round_evaluation import RoundEvaluationAgent
from app.repositories.evaluations import EvaluationRecord
from app.repositories.interviews import (
    InterviewRecord,
    InterviewRoundRecord,
    QARecord,
    ResumeRecord,
)
from app.services.evaluations import (
    FINAL_EVALUATION_TYPE,
    QUESTION_EVALUATION_TYPE,
    EvaluationSchedulerService,
)


class FakeEvaluationRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], EvaluationRecord] = {}
        self.next_id = 1

    def get_by_key(self, evaluation_type: str, evaluation_key: str) -> EvaluationRecord | None:
        return self.records.get((evaluation_type, evaluation_key))

    def list_by_interview(
        self,
        interview_id: int,
        evaluation_type: str | None = None,
        round_id: int | None = None,
    ) -> list[EvaluationRecord]:
        return [
            record
            for record in self.records.values()
            if record.interview_id == interview_id
            and (evaluation_type is None or record.evaluation_type == evaluation_type)
            and (round_id is None or record.round_id == round_id)
        ]

    def save_success(
        self,
        *,
        evaluation_type: str,
        evaluation_key: str,
        interview_id: int,
        round_id: int | None,
        question_id: int | None,
        dimension_scores: list[dict[str, Any]],
        total_score: int | None,
        evidence: list[str],
        result: dict[str, Any],
        prompt_version: str,
        model_name: str,
    ) -> EvaluationRecord:
        record = EvaluationRecord(
            id=self.next_id,
            evaluation_type=evaluation_type,
            evaluation_key=evaluation_key,
            interview_id=interview_id,
            round_id=round_id,
            question_id=question_id,
            status="succeeded",
            dimension_scores=dimension_scores,
            total_score=total_score,
            evidence=evidence,
            result=result,
            error_message=None,
            prompt_version=prompt_version,
            model_name=model_name,
            created_at=None,
            updated_at=None,
        )
        self.next_id += 1
        self.records[(evaluation_type, evaluation_key)] = record
        return record

    def save_failure(
        self,
        *,
        evaluation_type: str,
        evaluation_key: str,
        interview_id: int,
        round_id: int | None,
        question_id: int | None,
        error_message: str,
        prompt_version: str,
        model_name: str,
    ) -> EvaluationRecord:
        record = EvaluationRecord(
            id=self.next_id,
            evaluation_type=evaluation_type,
            evaluation_key=evaluation_key,
            interview_id=interview_id,
            round_id=round_id,
            question_id=question_id,
            status="failed",
            dimension_scores=[],
            total_score=None,
            evidence=[],
            result=None,
            error_message=error_message,
            prompt_version=prompt_version,
            model_name=model_name,
            created_at=None,
            updated_at=None,
        )
        self.next_id += 1
        self.records[(evaluation_type, evaluation_key)] = record
        return record


class FakeLLMClient:
    model_name = "fake-model"

    def __init__(self, payloads: list[dict[str, Any]] | None = None) -> None:
        self.payloads = payloads or []
        self.calls: list[dict[str, Any]] = []

    def parse_resume(self, resume_text: str) -> dict[str, Any]:
        raise AssertionError("parse_resume should not be called")

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        raise AssertionError("generate_question should not be called")

    def generate_feedback(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raise AssertionError("generate_feedback should not be called")

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"system_prompt": system_prompt, "user_payload": user_payload})
        if not self.payloads:
            raise RuntimeError("LLM failed")
        return self.payloads.pop(0)


def test_evaluation_agents_have_separate_files_and_prompts() -> None:
    agent_files = {
        QuestionEvaluationAgent: "question_evaluation.py",
        RoundEvaluationAgent: "round_evaluation.py",
        FinalEvaluationAgent: "final_evaluation.py",
    }

    for agent_class, file_name in agent_files.items():
        assert Path(inspect.getsourcefile(agent_class) or "").name == file_name

    assert QuestionEvaluationAgent.prompt_file == "question_evaluation.md"
    assert RoundEvaluationAgent.prompt_file_for("resume") == "round_evaluation_resume.md"
    assert RoundEvaluationAgent.prompt_file_for("technical") == "round_evaluation_technical.md"
    assert RoundEvaluationAgent.prompt_file_for("manager") == "round_evaluation_manager.md"
    assert RoundEvaluationAgent.prompt_file_for("hr") == "round_evaluation_hr.md"
    assert FinalEvaluationAgent.prompt_file == "final_evaluation.md"


def test_question_score_failure_is_recorded_and_non_blocking() -> None:
    repository = FakeEvaluationRepository()
    service = EvaluationSchedulerService(repository, FakeLLMClient())

    result = service.score_question(
        interview=_interview(),
        round_record=_round(),
        qa=_qa(answer="回答"),
        resume=_resume(),
    )

    assert result is None
    records = repository.list_by_interview(1, QUESTION_EVALUATION_TYPE, 10)
    assert records[0].status == "failed"
    assert records[0].evaluation_key == "1:10:100"
    assert records[0].model_name == "fake-model"


def test_question_score_caps_unknown_answer_and_removes_strengths() -> None:
    llm = FakeLLMClient(
        [
            {
                "total_score": 88,
                "dimension_scores": [
                    {"dimension": "经历真实性", "score": 88, "reason": "模型误判为高分"}
                ],
                "strengths": ["表达积极"],
                "issues": [],
                "evidence": ["不知道"],
                "should_follow_up": False,
                "follow_up_direction": None,
            }
        ]
    )
    service = EvaluationSchedulerService(FakeEvaluationRepository(), llm)

    result = service.score_question(
        interview=_interview(),
        round_record=_round(),
        qa=_qa(answer="不知道"),
        resume=_resume(),
    )

    assert result is not None
    assert result.total_score == 10
    assert result.strengths == []
    assert result.dimension_scores[0].score == 10
    assert result.should_follow_up is True
    assert llm.calls == []


def test_question_score_accepts_string_evidence_from_llm() -> None:
    repository = FakeEvaluationRepository()
    llm = FakeLLMClient(
        [
            {
                "total_score": 99,
                "dimension_scores": [
                    {"dimension": "正确性", "score": 75, "reason": "回答有项目证据"},
                    {"dimension": "相关性", "score": 78, "reason": "围绕项目经历回答"},
                    {"dimension": "完整性", "score": 68, "reason": "缺少结果指标"},
                    {"dimension": "逻辑性", "score": 72, "reason": "表达基本清楚"},
                    {"dimension": "深度", "score": 55, "reason": "技术细节不足"},
                ],
                "strengths": ["能说明项目实践"],
                "issues": [],
                "evidence": "回答提到了项目实践和技术取舍。",
                "should_follow_up": False,
                "follow_up_direction": None,
            }
        ]
    )
    service = EvaluationSchedulerService(repository, llm)

    result = service.score_question(
        interview=_interview(),
        round_record=_round(),
        qa=_qa(answer="我在项目中负责后端接口和评分流程。"),
        resume=_resume(),
    )

    assert result is not None
    assert result.evidence == ["回答提到了项目实践和技术取舍。"]
    assert result.total_score == 72
    records = repository.list_by_interview(1, QUESTION_EVALUATION_TYPE, 10)
    assert records[0].status == "succeeded"


def test_question_score_calibration_orders_answer_quality_for_same_question() -> None:
    question = "请解释数据库索引为什么能提升查询性能，并说明它的代价。"
    llm = FakeLLMClient(
        [
            _quality_payload(
                correctness=20,
                relevance=82,
                completeness=45,
                logic=48,
                depth=35,
                strengths=["内容较长"],
                issues=["把索引错误描述为加密机制，核心概念错误。", "没有说明查询路径和维护成本。"],
                evidence=["回答声称索引用来加密数据。"],
            ),
            _quality_payload(
                correctness=52,
                relevance=80,
                completeness=45,
                logic=60,
                depth=35,
                strengths=["提到索引可以减少扫描"],
                issues=["遗漏 B+ 树有序结构和写入维护成本。"],
                evidence=["回答提到索引能减少全表扫描。"],
            ),
            _quality_payload(
                correctness=76,
                relevance=86,
                completeness=75,
                logic=75,
                depth=58,
                strengths=["能解释减少扫描和定位数据"],
                issues=["对覆盖索引、选择性和写入代价展开不足。"],
                evidence=["回答说明索引能缩小扫描范围，但细节有限。"],
            ),
            _quality_payload(
                correctness=94,
                relevance=96,
                completeness=92,
                logic=91,
                depth=90,
                strengths=["准确解释 B+ 树、选择性、回表和写入维护成本"],
                issues=[],
                evidence=["回答覆盖 B+ 树、范围查询、回表、空间和写入代价。"],
            ),
        ]
    )
    service = EvaluationSchedulerService(FakeEvaluationRepository(), llm)
    answers = [
        "",
        "我不知道。",
        "今天天气很好，我平时喜欢打篮球。",
        "数据库索引主要是把密码加密后放到数据库里，所以查询会更安全，也就更快。"
        "只要建了索引，任何查询都会变快，而且没有明显成本。",
        "索引可以减少全表扫描，让数据库更快定位数据，但我不太清楚具体结构，"
        "也没有说清楚写入和存储上的代价。",
        "索引类似目录，可以让数据库少扫一些数据，更快定位满足条件的记录。"
        "不过索引会占空间，写入和更新时也需要维护，所以不是越多越好。",
        "MySQL 常见索引用 B+ 树保存有序键值，查询时能从根节点逐层定位叶子节点，"
        "减少全表扫描，并支持范围查询；如果命中覆盖索引还能少回表。代价是占用空间，"
        "插入、更新、删除要维护树结构，低选择性字段或函数计算还可能用不上索引，"
        "所以要结合基数、查询模式和写入频率权衡。",
    ]

    scores = [
        _score_answer(service, answer, qa_id=100 + index, question=question).total_score
        for index, answer in enumerate(answers)
    ]

    assert scores == [0, 10, 20, 29, 57, 76, 93]
    assert scores == sorted(scores)
    assert scores[-1] - scores[-2] >= 15
    assert scores[-2] - scores[4] >= 15
    assert llm.calls and len(llm.calls) == 4


def test_round_summary_uses_supplied_question_scores() -> None:
    question_scores = [{"question_id": 100, "total_score": 82, "evidence": ["回答具体"]}]
    llm = FakeLLMClient(
        [
            {
                "total_score": 82,
                "result": "passed",
                "dimension_scores": [
                    {"dimension": "经历真实性", "score": 82, "reason": "证据清晰"}
                ],
                "strengths": ["项目说明清楚"],
                "weaknesses": ["量化结果不足"],
                "suggestions": ["补充指标"],
                "evidence": ["回答具体"],
                "is_reference_only": False,
                "reference_note": None,
            }
        ]
    )
    service = EvaluationSchedulerService(FakeEvaluationRepository(), llm)

    summary = service.generate_round_summary(
        interview=_interview(),
        round_record=_round(),
        qa_history=[_qa(answer="回答")],
        question_scores=question_scores,
        is_reference_only=False,
    )

    assert llm.calls[0]["user_payload"]["question_evaluations"] == question_scores
    assert summary["score"] == 82
    assert summary["question_evaluations"] == question_scores


def test_round_summary_counts_unknown_and_unanswered_questions_as_low_scores() -> None:
    question_scores = [
        {
            "question_id": 100,
            "total_score": 88,
            "dimension_scores": [
                {"dimension": "经历真实性", "score": 88, "reason": "模型误判为高分"}
            ],
            "evidence": ["不知道"],
        }
    ]
    llm = FakeLLMClient(
        [
            {
                "total_score": 88,
                "result": "passed",
                "dimension_scores": [
                    {"dimension": "经历真实性", "score": 88, "reason": "模型误判为高分"}
                ],
                "strengths": ["表达积极"],
                "weaknesses": [],
                "suggestions": [],
                "evidence": ["不知道"],
                "is_reference_only": False,
                "reference_note": None,
            }
        ]
    )
    service = EvaluationSchedulerService(FakeEvaluationRepository(), llm)

    summary = service.generate_round_summary(
        interview=_interview(),
        round_record=_round(),
        qa_history=[_qa(answer="不知道"), _qa(answer=None, qa_id=101, sequence=2)],
        question_scores=question_scores,
        is_reference_only=False,
    )

    assert summary["score"] == 0
    assert summary["result"] == "failed"
    assert summary["strengths"] == []


def test_final_summary_does_not_receive_question_scores() -> None:
    llm = FakeLLMClient(
        [
            {
                "total_score": 78,
                "round_scores": [
                    {
                        "round_type": "resume",
                        "score": 82,
                        "result": "passed",
                        "is_reference_only": False,
                        "status": "completed",
                    }
                ],
                "ability_analysis": ["沟通表达稳定"],
                "job_match": "岗位匹配度较高",
                "core_strengths": ["项目经验相关"],
                "main_risks": ["技术深度仍需验证"],
                "improvement_plan": ["补充技术细节"],
                "final_conclusion": "建议录用",
                "confidence": "high",
                "reference_note": None,
            }
        ]
    )
    service = EvaluationSchedulerService(FakeEvaluationRepository(), llm)

    report = service.generate_final_report(
        interview=_interview(),
        resume=_resume(),
        rounds=[
            _round(
                summary={
                    "score": 82,
                    "result": "passed",
                    "question_evaluations": [{"question_id": 100, "total_score": 82}],
                }
            )
        ],
        effective_history_memory=[],
    )

    round_payload = llm.calls[0]["user_payload"]["round_evaluations"][0]
    assert "question_evaluations" not in round_payload["summary"]
    assert "candidate_memories" not in llm.calls[0]["user_payload"]
    assert "effective_history_memory" not in llm.calls[0]["user_payload"]
    assert report["score"] == 82
    assert repository_record_types(service) == [FINAL_EVALUATION_TYPE]


def test_final_summary_score_is_calculated_from_round_scores_and_completion() -> None:
    llm = FakeLLMClient(
        [
            {
                "total_score": 90,
                "round_scores": [],
                "ability_analysis": ["模型误判为优秀"],
                "job_match": "模型误判为匹配",
                "core_strengths": ["简历背景好"],
                "main_risks": [],
                "improvement_plan": [],
                "final_conclusion": "建议录用",
                "confidence": "high",
                "reference_note": None,
            }
        ]
    )
    service = EvaluationSchedulerService(FakeEvaluationRepository(), llm)
    completed = _round(summary={"score": 80, "result": "passed"})
    early = replace(
        _round(summary={"score": 80, "result": "passed", "is_reference_only": True}),
        id=11,
        round_type="technical",
        status="finished_early",
        score=80,
        result="passed",
        is_reference_only=True,
    )
    cancelled = replace(_round(), id=12, round_type="manager", status="cancelled", score=None)
    pending = replace(_round(), id=13, round_type="hr", status="pending", score=None)

    report = service.generate_final_report(
        interview=replace(_interview(), selected_rounds=["resume", "technical", "manager", "hr"]),
        resume=_resume(),
        rounds=[completed, early, cancelled, pending],
        effective_history_memory=[],
    )

    assert report["score"] == 32
    assert report["strengths"] == []
    assert report["confidence"] == "medium"
    assert report["final_conclusion"] == "不建议录用"


def test_final_summary_uses_fallback_when_llm_fails() -> None:
    repository = FakeEvaluationRepository()
    service = EvaluationSchedulerService(repository, FakeLLMClient())

    report = service.generate_final_report(
        interview=replace(_interview(), selected_rounds=["resume"]),
        resume=_resume(),
        rounds=[_round(summary={"score": 82, "result": "passed"})],
        effective_history_memory=[],
    )

    assert report["score"] == 82
    assert report["final_conclusion"] == "建议录用"
    assert report["confidence"] == "high"
    records = repository.list_by_interview(1, FINAL_EVALUATION_TYPE)
    assert len(records) == 1
    assert records[0].status == "succeeded"


def repository_record_types(service: EvaluationSchedulerService) -> list[str]:
    repository = service.repository
    assert isinstance(repository, FakeEvaluationRepository)
    return [record.evaluation_type for record in repository.records.values()]


def _resume() -> ResumeRecord:
    return ResumeRecord(id=1, user_id=1, structured_data={"skills": ["Python"]})


def _interview() -> InterviewRecord:
    return InterviewRecord(
        id=1,
        user_id=1,
        resume_id=1,
        target_position="后端开发",
        status="in_progress",
        question_count=1,
        started_at=datetime(2026, 6, 16, 10, 0, 0),
        ended_at=None,
        mode="multi_round",
        job_description="负责后端平台建设",
        overall_status="in_progress",
    )


def _round(summary: dict[str, Any] | None = None) -> InterviewRoundRecord:
    return InterviewRoundRecord(
        id=10,
        interview_id=1,
        agent_type="ResumeInterviewAgent",
        round_type="resume",
        status="completed",
        min_main_questions=1,
        max_main_questions=2,
        min_total_questions=1,
        max_total_questions=3,
        score=82,
        result="passed",
        summary=summary,
        is_reference_only=False,
        started_at=datetime(2026, 6, 16, 10, 0, 0),
        ended_at=datetime(2026, 6, 16, 10, 8, 0),
    )


def _score_answer(
    service: EvaluationSchedulerService,
    answer: str | None,
    qa_id: int,
    question: str,
):
    result = service.score_question(
        interview=_interview(),
        round_record=_round(),
        qa=_qa(answer=answer, qa_id=qa_id, question=question),
        resume=_resume(),
    )
    assert result is not None
    return result


def _quality_payload(
    *,
    correctness: int,
    relevance: int,
    completeness: int,
    logic: int,
    depth: int,
    strengths: list[str],
    issues: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "total_score": 95,
        "dimension_scores": [
            {"dimension": "正确性", "score": correctness, "reason": "按事实与概念准确性评分"},
            {"dimension": "相关性", "score": relevance, "reason": "按是否直接回答问题评分"},
            {"dimension": "完整性", "score": completeness, "reason": "按关键点覆盖程度评分"},
            {"dimension": "逻辑性", "score": logic, "reason": "按结构和因果表达评分"},
            {"dimension": "深度", "score": depth, "reason": "按技术细节、案例和权衡评分"},
        ],
        "strengths": strengths,
        "issues": issues,
        "evidence": evidence,
        "should_follow_up": bool(issues),
        "follow_up_direction": "追问缺失或错误的关键点。" if issues else None,
    }


def _qa(
    answer: str | None,
    qa_id: int = 100,
    sequence: int = 1,
    question: str = "介绍一个项目",
) -> QARecord:
    return QARecord(
        id=qa_id,
        interview_id=1,
        round_id=10,
        sequence=sequence,
        question_type="resume_question",
        question=question,
        answer=answer,
        question_kind="main",
        parent_question_id=None,
        created_at=datetime(2026, 6, 16, 10, 1, 0),
    )
