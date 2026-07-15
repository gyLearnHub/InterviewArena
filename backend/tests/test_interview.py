from datetime import datetime, timedelta
from typing import Any

import app.api.interviews as interviews_api_module
import app.services.interviews as interviews_module
import pytest
from app.api.interviews import get_interview_service
from app.core.errors import AppError, ErrorCode
from app.deps import get_current_user
from app.repositories.interviews import (
    AnswerDraftRecord,
    FeedbackReportRecord,
    InterviewRecord,
    InterviewRepository,
    InterviewRoundRecord,
    QARecord,
    ResumeRecord,
    WeaknessPracticeProgressRecord,
)
from app.repositories.users import UserRecord
from app.schemas.evaluation import DimensionScore, QuestionEvaluationOutput
from app.schemas.interview import (
    JOB_DESCRIPTION_MAX_LENGTH,
    ROUND_ANSWER_MAX_LENGTH,
    InterviewCreateRequest,
    RoundAnswerRequest,
)
from app.services.interviews import InterviewService
from fastapi.testclient import TestClient
from main import create_app
from pydantic import ValidationError


class DuplicateKeyError(Exception):
    def __init__(self) -> None:
        super().__init__(1062, "Duplicate entry")


class FakeInterviewRepository:
    def __init__(self) -> None:
        self.resumes: dict[int, ResumeRecord] = {}
        self.interviews: dict[int, InterviewRecord] = {}
        self.rounds: dict[int, list[InterviewRoundRecord]] = {}
        self.qa: dict[int, list[QARecord]] = {}
        self.answer_drafts: dict[tuple[int, int, int, int], AnswerDraftRecord] = {}
        self.feedback_reports: list[FeedbackReportRecord] = []
        self.practice_progress: list[WeaknessPracticeProgressRecord] = []
        self.next_interview_id = 1
        self.next_round_id = 1
        self.next_qa_id = 1
        self.next_practice_progress_id = 1
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def add_resume(self, resume_id: int, user_id: int) -> None:
        self.resumes[resume_id] = ResumeRecord(
            id=resume_id,
            user_id=user_id,
            structured_data={"skills": ["Python"]},
        )

    def get_resume_for_user(self, resume_id: int, user_id: int) -> ResumeRecord | None:
        resume = self.resumes.get(resume_id)
        if resume is None or resume.user_id != user_id:
            return None
        return resume

    def create_interview(
        self,
        user_id: int,
        resume_id: int,
        target_position: str,
        mode: str = "multi_round",
        job_description: str | None = None,
        selected_rounds: list[str] | None = None,
        interview_goal: str = "campus",
        difficulty: str = "normal",
        time_limit_minutes: int = 45,
    ) -> InterviewRecord:
        interview = InterviewRecord(
            id=self.next_interview_id,
            user_id=user_id,
            resume_id=resume_id,
            target_position=target_position,
            status="created",
            question_count=0,
            started_at=None,
            ended_at=None,
            mode=mode,
            job_description=job_description,
            selected_rounds=selected_rounds,
            interview_goal=interview_goal,
            difficulty=difficulty,
            time_limit_minutes=time_limit_minutes,
            overall_status="created",
        )
        self.next_interview_id += 1
        self.interviews[interview.id] = interview
        self.qa[interview.id] = []
        self.rounds[interview.id] = []
        return interview

    def get_interview_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> InterviewRecord | None:
        interview = self.interviews.get(interview_id)
        if interview is None or interview.user_id != user_id:
            return None
        return interview

    def update_question_count(self, interview_id: int, question_count: int) -> None:
        interview = self.interviews[interview_id]
        self.interviews[interview_id] = InterviewRecord(
            **{**interview.__dict__, "question_count": question_count}
        )

    def create_qa(
        self,
        interview_id: int,
        sequence: int,
        question_type: str,
        question: str,
        round_id: int | None = None,
        question_kind: str = "main",
        parent_question_id: int | None = None,
        regenerated_from_question_id: int | None = None,
    ) -> QARecord:
        if self.get_round_qa_by_sequence(interview_id, round_id, sequence) is not None:
            raise DuplicateKeyError()
        qa = QARecord(
            id=self.next_qa_id,
            interview_id=interview_id,
            sequence=sequence,
            question_type=question_type,
            question=question,
            answer=None,
            created_at=datetime.utcnow(),
            round_id=round_id,
            question_kind=question_kind,
            question_status="active",
            parent_question_id=parent_question_id,
            regenerated_from_question_id=regenerated_from_question_id,
        )
        self.next_qa_id += 1
        self.qa[interview_id].append(qa)
        return qa

    def create_qa_idempotent(
        self,
        interview_id: int,
        sequence: int,
        question_type: str,
        question: str,
        round_id: int | None = None,
        question_kind: str = "main",
        parent_question_id: int | None = None,
        regenerated_from_question_id: int | None = None,
    ) -> QARecord:
        try:
            return self.create_qa(
                interview_id=interview_id,
                sequence=sequence,
                question_type=question_type,
                question=question,
                round_id=round_id,
                question_kind=question_kind,
                parent_question_id=parent_question_id,
                regenerated_from_question_id=regenerated_from_question_id,
            )
        except DuplicateKeyError:
            existing = self.get_round_qa_by_sequence(interview_id, round_id, sequence)
            if existing is None:
                raise
            return existing

    def update_answer(self, qa_id: int, answer: str) -> bool:
        updated = False
        for interview_id, records in self.qa.items():
            self.qa[interview_id] = [
                QARecord(**{**qa.__dict__, "answer": answer})
                if qa.id == qa_id and qa.answer is None and qa.question_status == "active"
                else qa
                for qa in records
            ]
            if any(
                qa.id == qa_id and qa.answer is None and qa.question_status == "active"
                for qa in records
            ):
                updated = True
        return updated

    def update_question_status(self, qa_id: int, question_status: str) -> bool:
        updated = False
        for interview_id, records in self.qa.items():
            next_records: list[QARecord] = []
            for qa in records:
                if qa.id == qa_id and qa.answer is None and qa.question_status == "active":
                    next_records.append(
                        QARecord(**{**qa.__dict__, "question_status": question_status})
                    )
                    updated = True
                else:
                    next_records.append(qa)
            self.qa[interview_id] = next_records
        return updated

    def list_qa(self, interview_id: int, include_inactive: bool = False) -> list[QARecord]:
        records = list(self.qa[interview_id])
        if include_inactive:
            return records
        return [qa for qa in records if qa.question_status == "active"]

    def get_round_qa_by_sequence(
        self,
        interview_id: int,
        round_id: int | None,
        sequence: int,
    ) -> QARecord | None:
        return next(
            (
                qa
                for qa in self.qa[interview_id]
                if qa.round_id == round_id and qa.sequence == sequence
            ),
            None,
        )

    def create_rounds(self, rounds: list[dict[str, Any]]) -> list[InterviewRoundRecord]:
        created: list[InterviewRoundRecord] = []
        for item in rounds:
            round_record = InterviewRoundRecord(
                id=self.next_round_id,
                interview_id=int(item["interview_id"]),
                agent_type=str(item["agent_type"]),
                round_type=str(item["round_type"]),
                status=str(item["status"]),
                min_main_questions=int(item["min_main_questions"]),
                max_main_questions=int(item["max_main_questions"]),
                min_total_questions=int(item["min_total_questions"]),
                max_total_questions=int(item["max_total_questions"]),
                score=None,
                result=None,
                summary=None,
                is_reference_only=False,
                started_at=None,
                ended_at=None,
            )
            self.next_round_id += 1
            self.rounds[round_record.interview_id].append(round_record)
            created.append(round_record)
        return created

    def list_rounds(self, interview_id: int) -> list[InterviewRoundRecord]:
        return list(self.rounds[interview_id])

    def get_round(self, interview_id: int, round_id: int) -> InterviewRoundRecord | None:
        return next((item for item in self.rounds[interview_id] if item.id == round_id), None)

    def configure_round(
        self,
        interview_id: int,
        round_id: int,
        difficulty: str,
        time_limit_minutes: int,
    ) -> None:
        self.rounds[interview_id] = [
            InterviewRoundRecord(
                **{
                    **item.__dict__,
                    "difficulty": difficulty,
                    "time_limit_minutes": time_limit_minutes,
                }
            )
            if item.id == round_id and item.status == "pending"
            else item
            for item in self.rounds[interview_id]
        ]

    def mark_round_started(
        self,
        interview_id: int,
        round_id: int,
        round_type: str,
        started_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        self.rounds[interview_id] = [
            InterviewRoundRecord(
                **{
                    **item.__dict__,
                    "status": "in_progress",
                    "started_at": item.started_at or started_at,
                }
            )
            if item.id == round_id
            else item
            for item in self.rounds[interview_id]
        ]
        interview = self.interviews[interview_id]
        finished_round = self.get_round(interview_id, round_id)
        if finished_round is not None and interview.current_round == finished_round.round_type:
            self.interviews[interview_id] = InterviewRecord(
                **{**interview.__dict__, "current_round": None}
            )
        interview = self.interviews[interview_id]
        self.interviews[interview_id] = InterviewRecord(
            **{
                **interview.__dict__,
                "status": "in_progress",
                "overall_status": "in_progress",
                "current_round": round_type,
                "started_at": interview.started_at or started_at,
                "last_active_at": started_at,
                "elapsed_seconds": elapsed_seconds,
            }
        )

    def touch_interview(
        self,
        interview_id: int,
        last_active_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        interview = self.interviews[interview_id]
        self.interviews[interview_id] = InterviewRecord(
            **{
                **interview.__dict__,
                "last_active_at": last_active_at,
                "elapsed_seconds": elapsed_seconds,
            }
        )

    def pause_interview(
        self,
        interview_id: int,
        paused_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        interview = self.interviews[interview_id]
        self.interviews[interview_id] = InterviewRecord(
            **{
                **interview.__dict__,
                "status": "paused",
                "overall_status": "paused",
                "last_active_at": paused_at,
                "elapsed_seconds": elapsed_seconds,
            }
        )

    def resume_interview(
        self,
        interview_id: int,
        resumed_at: datetime,
        paused_at: datetime | None,
    ) -> None:
        interview = self.interviews[interview_id]
        paused_seconds = (
            max(0, int((resumed_at - paused_at).total_seconds())) if paused_at is not None else 0
        )
        self.rounds[interview_id] = [
            InterviewRoundRecord(
                **{
                    **item.__dict__,
                    "started_at": (
                        item.started_at + timedelta(seconds=paused_seconds)
                        if item.status == "in_progress"
                        and item.round_type == interview.current_round
                        and item.started_at is not None
                        else item.started_at
                    ),
                }
            )
            for item in self.rounds[interview_id]
        ]
        self.interviews[interview_id] = InterviewRecord(
            **{
                **interview.__dict__,
                "status": "in_progress",
                "overall_status": "in_progress",
                "last_active_at": resumed_at,
            }
        )

    def get_round_qa_by_id(
        self,
        interview_id: int,
        round_id: int,
        qa_id: int,
    ) -> QARecord | None:
        return next(
            (qa for qa in self.qa[interview_id] if qa.id == qa_id and qa.round_id == round_id),
            None,
        )

    def list_round_qa(
        self,
        interview_id: int,
        round_id: int,
        include_inactive: bool = False,
    ) -> list[QARecord]:
        records = [qa for qa in self.qa[interview_id] if qa.round_id == round_id]
        if include_inactive:
            return records
        return [qa for qa in records if qa.question_status == "active"]

    def get_unanswered_round_question(
        self,
        interview_id: int,
        round_id: int,
    ) -> QARecord | None:
        unanswered = [
            qa
            for qa in self.qa[interview_id]
            if qa.round_id == round_id and qa.answer is None and qa.question_status == "active"
        ]
        return unanswered[-1] if unanswered else None

    def get_answer_draft(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> AnswerDraftRecord | None:
        return self.answer_drafts.get((user_id, interview_id, round_id, question_id))

    def upsert_answer_draft(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
        answer: str,
    ) -> AnswerDraftRecord:
        record = AnswerDraftRecord(
            user_id=user_id,
            interview_id=interview_id,
            round_id=round_id,
            question_id=question_id,
            answer=answer,
            updated_at=datetime.utcnow(),
        )
        self.answer_drafts[(user_id, interview_id, round_id, question_id)] = record
        return record

    def delete_answer_draft(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> None:
        self.answer_drafts.pop((user_id, interview_id, round_id, question_id), None)

    def finish_round(
        self,
        interview_id: int,
        round_id: int,
        status: str,
        summary: dict[str, Any],
        ended_at: datetime,
    ) -> None:
        self.rounds[interview_id] = [
            InterviewRoundRecord(
                **{
                    **item.__dict__,
                    "status": status,
                    "score": summary["score"],
                    "result": summary["result"],
                    "summary": summary,
                    "is_reference_only": bool(summary["is_reference_only"]),
                    "ended_at": ended_at,
                }
            )
            if item.id == round_id
            else item
            for item in self.rounds[interview_id]
        ]
        interview = self.interviews[interview_id]
        finished_round = self.get_round(interview_id, round_id)
        if finished_round is not None and interview.current_round == finished_round.round_type:
            self.interviews[interview_id] = InterviewRecord(
                **{**interview.__dict__, "current_round": None}
            )

    def cancel_pending_rounds(self, interview_id: int) -> None:
        self.rounds[interview_id] = [
            InterviewRoundRecord(**{**item.__dict__, "status": "cancelled"})
            if item.status == "pending"
            else item
            for item in self.rounds[interview_id]
        ]

    def mark_multi_finished(
        self,
        interview_id: int,
        ended_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        interview = self.interviews[interview_id]
        self.interviews[interview_id] = InterviewRecord(
            **{
                **interview.__dict__,
                "status": "finished",
                "overall_status": "finished",
                "current_round": None,
                "ended_at": ended_at,
                "last_active_at": ended_at,
                "elapsed_seconds": elapsed_seconds,
            }
        )

    def update_interview_harness(
        self,
        interview_id: int,
        *,
        harness_status: str | None = None,
        last_checkpoint_id: int | None = None,
        recovery_count: int | None = None,
        last_recovered_at: datetime | None = None,
        last_harness_error: str | None = None,
        had_degradation: bool | None = None,
    ) -> None:
        interview = self.interviews[interview_id]
        values: dict[str, Any] = {}
        if harness_status is not None:
            values["harness_status"] = harness_status
        if last_checkpoint_id is not None:
            values["last_checkpoint_id"] = last_checkpoint_id
        if recovery_count is not None:
            values["recovery_count"] = recovery_count
        if last_recovered_at is not None:
            values["last_recovered_at"] = last_recovered_at
        if last_harness_error is not None:
            values["last_harness_error"] = last_harness_error
        if had_degradation is not None:
            values["had_degradation"] = had_degradation
        self.interviews[interview_id] = InterviewRecord(**{**interview.__dict__, **values})

    def update_round_execution(
        self,
        round_id: int,
        *,
        execution_status: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        for interview_id, rounds in self.rounds.items():
            self.rounds[interview_id] = [
                InterviewRoundRecord(
                    **{
                        **item.__dict__,
                        **(
                            {"execution_status": execution_status}
                            if execution_status is not None and item.id == round_id
                            else {}
                        ),
                        **(
                            {"retry_count": retry_count}
                            if retry_count is not None and item.id == round_id
                            else {}
                        ),
                    }
                )
                if item.id == round_id
                else item
                for item in rounds
            ]

    def create_feedback_report(
        self,
        interview_id: int,
        score: int,
        weaknesses: list[str],
        suggestions: list[str],
        recommendation: str | None = None,
        round_scores: list[dict[str, Any]] | None = None,
        strengths: list[str] | None = None,
        ability_analysis: list[str] | None = None,
        job_match: str | None = None,
        final_conclusion: str | None = None,
        confidence: str | None = None,
        reference_note: str | None = None,
        used_candidate_memory: bool = False,
        report_reliability_status: str = "normal",
    ) -> FeedbackReportRecord:
        if self.get_feedback_report(interview_id) is not None:
            raise DuplicateKeyError()
        report = FeedbackReportRecord(
            interview_id=interview_id,
            score=score,
            weaknesses=weaknesses,
            suggestions=suggestions,
            recommendation=recommendation,
            round_scores=round_scores,
            strengths=strengths,
            ability_analysis=ability_analysis,
            job_match=job_match,
            final_conclusion=final_conclusion,
            confidence=confidence,
            reference_note=reference_note,
            used_candidate_memory=used_candidate_memory,
            report_reliability_status=report_reliability_status,
        )
        self.feedback_reports.append(report)
        return report

    def create_feedback_report_idempotent(
        self,
        interview_id: int,
        score: int,
        weaknesses: list[str],
        suggestions: list[str],
        recommendation: str | None = None,
        round_scores: list[dict[str, Any]] | None = None,
        strengths: list[str] | None = None,
        ability_analysis: list[str] | None = None,
        job_match: str | None = None,
        final_conclusion: str | None = None,
        confidence: str | None = None,
        reference_note: str | None = None,
        used_candidate_memory: bool = False,
        report_reliability_status: str = "normal",
    ) -> FeedbackReportRecord:
        try:
            return self.create_feedback_report(
                interview_id=interview_id,
                score=score,
                weaknesses=weaknesses,
                suggestions=suggestions,
                recommendation=recommendation,
                round_scores=round_scores,
                strengths=strengths,
                ability_analysis=ability_analysis,
                job_match=job_match,
                final_conclusion=final_conclusion,
                confidence=confidence,
                reference_note=reference_note,
                used_candidate_memory=used_candidate_memory,
                report_reliability_status=report_reliability_status,
            )
        except DuplicateKeyError:
            existing = self.get_feedback_report(interview_id)
            if existing is None:
                raise
            return existing

    def get_feedback_report(self, interview_id: int) -> FeedbackReportRecord | None:
        return next(
            (report for report in self.feedback_reports if report.interview_id == interview_id),
            None,
        )

    def create_weakness_practice_progress(
        self,
        *,
        user_id: int,
        source_interview_id: int,
        practice_interview_id: int,
        weakness_title: str,
        weakness_key: str,
        suggestion: str | None,
        round_type: str | None,
        source_score: int | None,
    ) -> WeaknessPracticeProgressRecord:
        now = datetime.utcnow()
        record = WeaknessPracticeProgressRecord(
            id=self.next_practice_progress_id,
            user_id=user_id,
            source_interview_id=source_interview_id,
            practice_interview_id=practice_interview_id,
            weakness_title=weakness_title,
            weakness_key=weakness_key,
            suggestion=suggestion,
            round_type=round_type,
            status="pending",
            source_score=source_score,
            created_at=now,
            updated_at=now,
        )
        self.next_practice_progress_id += 1
        self.practice_progress.append(record)
        return record

    def get_weakness_practice_progress_by_practice(
        self,
        practice_interview_id: int,
    ) -> WeaknessPracticeProgressRecord | None:
        return next(
            (
                record
                for record in self.practice_progress
                if record.practice_interview_id == practice_interview_id
            ),
            None,
        )

    def update_weakness_practice_progress_result(
        self,
        *,
        practice_interview_id: int,
        status: str,
        practice_score: int,
        last_practiced_at: datetime,
    ) -> None:
        self.practice_progress = [
            WeaknessPracticeProgressRecord(
                **{
                    **record.__dict__,
                    "status": status,
                    "practice_score": practice_score,
                    "last_practiced_at": last_practiced_at,
                    "updated_at": datetime.utcnow(),
                }
            )
            if record.practice_interview_id == practice_interview_id
            else record
            for record in self.practice_progress
        ]


class FakeLLMClient:
    def __init__(self) -> None:
        self.question_number = 0
        self.question_resume_payloads: list[dict[str, Any]] = []

    def parse_resume(self, resume_text: str) -> dict[str, Any]:
        return {}

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.question_number += 1
        self.question_resume_payloads.append(resume)
        return {
            "question_type": "skill_check",
            "question": f"问题 {self.question_number}",
        }

    def generate_feedback(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {"score": 90, "weaknesses": [], "suggestions": []}


class FlakyQuestionLLMClient(FakeLLMClient):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise AppError(ErrorCode.LLM_API_KEY_MISSING)
        return super().generate_question(
            resume=resume,
            target_position=target_position,
            qa_history=qa_history,
            previous_answer=previous_answer,
            system_prompt=system_prompt,
        )


class RecoverableNextQuestionLLMClient(FakeLLMClient):
    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.question_number >= 1:
            raise AppError(ErrorCode.BUSINESS_ERROR, 502)
        return super().generate_question(
            resume=resume,
            target_position=target_position,
            qa_history=qa_history,
            previous_answer=previous_answer,
            system_prompt=system_prompt,
        )


class FailingNextQuestionLLMClient(FakeLLMClient):
    def __init__(self, repository: FakeInterviewRepository) -> None:
        super().__init__()
        self.repository = repository
        self.answer_commit_count: int | None = None

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.question_number >= 1:
            self.answer_commit_count = self.repository.commit_count
            raise RuntimeError("next_question_failed")
        return super().generate_question(
            resume=resume,
            target_position=target_position,
            qa_history=qa_history,
            previous_answer=previous_answer,
            system_prompt=system_prompt,
        )


class GuardedInterviewService:
    def __init__(self) -> None:
        self.create_interview_calls = 0

    def create_interview(self, *args: Any, **kwargs: Any) -> Any:
        self.create_interview_calls += 1
        raise AssertionError("create_interview should not run for invalid request bodies")


class FakeQuestionEvaluationService:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def score_question(self, **kwargs: Any) -> QuestionEvaluationOutput:
        qa = kwargs["qa"]
        self.calls.append(qa.id)
        return QuestionEvaluationOutput(
            total_score=74,
            dimension_scores=[
                DimensionScore(
                    dimension="回答质量",
                    score=74,
                    reason="回答有基础结构，但结果和取舍还可以更具体。",
                )
            ],
            strengths=["能说明自己的处理思路。"],
            issues=["缺少量化结果。", "技术取舍还可以更明确。"],
            evidence=["回答提到了推进方案。"],
            should_follow_up=True,
            follow_up_direction="追问项目结果和方案取舍。",
        )


def make_service(
    llm_client: FakeLLMClient | None = None,
    evaluation_service: Any | None = None,
) -> tuple[InterviewService, FakeInterviewRepository]:
    repository = FakeInterviewRepository()
    return (
        InterviewService(
            repository=repository,  # type: ignore[arg-type]
            llm_client=llm_client or FakeLLMClient(),
            evaluation_service=evaluation_service,
        ),
        repository,
    )


def _interview_api_client(
    service: GuardedInterviewService,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        id=1,
        username="alice",
        password_hash="hash",
    )
    app.dependency_overrides[get_interview_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def _validation_fields(response: Any) -> set[str]:
    return {
        str(part) for error in response.json()["error"]["details"] for part in error.get("loc", [])
    }


class _SqlCaptureConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def cursor(self) -> "_SqlCaptureConnection":
        return self

    def __enter__(self) -> "_SqlCaptureConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchone(self) -> Any:
        return None


def test_create_interview_requires_owned_resume() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=2)

    with pytest.raises(AppError) as exc_info:
        service.create_interview(user_id=1, resume_id=1, target_position="后端开发")

    assert exc_info.value.code == ErrorCode.FORBIDDEN


def test_resume_lookup_excludes_soft_deleted_rows() -> None:
    connection = _SqlCaptureConnection()
    repository = InterviewRepository(connection)

    assert repository.get_resume_for_user(resume_id=1, user_id=1) is None

    assert "deleted_at is null" in connection.sql.lower()
    assert connection.params == (1, 1)


def test_create_interview_rejects_oversized_job_description() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    with pytest.raises(AppError) as exc_info:
        service.create_interview(
            user_id=1,
            resume_id=1,
            target_position="后端开发",
            job_description="J" * (JOB_DESCRIPTION_MAX_LENGTH + 1),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert repository.interviews == {}


def test_interview_request_schemas_reject_oversized_text() -> None:
    with pytest.raises(ValidationError):
        InterviewCreateRequest(
            resume_id=1,
            target_position="后端开发",
            job_description="J" * (JOB_DESCRIPTION_MAX_LENGTH + 1),
        )

    with pytest.raises(ValidationError):
        RoundAnswerRequest(
            question_id=1,
            answer="A" * (ROUND_ANSWER_MAX_LENGTH + 1),
        )


def test_create_interview_endpoint_rejects_oversized_job_description_before_service() -> None:
    service = GuardedInterviewService()
    client = _interview_api_client(service)

    response = client.post(
        "/api/interviews",
        json={
            "resume_id": 1,
            "target_position": "后端开发",
            "job_description": "J" * (JOB_DESCRIPTION_MAX_LENGTH + 1),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
    assert "job_description" in _validation_fields(response)
    assert service.create_interview_calls == 0


def test_create_interview_endpoint_queues_evolution_binding_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    queued: list[dict[str, Any]] = []

    def fake_binding_task(**payload: Any) -> None:
        queued.append(payload)

    monkeypatch.setattr(
        interviews_api_module,
        "prepare_interview_evolution_context_task",
        fake_binding_task,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        id=1,
        username="alice",
        password_hash="hash",
    )
    app.dependency_overrides[get_interview_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/interviews",
        json={"resume_id": 1, "target_position": "后端开发"},
    )

    assert response.status_code == 200
    assert queued == [
        {
            "user_id": 1,
            "interview_id": 1,
            "target_position": "后端开发",
            "job_description": None,
        }
    ]


def test_create_multi_round_interview_defaults_to_all_rounds() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    interview = service.create_interview(1, 1, "后端开发")
    rounds = repository.list_rounds(interview.id)

    assert interview.mode == "multi_round"
    assert interview.interview_goal == "campus"
    assert interview.difficulty == "normal"
    assert interview.time_limit_minutes == 45
    assert [item.round_type for item in rounds] == ["resume", "technical", "manager", "hr"]
    assert [item.status for item in rounds] == ["pending", "pending", "pending", "pending"]


def test_create_interview_does_not_run_evolution_classification_synchronously() -> None:
    class ClassificationGuardLLM(FakeLLMClient):
        def generate_json(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("create_interview should not call evolution classification")

    service, repository = make_service(ClassificationGuardLLM())
    repository.add_resume(resume_id=1, user_id=1)

    interview = service.create_interview(1, 1, "后端开发")

    assert interview.id == 1
    assert interview.job_family_key is None
    assert repository.list_rounds(interview.id)


def test_create_interview_saves_strategy_configuration() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    interview = service.create_interview(
        1,
        1,
        "后端开发",
        interview_goal="big_tech",
        difficulty="pressure",
        time_limit_minutes=60,
    )

    state = service.get_state(1, interview.id)

    assert repository.interviews[interview.id].interview_goal == "big_tech"
    assert repository.interviews[interview.id].difficulty == "pressure"
    assert repository.interviews[interview.id].time_limit_minutes == 60
    assert state.interview_goal == "big_tech"
    assert state.difficulty == "pressure"
    assert state.time_limit_minutes == 60


def test_create_interview_rejects_invalid_strategy_configuration() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    with pytest.raises(AppError) as exc_info:
        service.create_interview(
            1,
            1,
            "后端开发",
            interview_goal="social",
            difficulty="pressure",
            time_limit_minutes=60,
        )

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert repository.interviews == {}


def test_round_configuration_is_applied_when_round_starts() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume"],
        time_limit_minutes=30,
    )
    repository.interviews[interview.id] = InterviewRecord(
        **{**interview.__dict__, "overall_status": "in_progress", "elapsed_seconds": 30 * 60}
    )
    round_record = repository.list_rounds(interview.id)[0]

    question = service.start_round(
        1,
        interview.id,
        round_record.id,
        difficulty="pressure",
        time_limit_minutes=60,
    )

    configured_round = repository.get_round(interview.id, round_record.id)
    assert question.round_id == round_record.id
    assert configured_round is not None
    assert configured_round.status == "in_progress"
    assert configured_round.difficulty == "pressure"
    assert configured_round.time_limit_minutes == 60


def test_round_time_limit_blocks_generating_another_question() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume"],
        time_limit_minutes=30,
    )
    question = service.start_round(
        1,
        interview.id,
        repository.list_rounds(interview.id)[0].id,
        difficulty="normal",
        time_limit_minutes=30,
        started_at=datetime.utcnow() - timedelta(minutes=31),
    )
    round_record = repository.list_rounds(interview.id)[0]

    with pytest.raises(AppError) as exc_info:
        service.regenerate_round_question(
            1,
            interview.id,
            round_record.id,
            question.id,
        )

    assert exc_info.value.status_code == 409
    assert "限时" in exc_info.value.message


def test_round_enters_closing_stage_with_three_minutes_remaining() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    repository.resumes[1] = ResumeRecord(
        id=1,
        user_id=1,
        structured_data={
            "skills": ["Python"],
            "project_experience": [
                {"name": "医疗知识问答系统"},
                {"name": "智能旅行规划系统"},
            ],
        },
    )
    interview = service.create_interview(1, 1, "后端开发", selected_rounds=["resume"])
    round_record = repository.list_rounds(interview.id)[0]
    question = service.start_round(
        1,
        interview.id,
        round_record.id,
        time_limit_minutes=30,
        started_at=datetime.utcnow() - timedelta(minutes=28),
    )

    response = service.answer_round_question(
        1,
        interview.id,
        round_record.id,
        question.id,
        "我结合项目背景、个人职责和最终结果完整说明本次经历。",
    )

    assert response.action == "next_question"
    assert response.question is not None
    assert response.question.is_last_question is True
    assert response.question.question.startswith("这是本轮最后一个问题：")
    assert "智能旅行规划系统" in response.question.question
    finish_response = service.answer_round_question(
        1,
        interview.id,
        round_record.id,
        response.question.id,
        "最后补充一个此前没有说到的关键事实。",
    )

    assert finish_response.action == "finish_round"
    assert len(repository.list_round_qa(interview.id, round_record.id)) == 2
    assert repository.get_round(interview.id, round_record.id).status == "completed"  # type: ignore[union-attr]


def test_expired_round_accepts_current_answer_once_then_finishes() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发", selected_rounds=["resume"])
    round_record = repository.list_rounds(interview.id)[0]
    question = service.start_round(
        1,
        interview.id,
        round_record.id,
        time_limit_minutes=30,
        started_at=datetime.utcnow() - timedelta(minutes=31),
    )

    response = service.answer_round_question(
        1,
        interview.id,
        round_record.id,
        question.id,
        "这是限时结束时正在输入的最后一次回答，提交后不应再生成新题。",
    )

    assert response.action == "finish_round"
    assert response.question is None
    assert repository.get_round(interview.id, round_record.id).status == "completed"  # type: ignore[union-attr]


def test_paused_interview_elapsed_does_not_grow_while_restoring_state() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume"],
        time_limit_minutes=30,
    )
    repository.interviews[interview.id] = InterviewRecord(
        **{
            **interview.__dict__,
            "overall_status": "paused",
            "last_active_at": datetime.utcnow() - timedelta(minutes=31),
            "elapsed_seconds": 120,
        }
    )

    state = service.get_state(1, interview.id)

    assert state.elapsed_seconds == 120


def test_create_weakness_practice_reuses_source_context() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    source = service.create_interview(
        1,
        1,
        "后端开发",
        job_description="原岗位 JD：负责平台架构和稳定性建设。",
        selected_rounds=["resume", "technical"],
        interview_goal="big_tech",
        difficulty="pressure",
        time_limit_minutes=60,
    )
    repository.create_feedback_report(
        interview_id=source.id,
        score=72,
        weaknesses=["系统设计取舍不足"],
        suggestions=["补充架构边界、容量估算和失败降级。"],
    )

    practice = service.create_weakness_practice(
        user_id=1,
        source_interview_id=source.id,
        weakness="系统设计取舍不足",
        suggestion="补充架构边界、容量估算和失败降级。",
        round_type="technical",
    )
    practice_rounds = repository.list_rounds(practice.id)

    assert practice.resume_id == source.resume_id
    assert practice.target_position == source.target_position
    assert practice.interview_goal == "big_tech"
    assert practice.difficulty == "pressure"
    assert practice.time_limit_minutes == 60
    assert practice.selected_rounds == ["technical"]
    assert "系统设计取舍不足" in (practice.job_description or "")
    assert "原岗位 JD" in (practice.job_description or "")
    assert [(item.round_type, item.status) for item in practice_rounds] == [
        ("technical", "pending"),
        ("resume", "skipped"),
        ("manager", "skipped"),
        ("hr", "skipped"),
    ]
    progress = repository.get_weakness_practice_progress_by_practice(practice.id)
    assert progress is not None
    assert progress.source_interview_id == source.id
    assert progress.weakness_title == "系统设计取舍不足"
    assert progress.status == "pending"
    assert progress.source_score == 72


def test_weakness_practice_progress_updates_after_practice_report() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    source = service.create_interview(1, 1, "后端开发", selected_rounds=["technical"])
    repository.create_feedback_report(
        interview_id=source.id,
        score=72,
        weaknesses=["系统设计取舍不足"],
        suggestions=["补充架构边界、容量估算和失败降级。"],
    )
    practice = service.create_weakness_practice(
        user_id=1,
        source_interview_id=source.id,
        weakness="系统设计取舍不足",
        suggestion="补充架构边界、容量估算和失败降级。",
        round_type="technical",
    )
    repository.create_feedback_report(
        interview_id=practice.id,
        score=86,
        weaknesses=[],
        suggestions=["继续保持结构化拆解。"],
    )

    service.finish_interview(1, practice.id, finish_type="early")

    progress = repository.get_weakness_practice_progress_by_practice(practice.id)
    assert progress is not None
    assert progress.status == "practiced"
    assert progress.practice_score == 86
    assert progress.last_practiced_at is not None


def test_weakness_practice_progress_marks_repeated_low_score_as_needs_work() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    source = service.create_interview(1, 1, "后端开发", selected_rounds=["technical"])
    repository.create_feedback_report(
        interview_id=source.id,
        score=70,
        weaknesses=["数据库索引原理薄弱"],
        suggestions=["补充 B+ 树、覆盖索引和回表。"],
    )
    practice = service.create_weakness_practice(
        user_id=1,
        source_interview_id=source.id,
        weakness="数据库索引原理薄弱",
        suggestion="补充 B+ 树、覆盖索引和回表。",
        round_type="technical",
    )
    repository.create_feedback_report(
        interview_id=practice.id,
        score=68,
        weaknesses=["数据库索引原理薄弱，回表和覆盖索引说明仍不清晰"],
        suggestions=["继续专项练习索引执行计划。"],
    )

    service.finish_interview(1, practice.id, finish_type="early")

    progress = repository.get_weakness_practice_progress_by_practice(practice.id)
    assert progress is not None
    assert progress.status == "needs_work"
    assert progress.practice_score == 68


def test_weakness_practice_focus_reaches_question_generation_payload() -> None:
    llm = FakeLLMClient()
    service, repository = make_service(llm)
    repository.add_resume(resume_id=1, user_id=1)
    source = service.create_interview(1, 1, "后端开发", selected_rounds=["technical"])
    repository.create_feedback_report(
        interview_id=source.id,
        score=65,
        weaknesses=["数据库索引原理薄弱"],
        suggestions=["补充 B+ 树、覆盖索引和回表。"],
    )
    practice = service.create_weakness_practice(
        user_id=1,
        source_interview_id=source.id,
        weakness="数据库索引原理薄弱",
        suggestion="补充 B+ 树、覆盖索引和回表。",
        round_type="technical",
    )
    technical_round = repository.list_rounds(practice.id)[0]

    service.start_round(1, practice.id, technical_round.id)

    assert llm.question_resume_payloads
    assert "数据库索引原理薄弱" in llm.question_resume_payloads[-1]["_job_description"]


def test_create_weakness_practice_requires_existing_report() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    source = service.create_interview(1, 1, "后端开发")

    with pytest.raises(AppError) as exc_info:
        service.create_weakness_practice(
            user_id=1,
            source_interview_id=source.id,
            weakness="回答缺少技术细节",
        )

    assert exc_info.value.status_code == 409


def test_create_multi_round_interview_marks_unselected_rounds_skipped() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["technical", "resume"],
    )

    assert [(item.round_type, item.status) for item in repository.list_rounds(interview.id)] == [
        ("technical", "pending"),
        ("resume", "pending"),
        ("manager", "skipped"),
        ("hr", "skipped"),
    ]
    assert [item.round_type for item in service.list_rounds(interview)] == [
        "technical",
        "resume",
        "manager",
        "hr",
    ]


def test_create_interview_with_one_round_still_creates_round_record() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["hr"],
    )

    rounds = service.list_rounds(interview)

    assert interview.mode == "multi_round"
    assert [(item.round_type, item.status) for item in rounds] == [
        ("hr", "pending"),
        ("resume", "skipped"),
        ("technical", "skipped"),
        ("manager", "skipped"),
    ]


def test_empty_selected_rounds_is_rejected() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)

    with pytest.raises(AppError) as exc_info:
        service.create_interview(1, 1, "后端开发", selected_rounds=[])

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_selected_round_order_controls_start_sequence() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["technical", "resume"],
    )
    rounds = {item.round_type: item for item in repository.list_rounds(interview.id)}

    with pytest.raises(AppError) as exc_info:
        service.start_round(1, interview.id, rounds["resume"].id)

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR

    first_question = service.start_round(1, interview.id, rounds["technical"].id)

    assert first_question.round_id == rounds["technical"].id


def test_start_round_is_idempotent_and_requires_previous_round_finished() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume", "technical"],
    )
    resume_round, technical_round = repository.list_rounds(interview.id)[:2]

    with pytest.raises(AppError) as exc_info:
        service.start_round(1, interview.id, technical_round.id)

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR

    first = service.start_round(1, interview.id, resume_round.id)
    second = service.start_round(1, interview.id, resume_round.id)

    assert first.id == second.id
    assert len(repository.list_round_qa(interview.id, resume_round.id)) == 1


def test_start_round_generation_error_remains_retryable() -> None:
    service, repository = make_service(FlakyQuestionLLMClient())
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]

    with pytest.raises(AppError) as exc_info:
        service.start_round(1, interview.id, resume_round.id)

    failed_round = repository.get_round(interview.id, resume_round.id)
    assert exc_info.value.code == ErrorCode.LLM_API_KEY_MISSING
    assert repository.interviews[interview.id].harness_status == "pending"
    assert failed_round is not None
    assert failed_round.execution_status == "failed"

    question = service.start_round(1, interview.id, resume_round.id)

    assert question.round_id == resume_round.id
    assert repository.get_round(interview.id, resume_round.id).status == "in_progress"  # type: ignore[union-attr]


def test_start_round_duplicate_insert_returns_existing_question() -> None:
    class RacingStartRepository(FakeInterviewRepository):
        def __init__(self) -> None:
            super().__init__()
            self.race_once = True

        def create_qa(self, *args: Any, **kwargs: Any) -> QARecord:
            if self.race_once:
                self.race_once = False
                super().create_qa(
                    interview_id=kwargs["interview_id"],
                    round_id=kwargs["round_id"],
                    sequence=kwargs["sequence"],
                    question_type=kwargs["question_type"],
                    question="并发请求已创建的首题",
                    question_kind=kwargs["question_kind"],
                    parent_question_id=kwargs.get("parent_question_id"),
                )
                raise DuplicateKeyError()
            return super().create_qa(*args, **kwargs)

    repository = RacingStartRepository()
    llm_client = FakeLLMClient()
    service = InterviewService(repository=repository, llm_client=llm_client)  # type: ignore[arg-type]
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]

    question = service.start_round(1, interview.id, resume_round.id)

    assert question.question == "并发请求已创建的首题"
    assert len(repository.list_round_qa(interview.id, resume_round.id)) == 1
    assert llm_client.question_number == 1


def test_start_round_continues_when_harness_trace_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingHarnessRepository:
        def create_trace(self, request: object) -> int:
            raise RuntimeError("trace table unavailable")

    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    monkeypatch.setattr(
        interviews_module,
        "_get_harness_repository",
        lambda connection: FailingHarnessRepository(),
    )

    question = service.start_round(1, interview.id, resume_round.id)

    assert question.round_id == resume_round.id
    assert question.question == "问题 1"


def test_start_round_fallback_harness_saves_rule_evaluations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingHarnessRepository:
        def __init__(self) -> None:
            self.trace_statuses: list[dict[str, Any]] = []
            self.evaluations: list[Any] = []

        def create_trace(self, request: object) -> int:
            self.request = request
            return 101

        def update_trace_status(self, trace_id: int, **values: Any) -> None:
            self.trace_statuses.append({"trace_id": trace_id, **values})

        def save_rule_evaluation(self, **values: Any) -> int:
            self.evaluations.append(values["evaluation"])
            return len(self.evaluations)

    harness_repository = RecordingHarnessRepository()
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    monkeypatch.setattr(
        interviews_module,
        "_get_harness_repository",
        lambda connection: harness_repository,
    )

    question = service.start_round(1, interview.id, resume_round.id)

    assert question.round_id == resume_round.id
    assert harness_repository.trace_statuses[-1]["status"] == "completed"
    assert {item.rule_name for item in harness_repository.evaluations} >= {
        "output_schema_valid",
        "trace_created",
        "checkpoint_created",
        "retry_limit",
    }


def test_round_answer_returns_follow_up_and_state_current_question() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)

    response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "这是回答",
    )
    state = service.get_state(1, interview.id)

    assert response.action == "follow_up"
    assert response.question is not None
    assert response.question.question_kind == "follow_up"
    assert response.question.parent_question_id == first_question.id
    assert response.answer_evaluation is not None
    assert response.answer_evaluation["status"] == "fallback"
    assert response.answer_evaluation["question_id"] == first_question.id
    assert response.answer_evaluation["issues"]
    assert state.current_question is not None
    assert state.current_question.id == response.question.id


