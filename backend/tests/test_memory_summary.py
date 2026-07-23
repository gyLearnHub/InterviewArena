import importlib
import inspect
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.schemas.memory import MemorySummaryOutput
from app.services.interviews import InterviewService
from app.services.memory_summary import MAX_TEXT_LENGTH, MemorySummaryService
from pydantic import ValidationError


def test_memory_summary_service_rejects_invalid_llm_output_contract() -> None:
    with pytest.raises(ValidationError):
        MemorySummaryOutput.model_validate(
            {
                "candidate_memories": [
                    {
                        "collection": "candidate_memories",
                        "memory_type": "technical_weakness",
                        "title": "",
                        "content": "",
                        "confidence": 1.5,
                    }
                ]
            }
        )


def test_memory_summary_service_exists() -> None:
    module = importlib.import_module("app.services.memory_summary")

    assert hasattr(module, "MemorySummaryService")
    assert hasattr(module, "MemorySummaryOutput")


def test_finish_interview_creates_summary_task_after_report_when_memory_enabled() -> None:
    source = inspect.getsource(InterviewService.finish_multi_round_interview)

    assert "create_feedback_report" in source
    assert "memory_enabled" in source
    assert "memory_summary" in source
    assert source.index("create_feedback_report") < source.index("memory_summary")


def test_memory_summary_payload_is_compact_and_schema_oriented() -> None:
    llm = _CapturingLLM()
    service = MemorySummaryService(
        interview_repository=_InterviewRepo(),
        evaluation_repository=_EvaluationRepo(),
        lifecycle_service=_Lifecycle(),
        llm_client=llm,
    )

    result = service.summarize_interview(user_id=1, interview_id=22)

    assert result == {"created_or_updated": 0}
    assert llm.payloads
    payload = llm.payloads[0]
    assert "created_at" not in payload["qa_history"][0]
    assert "started_at" not in payload["rounds"][0]
    assert len(payload["qa_history"][0]["answer"]) == MAX_TEXT_LENGTH
    assert payload["rounds"][0]["summary"] == {"score": 0, "result": "failed"}
    assert payload["evaluations"][0]["evidence"] == ["证据"]
    assert all(
        item["evaluation_type"] != "question_reanswer" for item in payload["evaluations"]
    )
    assert "unused_large_blob" not in payload["resume_summary"]


def test_memory_summary_retries_with_focused_payload_when_evidence_returns_empty() -> None:
    llm = _CapturingLLM(
        results=[
            _empty_summary(),
            _candidate_summary(),
        ]
    )
    lifecycle = _RecordingLifecycle()
    service = MemorySummaryService(
        interview_repository=_InterviewRepo(),
        evaluation_repository=_EvaluationRepo(),
        lifecycle_service=lifecycle,
        llm_client=llm,
    )

    result = service.summarize_interview(user_id=1, interview_id=22)

    assert result == {"created_or_updated": 1}
    assert len(llm.payloads) == 2
    assert "qa_history" in llm.payloads[0]
    assert "qa_evidence" in llm.payloads[1]
    assert lifecycle.upserts[0]["user_id"] == 1
    assert lifecycle.upserts[0]["item"].memory_type == "technical_weakness"


def test_memory_summary_adds_candidate_retry_when_focused_output_is_agent_only() -> None:
    llm = _CapturingLLM(
        results=[
            _empty_summary(),
            {
                "candidate_memories": [],
                "interviewer_memories": [],
                "agent_memories": [
                    {
                        "collection": "agent_memories",
                        "memory_type": "anomaly",
                        "title": "答案存在异常字符",
                        "content": "多轮回答包含不可解析内容。",
                        "structured_data": {"evidence": ["不可解析"]},
                        "confidence": 0.6,
                    }
                ],
            },
            _candidate_summary(),
        ]
    )
    lifecycle = _RecordingLifecycle()
    service = MemorySummaryService(
        interview_repository=_InterviewRepo(),
        evaluation_repository=_EvaluationRepo(),
        lifecycle_service=lifecycle,
        llm_client=llm,
    )

    result = service.summarize_interview(user_id=1, interview_id=22)

    assert result == {"created_or_updated": 2}
    assert len(llm.payloads) == 3
    assert lifecycle.upserts[0]["user_id"] == 1
    assert lifecycle.upserts[0]["item"].collection == "candidate_memories"
    assert lifecycle.upserts[1]["user_id"] is None
    assert lifecycle.upserts[1]["item"].collection == "agent_memories"


