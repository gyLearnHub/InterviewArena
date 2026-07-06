from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.evolution.quality_signals import build_interview_completion_quality_signal
from app.repositories.interviews import (
    FeedbackReportRecord,
    InterviewRecord,
    InterviewRoundRecord,
    QARecord,
)
from app.services.interviews import InterviewService
from test_interview import FakeInterviewRepository, FakeLLMClient


def test_finish_interview_records_completion_quality_signal() -> None:
    repository = _QualitySignalFakeRepository(active_bundle_id=23)
    service, interview = _ready_service(repository)

    report = service.finish_interview(user_id=1, interview_id=interview.id)

    assert report.score == 80
    assert len(repository.quality_signals) == 1
    signal = repository.quality_signals[0]
    assert signal["interview_id"] == interview.id
    assert signal["version_bundle_id"] == 23
    assert signal["signal_type"] == "interview_completed"
    assert signal["metrics"]["score"] == 80
    assert signal["metrics"]["harness_summary"]["failed_hard_rules"] == 0


def test_quality_signal_failure_does_not_block_finish_flow() -> None:
    repository = _FailingQualitySignalFakeRepository(active_bundle_id=23)
    service, interview = _ready_service(repository)

    report = service.finish_interview(user_id=1, interview_id=interview.id)

    assert report.score == 80
    assert repository.get_feedback_report(interview.id) is not None


def test_quality_signal_records_full_v3_2_metrics_and_trigger_codes() -> None:
    interview = InterviewRecord(
        id=42,
        user_id=7,
        resume_id=1,
        target_position="后端开发",
        status="finished",
        question_count=3,
        started_at=None,
        ended_at=datetime.utcnow(),
        job_description="负责 Python API 性能优化",
        overall_status="finished",
        version_bundle_id=23,
    )
    rounds = [
        InterviewRoundRecord(
            id=1,
            interview_id=42,
            agent_type="technical",
            round_type="technical",
            status="completed",
            min_main_questions=2,
            max_main_questions=5,
            min_total_questions=2,
            max_total_questions=8,
            score=88,
            result="pass",
            summary={"summary": "ok"},
            is_reference_only=False,
            started_at=None,
            ended_at=datetime.utcnow(),
        )
    ]
    qa_history = [
        _qa(1, "请介绍一个项目。", "好", question_kind="main"),
        _qa(2, "请介绍一个项目。", "好", question_kind="main"),
        _qa(3, "请介绍一个项目。", None, question_kind="main"),
    ]
    report = FeedbackReportRecord(
        interview_id=42,
        score=88,
        weaknesses=["需要进一步提升。"],
        suggestions=["建议复盘。"],
        recommendation="建议录用",
        report_reliability_status="normal",
    )

    signal = build_interview_completion_quality_signal(
        interview=interview,
        rounds=rounds,
        qa_history=qa_history,
        report=report,
        harness_summary={
            "available": True,
            "total_rules": 1,
            "failed_rules": 0,
            "failed_hard_rules": 0,
            "total_traces": 1,
            "failed_traces": 0,
        },
    )

    assert signal["threshold_trigger"] is True
    assert "question_repeat" in signal["metrics"]["threshold_reason_codes"]
    assert "report_vague" in signal["metrics"]["threshold_reason_codes"]
    assert "empty_answer_high_score" in signal["metrics"]["hard_reason_codes"]
    assert signal["metrics"]["question_quality"]["repeat_count"] == 2
    assert signal["metrics"]["job_match"]["match_score"] < 1


def test_quality_signal_covers_all_v3_2_hard_trigger_sources() -> None:
    interview = InterviewRecord(
        id=43,
        user_id=7,
        resume_id=1,
        target_position="Agent 工程师",
        status="finished",
        question_count=1,
        started_at=None,
        ended_at=datetime.utcnow(),
        overall_status="finished",
        version_bundle_id=23,
    )
    rounds = [
        InterviewRoundRecord(
            id=1,
            interview_id=43,
            agent_type="technical",
            round_type="technical",
            status="completed",
            min_main_questions=1,
            max_main_questions=2,
            min_total_questions=1,
            max_total_questions=3,
            score=85,
            result="pass",
            summary={},
            is_reference_only=False,
            started_at=None,
            ended_at=datetime.utcnow(),
        )
    ]
    report = FeedbackReportRecord(
        interview_id=43,
        score=85,
        weaknesses=[],
        suggestions=[],
        recommendation="建议录用",
        report_reliability_status="normal",
    )

    signal = build_interview_completion_quality_signal(
        interview=interview,
        rounds=rounds,
        qa_history=[_qa(1, "请介绍 Agent 项目。", "", question_kind="main")],
        report=report,
        harness_summary={
            "available": True,
            "failed_hard_rules": 0,
            "failed_traces": 0,
            "llm_output_format_error_count": 1,
            "blocking_degradation_count": 1,
            "negative_feedback_count": 1,
            "agent_overreach_count": 1,
        },
    )

    hard_reasons = set(signal["metrics"]["hard_reason_codes"])

    assert signal["hard_trigger"] is True
    assert {
        "llm_output_format_error",
        "interface_degradation_blocked",
        "user_or_developer_thumbs_down",
        "agent_overreach",
        "empty_answer_high_score",
        "scoring_missing_evidence",
        "report_structure_missing",
    }.issubset(hard_reasons)