def test_round_answer_returns_realtime_question_evaluation() -> None:
    evaluation_service = FakeQuestionEvaluationService()
    service, repository = make_service(evaluation_service=evaluation_service)
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)

    response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "我负责推进接口改造，先梳理调用链路，再设计灰度方案。",
    )

    assert response.action == "follow_up"
    assert response.answer_evaluation is not None
    assert response.answer_evaluation["status"] == "succeeded"
    assert response.answer_evaluation["question_id"] == first_question.id
    assert response.answer_evaluation["round_id"] == resume_round.id
    assert response.answer_evaluation["total_score"] == 74
    assert response.answer_evaluation["issues"] == ["缺少量化结果。", "技术取舍还可以更明确。"]
    assert evaluation_service.calls == [first_question.id]


def test_answer_draft_roundtrip_does_not_persist_as_formal_answer() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    question = service.start_round(1, interview.id, resume_round.id)

    draft = service.save_answer_draft(
        1,
        interview.id,
        resume_round.id,
        question.id,
        "这是还没提交的草稿",
    )
    loaded = service.get_answer_draft(1, interview.id, resume_round.id, question.id)
    stored_question = repository.get_round_qa_by_id(interview.id, resume_round.id, question.id)
    state = service.get_state(1, interview.id)

    assert draft.question_id == question.id
    assert draft.answer == "这是还没提交的草稿"
    assert loaded.answer == draft.answer
    assert stored_question is not None
    assert stored_question.answer is None
    assert state.current_question is not None
    assert state.current_question.id == question.id
    assert len(state.qa_history) == 1
    assert state.qa_history[0]["id"] == question.id
    assert state.qa_history[0]["answer"] is None