class _CapturingLLM:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.results = results or [_empty_summary()]

    def generate_json(self, _system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(user_payload)
        index = min(len(self.payloads) - 1, len(self.results) - 1)
        return self.results[index]


class _InterviewRepo:
    def get_interview_for_user(self, _interview_id: int, _user_id: int) -> Any:
        return SimpleNamespace(
            id=22,
            resume_id=5,
            target_position="后端开发",
            job_description="负责 API",
            selected_rounds=["resume", "technical"],
        )

    def get_resume_for_user(self, _resume_id: int, _user_id: int) -> Any:
        return SimpleNamespace(
            structured_data={
                "basic_info": {"name": "候选人"},
                "skills": ["Python"],
                "unused_large_blob": "x" * 5000,
            }
        )

    def list_rounds(self, _interview_id: int) -> list[Any]:
        return [
            SimpleNamespace(
                id=61,
                round_type="technical",
                agent_type="technical",
                status="finished",
                score=0,
                result="failed",
                summary={"score": 0, "result": "failed"},
                started_at=datetime(2026, 1, 1),
            )
        ]

    def list_qa(self, _interview_id: int) -> list[Any]:
        return [
            SimpleNamespace(
                id=76,
                round_id=61,
                sequence=1,
                question_type="technical",
                question_kind="main",
                parent_question_id=None,
                question="请说明项目。",
                answer="答" * (MAX_TEXT_LENGTH + 50),
                created_at=datetime(2026, 1, 1),
            )
        ]


class _EvaluationRepo:
    def list_by_interview(self, _interview_id: int) -> list[Any]:
        return [
            SimpleNamespace(
                id=101,
                evaluation_type="round",
                evaluation_key="round-61",
                round_id=61,
                question_id=None,
                status="succeeded",
                total_score=0,
                evidence=["证据"],
                dimension_scores=[{"name": "技术", "score": 0}],
                result={"summary": "表现不足"},
                created_at=datetime(2026, 1, 1),
            ),
            SimpleNamespace(
                id=102,
                evaluation_type="question_reanswer",
                evaluation_key="22:61:76:reanswer:1",
                round_id=61,
                question_id=76,
                status="succeeded",
                total_score=95,
                evidence=["重答证据不属于原面试表现"],
                dimension_scores=[{"name": "技术", "score": 95}],
                result={"summary": "重答表现"},
                created_at=datetime(2026, 1, 2),
            ),
        ]


class _Lifecycle:
    def upsert_memory(self, **_kwargs: Any) -> None:
        raise AssertionError("empty memory output should not upsert")


class _RecordingLifecycle:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert_memory(self, **kwargs: Any) -> None:
        self.upserts.append(kwargs)


def _empty_summary() -> dict[str, Any]:
    return {
        "candidate_memories": [],
        "interviewer_memories": [],
        "agent_memories": [],
    }


def _candidate_summary() -> dict[str, Any]:
    return {
        "candidate_memories": [
            {
                "collection": "candidate_memories",
                "memory_type": "interview_weakness",
                "title": "回答与问题匹配度不足",
                "content": "多轮回答被评估为与问题无关或缺少有效技术信息。",
                "structured_data": {"evidence": ["问题级评估显示回答无关"]},
                "confidence": 0.78,
                "source_round_id": 61,
            }
        ],
        "interviewer_memories": [],
        "agent_memories": [],
    }