def _ready_service(
    repository: _QualitySignalFakeRepository,
) -> tuple[InterviewService, InterviewRecord]:
    repository.add_resume(1, 1)
    service = InterviewService(repository=repository, llm_client=FakeLLMClient())  # type: ignore[arg-type]
    interview = service.create_interview(
        user_id=1,
        resume_id=1,
        target_position="后端开发",
        selected_rounds=["resume"],
    )
    round_record = repository.rounds[interview.id][0]
    qa = repository.create_qa(
        interview_id=interview.id,
        round_id=round_record.id,
        sequence=1,
        question_type="skill_check",
        question="请介绍一个项目。",
    )
    repository.update_answer(qa.id, "我做过一个后端项目。")
    repository.rounds[interview.id] = [
        InterviewRoundRecord(
            **{
                **round_record.__dict__,
                "status": "completed",
                "score": 80,
                "result": "pass",
                "summary": {
                    "score": 80,
                    "result": "pass",
                    "summary": "证据充分。",
                    "is_reference_only": False,
                },
                "ended_at": datetime.utcnow(),
            }
        )
    ]
    stored = repository.interviews[interview.id]
    repository.interviews[interview.id] = InterviewRecord(
        **{**stored.__dict__, "question_count": 1}
    )
    return service, repository.interviews[interview.id]


class _QualitySignalFakeRepository(FakeInterviewRepository):
    def __init__(self, *, active_bundle_id: int) -> None:
        super().__init__()
        self.active_bundle_id = active_bundle_id
        self.quality_signals: list[dict[str, Any]] = []

    def get_active_version_bundle(
        self,
        *,
        scope_type: str = "global",
        scope_key: str | None = None,
    ) -> Any:
        return SimpleNamespace(id=self.active_bundle_id)

    def get_or_create_active_default_version_bundle(self) -> Any:
        return SimpleNamespace(id=self.active_bundle_id)

    def create_interview(
        self,
        user_id: int,
        resume_id: int,
        target_position: str,
        mode: str = "multi_round",
        job_description: str | None = None,
        selected_rounds: list[str] | None = None,
        version_bundle_id: int | None = None,
    ) -> InterviewRecord:
        interview = super().create_interview(
            user_id=user_id,
            resume_id=resume_id,
            target_position=target_position,
            mode=mode,
            job_description=job_description,
            selected_rounds=selected_rounds,
        )
        interview = InterviewRecord(
            **{**interview.__dict__, "version_bundle_id": version_bundle_id}
        )
        self.interviews[interview.id] = interview
        return interview

    def get_interview_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> InterviewRecord | None:
        return super().get_interview_for_user(interview_id, user_id)

    def get_interview_harness_summary(self, interview_id: int) -> dict[str, Any]:
        return {
            "available": True,
            "total_rules": 2,
            "failed_rules": 0,
            "failed_hard_rules": 0,
            "total_traces": 1,
            "failed_traces": 0,
        }

    def create_quality_signal(self, **payload: Any) -> Any:
        self.quality_signals.append(payload)
        return payload

    def create_quality_signal_idempotent(self, **payload: Any) -> Any:
        existing = next(
            (
                item
                for item in self.quality_signals
                if item["interview_id"] == payload["interview_id"]
                and item["signal_type"] == payload["signal_type"]
            ),
            None,
        )
        if existing is not None:
            return existing
        return self.create_quality_signal(**payload)


class _FailingQualitySignalFakeRepository(_QualitySignalFakeRepository):
    def create_quality_signal(self, **payload: Any) -> Any:
        raise RuntimeError("quality signal unavailable")

    def create_quality_signal_idempotent(self, **payload: Any) -> Any:
        raise RuntimeError("quality signal unavailable")


def _qa(
    qa_id: int,
    question: str,
    answer: str | None,
    *,
    question_kind: str,
) -> Any:
    return QARecord(
        id=qa_id,
        interview_id=42,
        sequence=qa_id,
        question_type="skill_check",
        question=question,
        answer=answer,
        created_at=datetime.utcnow(),
        round_id=1,
        question_kind=question_kind,
        question_status="active",
    )