def test_answer_submission_clears_saved_draft() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    question = service.start_round(1, interview.id, resume_round.id)
    service.save_answer_draft(1, interview.id, resume_round.id, question.id, "准备提交的草稿")

    service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        question.id,
        "正式回答",
    )

    assert repository.get_answer_draft(1, interview.id, resume_round.id, question.id) is None


def test_regenerate_current_question_preserves_old_question_for_audit() -> None:
    llm_client = FakeLLMClient()
    service, repository = make_service(llm_client)
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    service.save_answer_draft(1, interview.id, resume_round.id, first_question.id, "旧题草稿")

    response = service.regenerate_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
    )
    state = service.get_state(1, interview.id)
    active_history = repository.list_round_qa(interview.id, resume_round.id)
    audit_history = repository.list_round_qa(
        interview.id,
        resume_round.id,
        include_inactive=True,
    )

    assert response.action == "next_question"
    assert response.question is not None
    assert response.question.id != first_question.id
    assert response.question.regenerated_from_question_id == first_question.id
    assert state.current_question is not None
    assert state.current_question.id == response.question.id
    assert [item["id"] for item in state.qa_history] == [response.question.id]
    assert len(active_history) == 1
    assert len(audit_history) == 2
    assert audit_history[0].question_status == "regenerated"
    assert audit_history[1].question_status == "active"
    assert repository.interviews[interview.id].question_count == 1
    assert llm_client.question_number == 2
    assert repository.get_answer_draft(1, interview.id, resume_round.id, first_question.id) is None


