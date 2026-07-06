from datetime import datetime
from typing import Any

import pytest
from app.repositories.evaluations import EvaluationRecord
from app.repositories.interviews import InterviewRecord, InterviewRoundRecord, ResumeRecord
from app.schemas.evaluation import (
    FinalEvaluationInput,
    QuestionEvaluationInput,
    RoundEvaluationInput,
)
from app.services.evaluations import EvaluationSchedulerService
from pydantic import ValidationError


def test_scoring_input_schemas_reject_candidate_memory_fields() -> None:
    with pytest.raises(ValidationError):
        QuestionEvaluationInput(
            interview_id=1,
            round_id=2,
            question_id=3,
            round_type="technical",
            dimensions=["技术深度"],
            resume={},
            target_position="后端开发",
            question="解释索引",
            answer="回答",
            candidate_memories=[],
        )

    with pytest.raises(ValidationError):
        RoundEvaluationInput(
            interview_id=1,
            round_id=2,
            round_type="technical",
            dimensions=["技术深度"],
            qa_history=[],
            question_evaluations=[],
            candidate_memories=[],
        )

    with pytest.raises(ValidationError):
        FinalEvaluationInput(
            interview_id=1,
            resume_summary={},
            target_position="后端开发",
            round_evaluations=[],
            candidate_memories=[],
        )

    with pytest.raises(ValidationError):
        FinalEvaluationInput(
            interview_id=1,
            resume_summary={},
            target_position="后端开发",
            round_evaluations=[],
            effective_history_memory=[],
        )


def test_final_scoring_payload_does_not_include_memory_fields() -> None:
    llm = _RecordingLLM()
    service = EvaluationSchedulerService(_Repository(), llm)

    service.generate_final_report(
        interview=_interview(),
        resume=_resume(),
        rounds=[_round()],
        effective_history_memory=[{"id": 1, "content": "历史薄弱点"}],
    )

    payload = llm.calls[0]
    assert "candidate_memories" not in payload
    assert "effective_history_memory" not in payload


class _Repository:
    def __init__(self) -> None:
        self.saved: list[EvaluationRecord] = []

    def get_by_key(self, evaluation_type: str, evaluation_key: str) -> EvaluationRecord | None:
        return None

    def list_by_interview(
        self,
        interview_id: int,
        evaluation_type: str | None = None,
        round_id: int | None = None,
    ) -> list[EvaluationRecord]:
        return []

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
            id=1,
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
        self.saved.append(record)
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
        raise AssertionError(error_message)


class _RecordingLLM:
    model_name = "fake-model"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(user_payload)
        return {
            "total_score": 80,
            "round_scores": [
                {
                    "round_type": "technical",
                    "score": 80,
                    "result": "passed",
                    "is_reference_only": False,
                    "status": "completed",
                }
            ],
            "ability_analysis": ["回答完整"],
            "job_match": "匹配",
            "core_strengths": ["基础扎实"],
            "main_risks": ["继续验证深度"],
            "improvement_plan": ["复盘项目细节"],
            "final_conclusion": "建议录用",
            "confidence": "high",
            "reference_note": None,
        }


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


def _round() -> InterviewRoundRecord:
    return InterviewRoundRecord(
        id=10,
        interview_id=1,
        agent_type="TechnicalInterviewAgent",
        round_type="technical",
        status="completed",
        min_main_questions=1,
        max_main_questions=2,
        min_total_questions=1,
        max_total_questions=3,
        score=80,
        result="passed",
        summary={"score": 80, "result": "passed"},
        is_reference_only=False,
        started_at=datetime(2026, 6, 16, 10, 0, 0),
        ended_at=datetime(2026, 6, 16, 10, 8, 0),
    )