def test_regenerated_question_rejects_old_question_answer() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    service.regenerate_round_question(1, interview.id, resume_round.id, first_question.id)

    with pytest.raises(AppError) as exc_info:
        service.answer_round_question(
            1,
            interview.id,
            resume_round.id,
            first_question.id,
            "旧题回答",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == ErrorCode.CONFLICT


def test_skip_current_question_marks_old_question_skipped_and_creates_next_question() -> None:
    llm_client = FakeLLMClient()
    service, repository = make_service(llm_client)
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    service.save_answer_draft(1, interview.id, resume_round.id, first_question.id, "要跳过的草稿")

    response = service.skip_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
    )
    state = service.get_state(1, interview.id)
    active_history = repository.list_round_qa(interview.id, resume_round.id)
    audit_history = repository.list_round_qa(
        interview.id,
        resume_round.id,
        include_inactive=True,
    )

    assert response.action == "next_question"
    assert response.question is not None
    assert response.question.id != first_question.id
    assert state.current_question is not None
    assert state.current_question.id == response.question.id
    assert [item["id"] for item in state.qa_history] == [response.question.id]
    assert len(active_history) == 1
    assert len(audit_history) == 2
    assert audit_history[0].question_status == "skipped"
    assert audit_history[1].question_status == "active"
    assert repository.interviews[interview.id].question_count == 1
    assert llm_client.question_number == 2
    assert repository.get_answer_draft(1, interview.id, resume_round.id, first_question.id) is None


def test_skipped_question_rejects_old_question_answer() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    service.skip_round_question(1, interview.id, resume_round.id, first_question.id)

    with pytest.raises(AppError) as exc_info:
        service.answer_round_question(
            1,
            interview.id,
            resume_round.id,
            first_question.id,
            "旧题回答",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == ErrorCode.CONFLICT


def test_round_answer_rejects_oversized_answer_before_persisting() -> None:
    llm_client = FakeLLMClient()
    service, repository = make_service(llm_client)
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)

    with pytest.raises(AppError) as exc_info:
        service.answer_round_question(
            1,
            interview.id,
            resume_round.id,
            first_question.id,
            "A" * (ROUND_ANSWER_MAX_LENGTH + 1),
        )

    saved_question = repository.get_round_qa_by_id(
        interview.id,
        resume_round.id,
        first_question.id,
    )
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
    assert saved_question is not None
    assert saved_question.answer is None
    assert llm_client.question_number == 1


def test_pause_interview_blocks_answer_until_resumed() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    started_at = datetime.utcnow() - timedelta(seconds=12)
    repository.interviews[interview.id] = InterviewRecord(
        **{
            **repository.interviews[interview.id].__dict__,
            "last_active_at": started_at,
        }
    )
    repository.rounds[interview.id] = [
        InterviewRoundRecord(
            **{
                **item.__dict__,
                "started_at": started_at if item.id == resume_round.id else item.started_at,
            }
        )
        for item in repository.rounds[interview.id]
    ]

    paused_state = service.pause_interview(1, interview.id)

    assert paused_state.overall_status == "paused"
    assert paused_state.current_question is not None
    assert paused_state.current_question.id == first_question.id
    assert paused_state.rounds[0].status == "in_progress"
    assert paused_state.rounds[0].elapsed_seconds >= 12

    with pytest.raises(AppError) as exc_info:
        service.answer_round_question(
            1,
            interview.id,
            resume_round.id,
            first_question.id,
            "暂停期间不能提交",
        )

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR
    assert "暂停" in exc_info.value.message

    resumed_state = service.resume_interview(1, interview.id)
    response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "继续后可以提交",
    )

    assert resumed_state.overall_status == "in_progress"
    assert response.action == "follow_up"


def test_recoverable_next_question_error_falls_back_without_breaking_round() -> None:
    service, repository = make_service(RecoverableNextQuestionLLMClient())
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["manager"],
    )
    manager_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, manager_round.id)

    response = service.answer_round_question(
        1,
        interview.id,
        manager_round.id,
        first_question.id,
        "我会先对齐目标和验收标准，再拆解任务推进。",
    )
    state = service.get_state(1, interview.id)

    assert response.action == "follow_up"
    assert response.question is not None
    assert response.question.round_id == manager_round.id
    assert "业务理解能力" in response.question.question
    assert repository.interviews[interview.id].harness_status == "degraded"
    assert state.current_round == "manager"
    assert state.current_question is not None
    assert state.current_question.id == response.question.id


def test_retry_same_answer_returns_existing_next_question_without_duplicate() -> None:
    llm_client = FakeLLMClient()
    service, repository = make_service(llm_client)
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    first_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "这是回答",
    )

    retry_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "这是回答",
    )

    assert first_response.question is not None
    assert retry_response.question is not None
    assert retry_response.action == first_response.action
    assert retry_response.question.id == first_response.question.id
    assert len(repository.list_round_qa(interview.id, resume_round.id)) == 2
    assert llm_client.question_number == 2


def test_retry_same_answer_continues_when_answer_was_saved_before_next_question() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    repository.update_answer(first_question.id, "这是回答")

    retry_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "这是回答",
    )

    assert retry_response.action == "follow_up"
    assert retry_response.question is not None
    assert retry_response.question.parent_question_id == first_question.id
    assert len(repository.list_round_qa(interview.id, resume_round.id)) == 2


def test_concurrent_same_answer_returns_existing_next_question() -> None:
    class RacingAnswerRepository(FakeInterviewRepository):
        def __init__(self) -> None:
            super().__init__()
            self.race_once = True

        def update_answer(self, qa_id: int, answer: str) -> bool:
            if self.race_once:
                self.race_once = False
                current = next(
                    qa for records in self.qa.values() for qa in records if qa.id == qa_id
                )
                super().update_answer(qa_id, answer)
                super().create_qa(
                    interview_id=current.interview_id,
                    round_id=current.round_id,
                    sequence=current.sequence + 1,
                    question_type=current.question_type,
                    question="并发请求已创建的下一题",
                    question_kind="follow_up",
                    parent_question_id=current.id,
                )
                return False
            return super().update_answer(qa_id, answer)

    repository = RacingAnswerRepository()
    llm_client = FakeLLMClient()
    service = InterviewService(repository=repository, llm_client=llm_client)  # type: ignore[arg-type]
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)

    response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "这是回答",
    )

    assert response.action == "follow_up"
    assert response.question is not None
    assert response.question.question == "并发请求已创建的下一题"
    assert len(repository.list_round_qa(interview.id, resume_round.id)) == 2
    assert llm_client.question_number == 1


def test_answer_can_finish_round_without_creating_third_question() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    first_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "第一题回答",
    )

    assert first_response.question is not None
    finish_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_response.question.id,
        "第二题回答",
        finish_after_answer=True,
    )
    state = service.get_state(1, interview.id)
    qa_history = repository.list_round_qa(interview.id, resume_round.id)

    assert finish_response.action == "finish_round"
    assert finish_response.round_summary is not None
    assert len(qa_history) == 2
    assert all(item.answer is not None for item in qa_history)
    assert repository.get_round(interview.id, resume_round.id).status == "completed"  # type: ignore[union-attr]
    assert state.current_question is None
    assert state.current_round is None


def test_finish_round_normal_rejects_pending_round_without_answer() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]

    with pytest.raises(AppError) as exc_info:
        service.finish_round(1, interview.id, resume_round.id)

    stored_round = repository.get_round(interview.id, resume_round.id)
    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR
    assert stored_round is not None
    assert stored_round.status == "pending"
    assert stored_round.summary is None


def test_finish_round_normal_rejects_started_round_without_answer() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    service.start_round(1, interview.id, resume_round.id)

    with pytest.raises(AppError) as exc_info:
        service.finish_round(1, interview.id, resume_round.id)

    stored_round = repository.get_round(interview.id, resume_round.id)
    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR
    assert stored_round is not None
    assert stored_round.status == "in_progress"
    assert stored_round.summary is None


def test_answer_is_committed_before_next_question_generation_failure() -> None:
    repository = FakeInterviewRepository()
    llm_client = FailingNextQuestionLLMClient(repository)
    service = InterviewService(repository=repository, llm_client=llm_client)  # type: ignore[arg-type]
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    commits_before_answer = repository.commit_count

    with pytest.raises(RuntimeError, match="next_question_failed"):
        service.answer_round_question(
            1,
            interview.id,
            resume_round.id,
            first_question.id,
            "答案已提交",
        )

    saved_question = repository.get_round_qa_by_id(
        interview.id,
        resume_round.id,
        first_question.id,
    )
    assert saved_question is not None
    assert saved_question.answer == "答案已提交"
    assert llm_client.answer_commit_count is not None
    assert llm_client.answer_commit_count >= commits_before_answer + 2


def test_failed_round_result_allows_next_selected_round() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume", "technical"],
    )
    resume_round, technical_round = repository.list_rounds(interview.id)[:2]
    first_question = service.start_round(1, interview.id, resume_round.id)
    first_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "第一题回答",
    )
    assert first_response.question is not None
    second_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_response.question.id,
        "第二题回答",
    )
    assert second_response.question is not None
    finish_response = service.finish_round(1, interview.id, resume_round.id)

    failed_round = repository.get_round(interview.id, resume_round.id)
    next_question = service.start_round(1, interview.id, technical_round.id)

    assert finish_response.action == "finish_round"
    assert failed_round is not None
    assert failed_round.result == "failed"
    assert next_question.round_id == technical_round.id


def test_round_respects_maximum_total_questions() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["technical"],
    )
    technical_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, technical_round.id)
    current_question = first_question
    first_response = None
    second_response = None
    response = None

    for index in range(1, 41):
        response = service.answer_round_question(
            1,
            interview.id,
            technical_round.id,
            current_question.id,
            f"第 {index} 题回答",
        )
        if index == 1:
            first_response = response
        if index == 2:
            second_response = response
        if index < 10:
            assert response.action != "finish_round"
            assert response.question is not None
        if index < 40:
            assert response.question is not None
            current_question = response.question

    qa_history = repository.list_round_qa(interview.id, technical_round.id)

    assert first_response is not None
    assert first_response.action == "follow_up"
    assert first_response.question is not None
    assert first_response.question.question_kind == "follow_up"
    assert second_response is not None
    assert second_response.action == "next_question"
    assert second_response.question is not None
    assert second_response.question.question_kind == "main"
    assert response is not None
    assert response.action == "finish_round"
    assert len(qa_history) == 40


def test_retry_same_answer_after_round_finished_returns_existing_summary() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发")
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    first_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "第一题回答",
    )
    assert first_response.question is not None
    finish_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_response.question.id,
        "第二题回答",
        finish_after_answer=True,
    )

    retry_response = service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_response.question.id,
        "第二题回答",
        finish_after_answer=True,
    )

    assert retry_response.action == "finish_round"
    assert retry_response.round_summary == finish_response.round_summary
    assert len(repository.list_round_qa(interview.id, resume_round.id)) == 2


def test_finish_round_early_allows_next_selected_round() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume", "technical"],
    )
    resume_round, technical_round = repository.list_rounds(interview.id)[:2]
    first_question = service.start_round(1, interview.id, resume_round.id)

    finish_response = service.finish_round(1, interview.id, resume_round.id, finish_type="early")
    next_question = service.start_round(1, interview.id, technical_round.id)
    active_history = repository.list_round_qa(interview.id, resume_round.id)
    audit_history = repository.list_round_qa(
        interview.id,
        resume_round.id,
        include_inactive=True,
    )

    assert finish_response.round_summary is not None
    assert finish_response.round_summary["is_reference_only"] is True
    assert next_question.round_id == technical_round.id
    assert active_history == []
    assert audit_history[0].id == first_question.id
    assert audit_history[0].question_status == "skipped"
    assert repository.interviews[interview.id].question_count == 1


def test_finish_multi_round_early_cancels_pending_rounds() -> None:
    service, repository = make_service()
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(
        1,
        1,
        "后端开发",
        selected_rounds=["resume", "technical"],
    )
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)

    report = service.finish_interview(1, interview.id, finish_type="early")
    active_history = repository.list_round_qa(interview.id, resume_round.id)
    audit_history = repository.list_round_qa(
        interview.id,
        resume_round.id,
        include_inactive=True,
    )

    assert report.reference_note == "面试提前结束，评价仅供参考。"
    assert repository.interviews[interview.id].status == "finished"
    assert [item.status for item in repository.list_rounds(interview.id)] == [
        "finished_early",
        "cancelled",
        "skipped",
        "skipped",
    ]
    assert active_history == []
    assert audit_history[0].id == first_question.id
    assert audit_history[0].question_status == "skipped"
    assert repository.interviews[interview.id].question_count == 0


def test_finish_multi_round_duplicate_report_returns_existing_report() -> None:
    class RacingFeedbackRepository(FakeInterviewRepository):
        def __init__(self) -> None:
            super().__init__()
            self.race_once = True

        def create_feedback_report(self, *args: Any, **kwargs: Any) -> FeedbackReportRecord:
            if self.race_once:
                self.race_once = False
                super().create_feedback_report(
                    interview_id=kwargs["interview_id"],
                    score=77,
                    weaknesses=["已有薄弱点"],
                    suggestions=["已有建议"],
                    recommendation=kwargs.get("recommendation"),
                    round_scores=kwargs.get("round_scores"),
                    strengths=["已有优势"],
                    ability_analysis=kwargs.get("ability_analysis"),
                    job_match=kwargs.get("job_match"),
                    final_conclusion=kwargs.get("final_conclusion"),
                    confidence=kwargs.get("confidence"),
                    reference_note=kwargs.get("reference_note"),
                    used_candidate_memory=kwargs.get("used_candidate_memory", False),
                    report_reliability_status=kwargs.get("report_reliability_status", "normal"),
                )
                raise DuplicateKeyError()
            return super().create_feedback_report(*args, **kwargs)

    repository = RacingFeedbackRepository()
    service = InterviewService(repository=repository, llm_client=FakeLLMClient())  # type: ignore[arg-type]
    repository.add_resume(resume_id=1, user_id=1)
    interview = service.create_interview(1, 1, "后端开发", selected_rounds=["resume"])
    resume_round = repository.list_rounds(interview.id)[0]
    first_question = service.start_round(1, interview.id, resume_round.id)
    service.answer_round_question(
        1,
        interview.id,
        resume_round.id,
        first_question.id,
        "第一题回答",
        finish_after_answer=True,
    )

    report = service.finish_interview(1, interview.id)

    assert report.score == 77
    assert report.weaknesses == ["已有薄弱点"]
    assert len(repository.feedback_reports) == 1
    assert repository.interviews[interview.id].status == "finished"
