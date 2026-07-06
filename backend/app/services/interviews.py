import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from typing import Any, cast

from fastapi import status

from app.agents import ROUND_ORDER, ROUND_SPECS, count_questions, get_round_agent
from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.evolution.quality_signals import record_interview_completion_quality_signal
from app.evolution.runtime import resolve_round_spec
from app.evolution.versioning import resolve_active_version_bundle_id
from app.harness.contracts import ValidationStatus
from app.repositories.interviews import (
    FeedbackReportRecord,
    InterviewRecord,
    InterviewRepository,
    InterviewRoundRecord,
    QARecord,
)
from app.repositories.preferences import PreferencesRepository
from app.schemas.interview import (
    JOB_DESCRIPTION_MAX_LENGTH,
    ROUND_ANSWER_MAX_LENGTH,
    FeedbackReportResponse,
    InterviewRoundResponse,
    InterviewStateResponse,
    RoundAnswerResponse,
    RoundQuestionResponse,
)
from app.schemas.memory import MemoryRetrievalRequest
from app.services.evaluations import EvaluationSchedulerService
from app.services.llm import LLMClient
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.memory_tasks import MemoryTaskService

ACTIVE_ROUND_STATUSES = {"pending", "in_progress"}
FINISHED_ROUND_STATUSES = {"completed", "finished_early"}
ELAPSED_SECONDS_CAP = 300
ACTIVE_QUESTION_STATUS = "active"


class InterviewService:
    def __init__(
        self,
        repository: InterviewRepository,
        llm_client: LLMClient,
        evaluation_service: EvaluationSchedulerService | None = None,
        memory_task_service: MemoryTaskService | None = None,
        memory_retrieval_service: MemoryRetrievalService | None = None,
        preferences_repository: PreferencesRepository | None = None,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.evaluation_service = evaluation_service
        self.memory_task_service = memory_task_service
        self.memory_retrieval_service = memory_retrieval_service
        self.preferences_repository = preferences_repository

    def create_interview(
        self,
        user_id: int,
        resume_id: int,
        target_position: str,
        job_description: str | None = None,
        selected_rounds: list[str] | None = None,
    ) -> InterviewRecord:
        target = target_position.strip()
        if not target:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        clean_job_description = job_description.strip() if job_description else None
        if (
            clean_job_description is not None
            and len(clean_job_description) > JOB_DESCRIPTION_MAX_LENGTH
        ):
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        _require_resume(self.repository, resume_id, user_id)
        rounds = _normalize_selected_rounds(selected_rounds)
        version_bundle_id = self._resolve_version_bundle_id(
            job_family=target,
            developer_user_id=user_id,
        )
        try:
            interview = self.repository.create_interview(
                user_id,
                resume_id,
                target,
                mode="multi_round",
                job_description=clean_job_description,
                selected_rounds=rounds,
                version_bundle_id=version_bundle_id,
            )
        except TypeError:
            interview = self.repository.create_interview(
                user_id,
                resume_id,
                target,
                mode="multi_round",
                job_description=clean_job_description,
                selected_rounds=rounds,
            )
        self.repository.create_rounds(
            _round_rows(
                interview.id,
                rounds,
                repository=self.repository,
                version_bundle_id=interview.version_bundle_id,
            )
        )
        self._update_interview_harness(interview.id, harness_status="pending")
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=None,
            node_type="create_interview",
            snapshot={"resume_id": resume_id, "selected_rounds": rounds},
        )
        return interview

    def finish_interview(
        self,
        user_id: int,
        interview_id: int,
        finish_type: str = "normal",
    ) -> FeedbackReportResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        return self.finish_multi_round_interview(user_id, interview_id, finish_type=finish_type)

    def get_state(self, user_id: int, interview_id: int) -> InterviewStateResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        rounds = self.list_rounds(interview)
        qa_history = self.repository.list_qa(interview.id)
        current_round = next((item for item in rounds if item.status == "in_progress"), None)
        current_question = (
            self.repository.get_unanswered_round_question(interview.id, current_round.id)
            if current_round is not None
            else None
        )
        question_scores = (
            self.evaluation_service.question_scores_by_id(interview.id)
            if self.evaluation_service is not None
            else {}
        )
        finished_round_ids = {item.id for item in rounds if item.status in FINISHED_ROUND_STATUSES}
        return InterviewStateResponse(
            interview_id=interview.id,
            mode=interview.mode,
            overall_status=interview.overall_status,
            target_position=interview.target_position,
            job_description=interview.job_description,
            current_round=interview.current_round,
            elapsed_seconds=interview.elapsed_seconds,
            harness_status=interview.harness_status,
            recovery_count=interview.recovery_count,
            had_degradation=interview.had_degradation,
            last_harness_error=interview.last_harness_error,
            rounds=[_round_response(item, interview) for item in rounds],
            current_question=_round_question_response(current_question)
            if current_question is not None and current_question.round_id is not None
            else None,
            qa_history=[
                _qa_state_item(
                    qa,
                    question_scores.get(qa.id)
                    if qa.round_id is not None and qa.round_id in finished_round_ids
                    else None,
                )
                for qa in qa_history
            ],
        )

    def list_rounds(self, interview: InterviewRecord) -> list[InterviewRoundRecord]:
        return _ordered_rounds(interview, self.repository.list_rounds(interview.id))

    def start_round(self, user_id: int, interview_id: int, round_id: int) -> RoundQuestionResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        self._ensure_interview_not_paused(interview)
        self._ensure_harness_can_continue(interview)
        round_record = self._require_round(interview.id, round_id)
        if round_record.status == "skipped":
            raise _status_error()
        if round_record.status in FINISHED_ROUND_STATUSES:
            raise _status_error()
        self._ensure_previous_rounds_finished(interview, round_record)

        existing_question = self.repository.get_unanswered_round_question(interview.id, round_id)
        if round_record.status == "in_progress" and existing_question is not None:
            return _round_question_response(existing_question)

        resume = _require_resume(self.repository, interview.resume_id, user_id)
        history = self.repository.list_round_qa(interview.id, round_id)
        effective_memories = self._retrieve_effective_memories(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            scene="new_question",
            intent="生成新问题前检索候选人的历史薄弱点、已问题目和岗位目标。",
        )
        question = self._generate_round_question(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            purpose="start_round_question",
            payload={
                "history_count": len(history),
                "memory_count": len(effective_memories),
                "question_kind": "main",
            },
            qa_history_payload=_qa_history(history),
            resume_data=resume.structured_data,
            previous_answer=None,
            effective_memories=effective_memories,
            question_kind="main",
        )
        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        qa = create_qa(
            interview_id=interview.id,
            round_id=round_id,
            sequence=len(history) + 1,
            question_type=question.question_type,
            question=question.question,
            question_kind="main",
        )
        now = datetime.utcnow()
        self.repository.mark_round_started(
            interview_id=interview.id,
            round_id=round_id,
            round_type=round_record.round_type,
            started_at=now,
            elapsed_seconds=_elapsed_seconds(interview, now),
        )
        self.repository.update_question_count(
            interview.id,
            len(self.repository.list_qa(interview.id)),
        )
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            node_type="question_generated",
            snapshot={"question_id": qa.id, "sequence": qa.sequence},
        )
        return _round_question_response(qa)

    def answer_round_question(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
        answer: str,
        finish_after_answer: bool = False,
    ) -> RoundAnswerResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        self._ensure_interview_not_paused(interview)
        self._ensure_harness_can_continue(interview)
        round_record = self._require_round(interview.id, round_id)
        clean_answer = answer.strip()
        if not clean_answer:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        if len(clean_answer) > ROUND_ANSWER_MAX_LENGTH:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        if round_record.status != "in_progress":
            if round_record.status in FINISHED_ROUND_STATUSES:
                current_qa = self.repository.get_round_qa_by_id(
                    interview.id,
                    round_id,
                    question_id,
                )
                if current_qa is not None and current_qa.answer == clean_answer:
                    return RoundAnswerResponse(
                        action="finish_round",
                        round_summary=round_record.summary,
                    )
            raise _status_error()
        current_qa = self.repository.get_round_qa_by_id(interview.id, round_id, question_id)
        if current_qa is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if current_qa.question_status != ACTIVE_QUESTION_STATUS:
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="该题已跳过或重新生成，不能继续提交旧题回答。",
            )
        if current_qa.answer is not None:
            if current_qa.answer != clean_answer:
                raise AppError(
                    ErrorCode.CONFLICT,
                    status.HTTP_409_CONFLICT,
                    message="该题已提交回答。",
                )
            existing_question = self.repository.get_unanswered_round_question(
                interview.id,
                round_id,
            )
            if existing_question is not None and existing_question.id != current_qa.id:
                return RoundAnswerResponse(
                    action=_answer_action_for_question(existing_question),
                    question=_round_question_response(existing_question),
                )
            answered_qa = QARecord(**{**current_qa.__dict__, "answer": clean_answer})
            return self._continue_round_after_answer(
                user_id=user_id,
                interview=interview,
                round_record=round_record,
                answered_qa=answered_qa,
                clean_answer=clean_answer,
                finish_after_answer=finish_after_answer,
            )
        answer_saved = self.repository.update_answer(current_qa.id, clean_answer)
        if not answer_saved:
            refreshed_qa = self.repository.get_round_qa_by_id(interview.id, round_id, question_id)
            if refreshed_qa is None:
                raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
            if refreshed_qa.answer != clean_answer:
                raise AppError(
                    ErrorCode.CONFLICT,
                    status.HTTP_409_CONFLICT,
                    message="该题已提交回答。",
                )
            existing_question = self.repository.get_unanswered_round_question(
                interview.id,
                round_id,
            )
            if existing_question is not None and existing_question.id != refreshed_qa.id:
                return RoundAnswerResponse(
                    action=_answer_action_for_question(existing_question),
                    question=_round_question_response(existing_question),
                )
            current_qa = refreshed_qa

        answered_qa = QARecord(**{**current_qa.__dict__, "answer": clean_answer})
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            node_type="answer_submitted",
            snapshot={"question_id": current_qa.id, "answer_length": len(clean_answer)},
        )
        # The answer is durable before scoring or question generation calls an external model.
        self.repository.commit()

        return self._continue_round_after_answer(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            answered_qa=answered_qa,
            clean_answer=clean_answer,
            finish_after_answer=finish_after_answer,
        )

    def regenerate_round_question(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> RoundAnswerResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        self._ensure_interview_not_paused(interview)
        self._ensure_harness_can_continue(interview)
        round_record = self._require_round(interview.id, round_id)
        if round_record.status != "in_progress":
            raise _status_error()

        current_qa = self.repository.get_round_qa_by_id(interview.id, round_id, question_id)
        active_question = self.repository.get_unanswered_round_question(interview.id, round_id)
        if current_qa is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if (
            current_qa.answer is not None
            or current_qa.question_status != ACTIVE_QUESTION_STATUS
            or active_question is None
            or active_question.id != current_qa.id
        ):
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="只能重新生成当前未回答的问题。",
            )

        resume = _require_resume(self.repository, interview.resume_id, user_id)
        all_history = self.repository.list_round_qa(interview.id, round_id, include_inactive=True)
        previous_answer = _parent_answer(all_history, current_qa)
        effective_memories = self._retrieve_effective_memories(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            scene="new_question",
            intent="重新生成当前问题前检索已问题目、候选人材料和岗位目标，避免重复。",
            query_text=current_qa.question,
        )
        question = self._generate_round_question(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            purpose="regenerate_round_question",
            payload={
                "regenerated_question_id": current_qa.id,
                "history_count": len(all_history),
                "memory_count": len(effective_memories),
                "question_kind": current_qa.question_kind,
            },
            qa_history_payload=_qa_history(all_history),
            resume_data=resume.structured_data,
            previous_answer=previous_answer,
            effective_memories=effective_memories,
            question_kind=current_qa.question_kind,
        )
        updated = self.repository.update_question_status(current_qa.id, "regenerated")
        if not updated:
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="当前问题状态已变化，请刷新后重试。",
            )

        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        next_qa = create_qa(
            interview_id=interview.id,
            round_id=round_record.id,
            sequence=len(all_history) + 1,
            question_type=question.question_type,
            question=question.question,
            question_kind=current_qa.question_kind,
            parent_question_id=current_qa.parent_question_id,
            regenerated_from_question_id=current_qa.id,
        )
        self.repository.update_question_count(
            interview.id,
            len(self.repository.list_qa(interview.id)),
        )
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            node_type="question_regenerated",
            snapshot={
                "old_question_id": current_qa.id,
                "new_question_id": next_qa.id,
                "question_kind": next_qa.question_kind,
            },
        )
        return RoundAnswerResponse(
            action=_answer_action_for_question(next_qa),
            question=_round_question_response(next_qa),
        )

    def skip_round_question(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> RoundAnswerResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        self._ensure_interview_not_paused(interview)
        self._ensure_harness_can_continue(interview)
        round_record = self._require_round(interview.id, round_id)
        if round_record.status != "in_progress":
            raise _status_error()

        current_qa = self.repository.get_round_qa_by_id(interview.id, round_id, question_id)
        active_question = self.repository.get_unanswered_round_question(interview.id, round_id)
        if current_qa is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if (
            current_qa.answer is not None
            or current_qa.question_status != ACTIVE_QUESTION_STATUS
            or active_question is None
            or active_question.id != current_qa.id
        ):
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="只能跳过当前未回答的问题。",
            )

        resume = _require_resume(self.repository, interview.resume_id, user_id)
        all_history = self.repository.list_round_qa(interview.id, round_id, include_inactive=True)
        previous_answer = _parent_answer(all_history, current_qa)
        effective_memories = self._retrieve_effective_memories(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            scene="new_question",
            intent="跳过当前问题后检索已问题目、候选人材料和岗位目标，生成新的有效问题。",
            query_text=current_qa.question,
        )
        question = self._generate_round_question(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            purpose="skip_round_question",
            payload={
                "skipped_question_id": current_qa.id,
                "history_count": len(all_history),
                "memory_count": len(effective_memories),
                "question_kind": current_qa.question_kind,
            },
            qa_history_payload=_qa_history(all_history),
            resume_data=resume.structured_data,
            previous_answer=previous_answer,
            effective_memories=effective_memories,
            question_kind=current_qa.question_kind,
        )
        updated = self.repository.update_question_status(current_qa.id, "skipped")
        if not updated:
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="当前问题状态已变化，请刷新后重试。",
            )

        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        next_qa = create_qa(
            interview_id=interview.id,
            round_id=round_record.id,
            sequence=len(all_history) + 1,
            question_type=question.question_type,
            question=question.question,
            question_kind=current_qa.question_kind,
            parent_question_id=current_qa.parent_question_id,
        )
        self.repository.update_question_count(
            interview.id,
            len(self.repository.list_qa(interview.id)),
        )
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            node_type="question_skipped",
            snapshot={
                "old_question_id": current_qa.id,
                "new_question_id": next_qa.id,
                "question_kind": next_qa.question_kind,
            },
        )
        return RoundAnswerResponse(
            action=_answer_action_for_question(next_qa),
            question=_round_question_response(next_qa),
        )

    def _continue_round_after_answer(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        answered_qa: QARecord,
        clean_answer: str,
        finish_after_answer: bool,
    ) -> RoundAnswerResponse:
        now = datetime.utcnow()
        self.repository.touch_interview(interview.id, now, _elapsed_seconds(interview, now))
        history = self.repository.list_round_qa(interview.id, round_record.id)
        generation_history = self.repository.list_round_qa(
            interview.id,
            round_record.id,
            include_inactive=True,
        )
        resume = _require_resume(self.repository, interview.resume_id, user_id)
        question_score = (
            self.evaluation_service.score_question(
                interview=interview,
                round_record=round_record,
                qa=answered_qa,
                resume=resume,
            )
            if self.evaluation_service is not None
            else None
        )
        if finish_after_answer:
            summary = self._generate_round_summary(
                interview=interview,
                round_record=round_record,
                history=history,
                resume=resume,
                is_reference_only=False,
            )
            self.repository.finish_round(interview.id, round_record.id, "completed", summary, now)
            return RoundAnswerResponse(action="finish_round", round_summary=summary)

        agent = get_round_agent(round_record.round_type, self.llm_client)
        agent.spec = resolve_round_spec(
            self.repository,
            version_bundle_id=interview.version_bundle_id,
            base_spec=agent.spec,
        )
        if agent.should_finish(
            round_record,
            history,
            latest_question_score=question_score,
        ):
            summary = self._generate_round_summary(
                interview=interview,
                round_record=round_record,
                history=history,
                resume=resume,
                is_reference_only=False,
            )
            self.repository.finish_round(interview.id, round_record.id, "completed", summary, now)
            return RoundAnswerResponse(action="finish_round", round_summary=summary)

        next_kind = _next_question_kind(
            answered_qa,
            history,
            round_record,
            follow_up_recommended=(
                question_score.should_follow_up if question_score is not None else None
            ),
        )
        parent_question_id = answered_qa.id if next_kind == "follow_up" else None
        effective_memories = self._retrieve_effective_memories(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            scene="follow_up" if next_kind == "follow_up" else "new_question",
            intent=(
                "生成追问前检索相关项目经历、历史回答和未解决问题。"
                if next_kind == "follow_up"
                else "生成新问题前检索候选人的历史薄弱点、已问题目和岗位目标。"
            ),
            query_text=f"{answered_qa.question} {clean_answer}",
        )
        qa_history_payload = _qa_history(
            history,
            evaluation_by_qa_id=(
                {
                    answered_qa.id: {
                        "should_follow_up": question_score.should_follow_up,
                        "follow_up_direction": question_score.follow_up_direction,
                    }
                }
                if question_score is not None
                else None
            ),
        )
        question = self._generate_round_question(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            purpose="answer_round_next_question",
            payload={
                "answered_question_id": answered_qa.id,
                "history_count": len(history),
                "audit_history_count": len(generation_history),
                "memory_count": len(effective_memories),
                "question_kind": next_kind,
            },
            qa_history_payload=_merge_generation_history(
                generation_history,
                qa_history_payload,
            ),
            resume_data=resume.structured_data,
            previous_answer=clean_answer,
            effective_memories=effective_memories,
            question_kind=next_kind,
        )
        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        next_qa = create_qa(
            interview_id=interview.id,
            round_id=round_record.id,
            sequence=len(history) + 1,
            question_type=question.question_type,
            question=question.question,
            question_kind=next_kind,
            parent_question_id=parent_question_id,
        )
        self.repository.update_question_count(
            interview.id,
            len(self.repository.list_qa(interview.id)),
        )
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            node_type="question_generated",
            snapshot={"question_id": next_qa.id, "sequence": next_qa.sequence},
        )
        return RoundAnswerResponse(
            action="follow_up" if next_kind == "follow_up" else "next_question",
            question=_round_question_response(next_qa),
        )

    def finish_round(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        finish_type: str = "normal",
    ) -> RoundAnswerResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        self._ensure_interview_not_paused(interview)
        self._ensure_harness_can_continue(interview)
        round_record = self._require_round(interview.id, round_id)
        if round_record.status in FINISHED_ROUND_STATUSES:
            return RoundAnswerResponse(action="finish_round", round_summary=round_record.summary)
        if round_record.status not in ACTIVE_ROUND_STATUSES:
            raise _status_error()
        if finish_type != "early" and round_record.status != "in_progress":
            raise _status_error()
        if finish_type == "early":
            skipped_question = self.repository.get_unanswered_round_question(interview.id, round_id)
            if skipped_question is not None:
                self.repository.update_question_status(skipped_question.id, "skipped")
        history = self.repository.list_round_qa(interview.id, round_id)
        if finish_type != "early" and not _has_answer_evidence(history):
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="正常结束轮次需要至少一条有效回答。",
            )
        resume = _require_resume(self.repository, interview.resume_id, user_id)
        summary = self._generate_round_summary(
            interview=interview,
            round_record=round_record,
            history=history,
            resume=resume,
            is_reference_only=finish_type == "early",
        )
        now = datetime.utcnow()
        status_value = "finished_early" if finish_type == "early" else "completed"
        self.repository.finish_round(interview.id, round_id, status_value, summary, now)
        self.repository.update_question_count(
            interview.id,
            len(self.repository.list_qa(interview.id)),
        )
        self.repository.touch_interview(interview.id, now, _elapsed_seconds(interview, now))
        return RoundAnswerResponse(action="finish_round", round_summary=summary)

    def finish_multi_round_interview(
        self,
        user_id: int,
        interview_id: int,
        finish_type: str = "normal",
    ) -> FeedbackReportResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        if interview.overall_status == "paused":
            if finish_type != "early":
                raise _status_error()
            now = datetime.utcnow()
            self.repository.resume_interview(interview.id, now, interview.last_active_at)
            interview = self._require_interview(user_id, interview_id)
        rounds = self.list_rounds(interview)
        if finish_type == "early":
            for round_record in rounds:
                if round_record.status == "in_progress":
                    self.finish_round(user_id, interview.id, round_record.id, finish_type="early")
                    break
            self.repository.cancel_pending_rounds(interview.id)
            refreshed_interview = self._require_interview(user_id, interview_id)
            rounds = self.list_rounds(refreshed_interview)
        elif any(round_record.status in ACTIVE_ROUND_STATUSES for round_record in rounds):
            raise _status_error()

        existing_report = (
            self.repository.get_feedback_report(interview.id)
            if hasattr(self.repository, "get_feedback_report")
            else None
        )
        if existing_report is not None:
            self._record_completion_quality_signal(
                interview=interview,
                rounds=rounds,
                report=existing_report,
            )
            return _feedback_report_response(existing_report)

        self._assert_final_report_allowed(interview, rounds, finish_type)
        if self.evaluation_service is not None:
            resume = _require_resume(self.repository, interview.resume_id, user_id)
            report = self.evaluation_service.generate_final_report(
                interview=interview,
                resume=resume,
                rounds=rounds,
            )
        else:
            report = _overall_report(interview.id, rounds, is_reference_only=finish_type == "early")
        reliability_status = _report_reliability_status(interview, report, finish_type)
        report_payload = {
            "interview_id": interview.id,
            "score": report["score"],
            "weaknesses": report["weaknesses"],
            "suggestions": report["suggestions"],
            "recommendation": report["recommendation"],
            "round_scores": report["round_scores"],
            "strengths": report["strengths"],
            "ability_analysis": report.get("ability_analysis"),
            "job_match": report.get("job_match"),
            "final_conclusion": report.get("final_conclusion"),
            "confidence": report.get("confidence"),
            "reference_note": report["reference_note"],
            "report_reliability_status": reliability_status,
        }
        create_report = getattr(
            self.repository,
            "create_feedback_report_idempotent",
            self.repository.create_feedback_report,
        )
        try:
            saved_report = create_report(**report_payload)
        except TypeError:
            report_payload.pop("report_reliability_status")
            saved_report = create_report(**report_payload)
        now = datetime.utcnow()
        self.repository.mark_multi_finished(interview.id, now, _elapsed_seconds(interview, now))
        self._update_interview_harness(interview.id, harness_status="completed")
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=None,
            node_type="final_report_generated",
            snapshot={"report_reliability_status": reliability_status},
        )
        memory_enabled = self._is_memory_enabled(user_id)
        if memory_enabled:
            self._enqueue_memory_summary(user_id=user_id, interview_id=interview.id)
        finished_interview = self._require_interview(user_id, interview_id)
        self._record_completion_quality_signal(
            interview=finished_interview,
            rounds=rounds,
            report=saved_report,
        )
        return _feedback_report_response(
            saved_report,
            detailed_feedback=report.get("detailed_feedback"),
        )

    def pause_interview(self, user_id: int, interview_id: int) -> InterviewStateResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        if interview.overall_status == "paused":
            return self.get_state(user_id, interview_id)
        if interview.overall_status != "in_progress":
            raise _status_error()
        if not any(item.status == "in_progress" for item in self.list_rounds(interview)):
            raise _status_error()
        now = datetime.utcnow()
        self.repository.pause_interview(interview.id, now, _elapsed_seconds(interview, now))
        return self.get_state(user_id, interview_id)

    def resume_interview(self, user_id: int, interview_id: int) -> InterviewStateResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        if interview.overall_status != "paused":
            raise _status_error()
        now = datetime.utcnow()
        self.repository.resume_interview(interview.id, now, interview.last_active_at)
        return self.get_state(user_id, interview_id)

    def _is_memory_enabled(self, user_id: int) -> bool:
        if self.preferences_repository is None:
            return True
        try:
            return self.preferences_repository.get_memory_enabled(user_id)
        except Exception:
            return True

    def _enqueue_memory_summary(self, *, user_id: int, interview_id: int) -> None:
        if self.memory_task_service is None:
            return
        try:
            self.memory_task_service.create_summary_task_if_enabled(
                user_id=user_id,
                interview_id=interview_id,
            )
        except Exception:
            return

    def _resolve_version_bundle_id(
        self,
        *,
        job_family: str | None = None,
        developer_user_id: int | None = None,
    ) -> int | None:
        try:
            return resolve_active_version_bundle_id(
                self.repository,
                job_family=job_family,
                developer_user_id=developer_user_id,
            )
        except Exception:
            return None

    def _record_completion_quality_signal(
        self,
        *,
        interview: InterviewRecord,
        rounds: list[InterviewRoundRecord],
        report: FeedbackReportRecord,
    ) -> None:
        try:
            record_interview_completion_quality_signal(
                repository=self.repository,
                interview=interview,
                rounds=rounds,
                qa_history=self.repository.list_qa(interview.id, include_inactive=True),
                report=report,
            )
        except Exception:
            return

    def _retrieve_effective_memories(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        scene: str,
        intent: str,
        query_text: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.memory_retrieval_service is None:
            return []
        try:
            memory_enabled = (
                self.preferences_repository.get_memory_enabled(user_id)
                if self.preferences_repository is not None
                else True
            )
            result = self.memory_retrieval_service.retrieve(
                MemoryRetrievalRequest(
                    user_id=user_id,
                    memory_enabled=memory_enabled,
                    interview_id=interview.id,
                    round_id=round_record.id,
                    agent_type=round_record.round_type,
                    usage_scene=scene,  # type: ignore[arg-type]
                    intent=intent,
                    query_text=query_text,
                )
            )
            return [item.model_dump() for item in result.memories]
        except Exception:
            self._update_interview_harness(
                interview.id,
                harness_status="degraded",
                last_harness_error="memory_retrieval_failed",
                had_degradation=True,
            )
            _record_harness_event(
                user_id=user_id,
                interview_id=interview.id,
                round_id=round_record.id,
                node_type="context_retriever",
                event_type="degraded",
                payload={"scene": scene, "reason": "memory_retrieval_failed"},
            )
            return []

    def _generate_round_question(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        purpose: str,
        payload: dict[str, Any],
        qa_history_payload: list[dict[str, Any]],
        resume_data: dict[str, Any],
        previous_answer: str | None,
        effective_memories: list[dict[str, Any]],
        question_kind: str,
    ) -> Any:
        agent = get_round_agent(round_record.round_type, self.llm_client)
        fallback_error: AppError | None = None

        def generate_or_fallback() -> Any:
            nonlocal fallback_error
            try:
                return agent.generate_question(
                    resume=resume_data,
                    target_position=interview.target_position,
                    qa_history=qa_history_payload,
                    previous_answer=previous_answer,
                    effective_memories=effective_memories,
                    question_kind=question_kind,
                )
            except AppError as exc:
                if exc.code not in {ErrorCode.BUSINESS_ERROR, ErrorCode.NETWORK_TIMEOUT}:
                    raise
                fallback_error = exc
                return agent.fallback_question(qa_history_payload, question_kind)

        question = self._execute_harness_call(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            node_type="round_question_generator",
            agent_type=round_record.agent_type,
            purpose=purpose,
            payload=payload,
            operation=generate_or_fallback,
        )
        if fallback_error is not None:
            fallback = agent.fallback_question(qa_history_payload, question_kind)
            self._update_interview_harness(
                interview.id,
                harness_status="degraded",
                last_harness_error=str(fallback_error) or fallback_error.__class__.__name__,
                had_degradation=True,
            )
            self._update_round_execution(round_record.id, execution_status="degraded")
            _record_harness_event(
                user_id=user_id,
                interview_id=interview.id,
                round_id=round_record.id,
                node_type="round_question_generator",
                event_type="degraded",
                payload={
                    "purpose": purpose,
                    "reason": "question_generation_failed",
                    "fallback_question_type": fallback.question_type,
                },
            )
        return question

    def _generate_round_summary(
        self,
        *,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        history: list[QARecord],
        resume: Any,
        is_reference_only: bool,
    ) -> dict[str, Any]:
        if self.evaluation_service is None:
            agent = get_round_agent(round_record.round_type, self.llm_client)
            agent.spec = resolve_round_spec(
                self.repository,
                version_bundle_id=interview.version_bundle_id,
                base_spec=agent.spec,
            )
            return cast(
                dict[str, Any],
                self._execute_harness_call(
                    user_id=interview.user_id,
                    interview=interview,
                    round_record=round_record,
                    node_type="round_evaluator",
                    agent_type=round_record.agent_type,
                    purpose="fallback_round_summary",
                    payload={"history_count": len(history), "is_reference_only": is_reference_only},
                    operation=lambda: agent.summarize(
                        history,
                        is_reference_only=is_reference_only,
                    ),
                ),
            )
        question_scores = self.evaluation_service.fill_missing_question_scores(
            interview=interview,
            round_record=round_record,
            qa_history=history,
            resume=resume,
        )
        return self.evaluation_service.generate_round_summary(
            interview=interview,
            round_record=round_record,
            qa_history=history,
            question_scores=question_scores,
            is_reference_only=is_reference_only,
        )

    def _execute_harness_call(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord | None,
        node_type: str,
        agent_type: str | None,
        purpose: str,
        payload: dict[str, Any],
        operation: Callable[[], Any],
    ) -> Any:
        self._update_interview_harness(interview.id, harness_status="running")
        if round_record is not None:
            self._update_round_execution(round_record.id, execution_status="running")
        self.repository.commit()
        try:
            result = _execute_with_harness(
                connection=getattr(self.repository, "connection", None),
                user_id=user_id,
                interview_id=interview.id,
                round_id=round_record.id if round_record is not None else None,
                node_type=node_type,
                agent_type=agent_type,
                purpose=purpose,
                payload=payload,
                operation=operation,
            )
        except AppError as exc:
            self._update_interview_harness(
                interview.id,
                harness_status="pending",
                last_harness_error=str(exc) or exc.__class__.__name__,
            )
            if round_record is not None:
                self._update_round_execution(round_record.id, execution_status="failed")
            raise
        except Exception as exc:
            self._update_interview_harness(
                interview.id,
                harness_status="failed",
                last_harness_error=str(exc) or exc.__class__.__name__,
            )
            if round_record is not None:
                self._update_round_execution(round_record.id, execution_status="failed")
            raise
        if round_record is not None:
            self._update_round_execution(round_record.id, execution_status="completed")
        return result

    def _record_checkpoint(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord | None,
        node_type: str,
        snapshot: dict[str, Any],
    ) -> None:
        try:
            checkpoint_id = _save_harness_checkpoint(
                connection=getattr(self.repository, "connection", None),
                user_id=user_id,
                interview_id=interview.id,
                round_id=round_record.id if round_record is not None else None,
                node_type=node_type,
                snapshot=snapshot,
            )
            self._update_interview_harness(
                interview.id,
                last_checkpoint_id=checkpoint_id,
                last_harness_error="",
            )
        except Exception as exc:
            self._update_interview_harness(
                interview.id,
                harness_status="paused",
                last_harness_error=str(exc) or exc.__class__.__name__,
            )
            if round_record is not None:
                self._update_round_execution(round_record.id, execution_status="paused")

    def _ensure_harness_can_continue(self, interview: InterviewRecord) -> None:
        if interview.harness_status in {"paused", "failed"}:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="面试当前步骤暂不可继续，请稍后重试。",
            )

    def _ensure_interview_not_paused(self, interview: InterviewRecord) -> None:
        if interview.overall_status == "paused":
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="面试已暂停，请先继续面试。",
            )

    def _update_interview_harness(self, interview_id: int, **values: Any) -> None:
        method = getattr(self.repository, "update_interview_harness", None)
        if callable(method):
            method(interview_id, **values)

    def _update_round_execution(self, round_id: int, **values: Any) -> None:
        method = getattr(self.repository, "update_round_execution", None)
        if callable(method):
            method(round_id, **values)

    def _assert_final_report_allowed(
        self,
        interview: InterviewRecord,
        rounds: list[InterviewRoundRecord],
        finish_type: str,
    ) -> None:
        if interview.harness_status == "failed":
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="面试执行校验失败，暂不能生成最终报告。",
            )
        selected = set(interview.selected_rounds or ROUND_ORDER)
        selected_rounds = [item for item in rounds if item.round_type in selected]
        if finish_type != "early":
            missing = [
                item.round_type
                for item in selected_rounds
                if item.status not in FINISHED_ROUND_STATUSES
            ]
            if missing:
                raise AppError(
                    ErrorCode.BUSINESS_ERROR,
                    status.HTTP_409_CONFLICT,
                    message="存在未完成关键轮次，暂不能生成最终报告。",
                )
        answered_by_round = {
            round_id
            for round_id in [item.id for item in selected_rounds]
            if any(
                qa.answer and qa.answer.strip()
                for qa in self.repository.list_round_qa(interview.id, round_id)
            )
        }
        invalid_scored_rounds = [
            item.round_type
            for item in selected_rounds
            if item.status in FINISHED_ROUND_STATUSES
            and item.score is not None
            and item.score > 0
            and item.id not in answered_by_round
        ]
        if invalid_scored_rounds:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="评分缺少真实问答证据，暂不能生成最终报告。",
            )

    def _require_interview(self, user_id: int, interview_id: int) -> InterviewRecord:
        interview = self.repository.get_interview_for_user(interview_id, user_id)
        if interview is None:
            raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)
        return interview

    def _require_round(self, interview_id: int, round_id: int) -> InterviewRoundRecord:
        round_record = self.repository.get_round(interview_id, round_id)
        if round_record is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        return round_record

    def _ensure_previous_rounds_finished(
        self,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
    ) -> None:
        rounds = self.list_rounds(interview)
        for item in rounds:
            if item.id == round_record.id:
                return
            if item.status == "skipped":
                continue
            if item.status not in FINISHED_ROUND_STATUSES:
                raise _status_error()


def _require_resume(
    repository: InterviewRepository,
    resume_id: int,
    user_id: int,
) -> Any:
    resume = repository.get_resume_for_user(resume_id, user_id)
    if resume is None:
        raise AppError(ErrorCode.FORBIDDEN, status.HTTP_403_FORBIDDEN)
    return resume


def _has_answer_evidence(history: list[QARecord]) -> bool:
    return any(qa.answer is not None and qa.answer.strip() for qa in history)


def _qa_history(
    qa_records: list[QARecord],
    answer_override: dict[int, str] | None = None,
    evaluation_by_qa_id: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    overrides = answer_override or {}
    evaluations = evaluation_by_qa_id or {}
    history: list[dict[str, Any]] = []
    for qa in qa_records:
        item = {
            "id": qa.id,
            "sequence": qa.sequence,
            "question_type": qa.question_type,
            "question": qa.question,
            "answer": overrides.get(qa.sequence, qa.answer),
            "question_kind": qa.question_kind,
            "question_status": qa.question_status,
            "parent_question_id": qa.parent_question_id,
            "regenerated_from_question_id": qa.regenerated_from_question_id,
        }
        evaluation = evaluations.get(qa.id)
        if evaluation is not None:
            item["evaluation_follow_up"] = evaluation
        history.append(item)
    return history


def _merge_generation_history(
    audit_history: list[QARecord],
    active_history_payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    payload_by_id = {
        int(item["id"]): item
        for item in active_history_payload
        if isinstance(item.get("id"), int)
    }
    return [payload_by_id.get(qa.id, _qa_history([qa])[0]) for qa in audit_history]


def _normalize_selected_rounds(selected_rounds: list[str] | None) -> list[str]:
    values = list(ROUND_ORDER) if selected_rounds is None else selected_rounds
    seen: set[str] = set()
    normalized: list[str] = []
    for item in values:
        if item not in ROUND_SPECS or item in seen:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        seen.add(item)
        normalized.append(item)
    if not normalized:
        raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
    return normalized


def _round_rows(
    interview_id: int,
    selected_rounds: list[str],
    *,
    repository: Any | None = None,
    version_bundle_id: int | None = None,
) -> list[dict[str, Any]]:
    selected = set(selected_rounds)
    rows: list[dict[str, Any]] = []
    row_order = [*selected_rounds, *[item for item in ROUND_ORDER if item not in selected]]
    for round_type in row_order:
        spec = ROUND_SPECS[round_type]
        if repository is not None:
            spec = resolve_round_spec(
                repository,
                version_bundle_id=version_bundle_id,
                base_spec=spec,
            )
        rows.append(
            {
                "interview_id": interview_id,
                "agent_type": spec.agent_type,
                "round_type": round_type,
                "status": "pending" if round_type in selected else "skipped",
                "min_main_questions": spec.min_main_questions,
                "max_main_questions": spec.max_main_questions,
                "min_total_questions": spec.min_total_questions,
                "max_total_questions": spec.max_total_questions,
            }
        )
    return rows


def _ordered_rounds(
    interview: InterviewRecord,
    rounds: list[InterviewRoundRecord],
) -> list[InterviewRoundRecord]:
    selected_order = interview.selected_rounds or list(ROUND_ORDER)
    order = {round_type: index for index, round_type in enumerate(selected_order)}
    skipped_order = {
        round_type: len(order) + index for index, round_type in enumerate(ROUND_ORDER)
    }
    return sorted(
        rounds,
        key=lambda item: order.get(item.round_type, skipped_order.get(item.round_type, len(order))),
    )


def _round_response(
    round_record: InterviewRoundRecord,
    interview: InterviewRecord | None = None,
) -> InterviewRoundResponse:
    elapsed_seconds = 0
    if round_record.started_at is not None:
        ended_at = round_record.ended_at
        if ended_at is None and round_record.status == "in_progress":
            if interview is not None and interview.overall_status == "paused":
                ended_at = interview.last_active_at
            else:
                ended_at = datetime.utcnow()
        if ended_at is not None:
            elapsed_seconds = max(0, int((ended_at - round_record.started_at).total_seconds()))

    return InterviewRoundResponse(
        id=round_record.id,
        round_type=round_record.round_type,
        status=round_record.status,
        score=round_record.score,
        result=round_record.result,
        summary=round_record.summary,
        started_at=round_record.started_at,
        ended_at=round_record.ended_at,
        elapsed_seconds=elapsed_seconds,
        execution_status=round_record.execution_status,
        retry_count=round_record.retry_count,
    )


def _round_question_response(qa: QARecord) -> RoundQuestionResponse:
    if qa.round_id is None:
        raise AppError(ErrorCode.BUSINESS_ERROR, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return RoundQuestionResponse(
        id=qa.id,
        round_id=qa.round_id,
        sequence=qa.sequence,
        question_kind=qa.question_kind,
        question_status=qa.question_status,
        parent_question_id=qa.parent_question_id,
        regenerated_from_question_id=qa.regenerated_from_question_id,
        question_type=qa.question_type,
        question=qa.question,
    )


def _feedback_report_response(
    report: FeedbackReportRecord,
    detailed_feedback: dict[str, Any] | None = None,
) -> FeedbackReportResponse:
    return FeedbackReportResponse(
        interview_id=report.interview_id,
        score=report.score,
        weaknesses=report.weaknesses,
        suggestions=report.suggestions,
        recommendation=report.recommendation,
        round_scores=report.round_scores,
        strengths=report.strengths,
        ability_analysis=report.ability_analysis,
        job_match=report.job_match,
        final_conclusion=report.final_conclusion,
        confidence=report.confidence,
        reference_note=report.reference_note,
        used_candidate_memory=report.used_candidate_memory,
        report_reliability_status=getattr(report, "report_reliability_status", "normal"),
        detailed_feedback=detailed_feedback,
    )


def _answer_action_for_question(qa: QARecord) -> str:
    return "follow_up" if qa.question_kind == "follow_up" else "next_question"


def _qa_state_item(
    qa: QARecord,
    question_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": qa.id,
        "round_id": qa.round_id,
        "sequence": qa.sequence,
        "question_type": qa.question_type,
        "question": qa.question,
        "answer": qa.answer,
        "question_kind": qa.question_kind,
        "question_status": qa.question_status,
        "parent_question_id": qa.parent_question_id,
        "regenerated_from_question_id": qa.regenerated_from_question_id,
        "created_at": qa.created_at,
    }
    if question_evaluation is not None:
        payload["question_evaluation"] = question_evaluation
    return payload


def _next_question_kind(
    current_qa: QARecord,
    history: list[QARecord],
    round_record: InterviewRoundRecord,
    follow_up_recommended: bool | None = None,
) -> str:
    counts = count_questions(history)
    if counts["total"] >= round_record.max_total_questions:
        return "main"
    if (
        current_qa.question_kind == "main"
        and counts["main"] >= round_record.max_main_questions
    ):
        return "follow_up"
    has_follow_up = any(qa.parent_question_id == current_qa.id for qa in history)
    if current_qa.question_kind == "main" and not has_follow_up:
        if follow_up_recommended is False:
            return "main"
        return "follow_up"
    if follow_up_recommended is True and current_qa.question_kind == "main":
        return "follow_up"
    return "main"


def _parent_answer(history: list[QARecord], qa: QARecord) -> str | None:
    if qa.parent_question_id is None:
        return None
    parent = next((item for item in history if item.id == qa.parent_question_id), None)
    return parent.answer if parent is not None else None


def _elapsed_seconds(interview: InterviewRecord, now: datetime) -> int:
    if interview.last_active_at is None or interview.overall_status != "in_progress":
        return interview.elapsed_seconds
    delta = int((now - interview.last_active_at).total_seconds())
    if delta <= 0:
        return interview.elapsed_seconds
    return interview.elapsed_seconds + min(delta, ELAPSED_SECONDS_CAP)


def _overall_report(
    interview_id: int,
    rounds: list[InterviewRoundRecord],
    is_reference_only: bool,
) -> dict[str, Any]:
    scored_rounds = [
        round_record
        for round_record in rounds
        if round_record.status in FINISHED_ROUND_STATUSES and round_record.score is not None
    ]
    score = (
        int(sum(round_record.score or 0 for round_record in scored_rounds) / len(scored_rounds))
        if scored_rounds
        else 0
    )
    recommendation = "建议进入下一轮" if is_reference_only else _recommendation(score)
    round_scores = [
        {
            "round_type": round_record.round_type,
            "score": round_record.score,
            "result": round_record.result,
            "is_reference_only": round_record.is_reference_only,
            "status": round_record.status,
        }
        for round_record in rounds
    ]
    reference_note = "面试提前结束，评价仅供参考。" if is_reference_only else None
    return {
        "interview_id": interview_id,
        "score": score,
        "weaknesses": ["部分能力维度仍需结合后续面试继续验证。"],
        "suggestions": ["复盘每轮回答，补充更具体的项目证据、技术取舍和结果数据。"],
        "recommendation": recommendation,
        "round_scores": round_scores,
        "strengths": ["已完成轮次中存在可验证的岗位相关证据。"] if score >= 60 else [],
        "reference_note": reference_note,
    }


def _report_reliability_status(
    interview: InterviewRecord,
    report: dict[str, Any],
    finish_type: str,
) -> str:
    if interview.harness_status == "failed":
        return "unavailable"
    if finish_type == "early" or interview.had_degradation or interview.recovery_count > 0:
        return "reference_only"
    if report.get("reference_note"):
        return "reference_only"
    return "normal"


def _execute_with_harness(
    *,
    connection: Any | None = None,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    agent_type: str | None,
    purpose: str,
    payload: dict[str, Any],
    operation: Callable[[], Any],
) -> Any:
    service = _get_harness_service()
    if service is None:
        repository = _get_harness_repository(connection)
        if repository is None:
            return operation()
        request = _harness_request(
            user_id=user_id,
            interview_id=interview_id,
            round_id=round_id,
            node_type=node_type,
            agent_type=agent_type,
            purpose=purpose,
            payload=payload,
        )
        try:
            trace_id = repository.create_trace(request)
        except Exception:
            return operation()
        if connection is not None:
            connection.commit()
        try:
            result = operation()
        except Exception as exc:
            try:
                repository.update_trace_status(
                    trace_id,
                    status="failed",
                    validation_status="failed",
                    error_code="BUSINESS_EXECUTION_FAILED",
                    error_detail=str(exc) or exc.__class__.__name__,
                )
                _save_fallback_rule_evaluations(
                    repository=repository,
                    request=request,
                    trace_id=trace_id,
                    validation_status="failed",
                    error_detail=str(exc) or exc.__class__.__name__,
                )
            except Exception:
                pass
            raise
        try:
            repository.update_trace_status(
                trace_id,
                status="completed",
                validation_status="passed",
                output_snapshot={"result": _snapshot_value(result)},
            )
            _save_fallback_rule_evaluations(
                repository=repository,
                request=request,
                trace_id=trace_id,
                validation_status="passed",
            )
        except Exception:
            pass
        return result
    request = _harness_request(
        user_id=user_id,
        interview_id=interview_id,
        round_id=round_id,
        node_type=node_type,
        agent_type=agent_type,
        purpose=purpose,
        payload=payload,
    )
    for method_name in ("execute_callable", "run_callable", "wrap"):
        method = getattr(service, method_name, None)
        if callable(method):
            result = method(request, operation)
            return _harness_business_result(result)
    execute = getattr(service, "execute", None)
    if callable(execute):
        try:
            result = execute(request=request, operation=operation)
        except TypeError:
            result = execute(request, operation)
        return _harness_business_result(result)
    return operation()


def _save_fallback_rule_evaluations(
    *,
    repository: Any,
    request: Any,
    trace_id: int,
    validation_status: str,
    error_detail: str | None = None,
    checkpoint_id: int | None = None,
) -> None:
    try:
        from app.harness.output_validation import OutputValidationResult
        from app.harness.rules import RuleEvaluator

        validation = OutputValidationResult(
            validation_status=_coerce_validation_status(validation_status),
            errors=[error_detail] if validation_status == "failed" and error_detail else [],
        )
        evaluator = RuleEvaluator(repository)
        evaluations = evaluator.evaluate_node(
            request,
            trace_id=trace_id,
            checkpoint_id=checkpoint_id,
            output_validation=validation,
            retry_count=0,
            event_write_failed=False,
        )
        evaluator.save_all(
            user_id=request.user_id,
            interview_id=request.interview_id,
            trace_id=trace_id,
            evaluations=evaluations,
        )
    except Exception:
        return


def _coerce_validation_status(value: str) -> ValidationStatus:
    if value in {"pending", "passed", "warning", "failed"}:
        return cast(ValidationStatus, value)
    return "failed"


def _save_harness_checkpoint(
    *,
    connection: Any | None = None,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    snapshot: dict[str, Any],
) -> int | None:
    service = _get_harness_service()
    if service is None:
        repository = _get_harness_repository(connection)
        if repository is None:
            return None
        checkpoint = _harness_checkpoint(
            user_id=user_id,
            interview_id=interview_id,
            round_id=round_id,
            node_type=node_type,
            snapshot=snapshot,
        )
        return cast(int, repository.create_checkpoint(checkpoint))
    payload = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": round_id,
        "node_type": node_type,
        "snapshot": snapshot,
    }
    for method_name in ("save_checkpoint", "create_checkpoint", "checkpoint"):
        method = getattr(service, method_name, None)
        if callable(method):
            result = method(**payload)
            return _extract_int_attr(result, "checkpoint_id") or _extract_int_attr(result, "id")
    return None


def _record_harness_event(
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    service = _get_harness_service()
    if service is None:
        return
    event_payload = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": round_id,
        "node_type": node_type,
        "event_type": event_type,
        "payload": payload,
    }
    for method_name in ("record_event", "create_event", "trace_event"):
        method = getattr(service, method_name, None)
        if callable(method):
            method(**event_payload)
            return


def _get_harness_service() -> Any | None:
    try:
        module = import_module("app.harness.execution")
    except Exception:
        return None
    for factory_name in ("get_harness_execution_service", "get_execution_service"):
        factory = getattr(module, factory_name, None)
        if callable(factory):
            return factory()
    service = getattr(module, "harness_execution_service", None)
    if service is not None:
        return service
    service_class = getattr(module, "HarnessExecutionService", None)
    if callable(service_class):
        try:
            return service_class()
        except TypeError:
            return None
    return None


def _get_harness_repository(connection: Any | None) -> Any | None:
    if connection is None:
        return None
    try:
        module = import_module("app.repositories.harness")
        repository_class = getattr(module, "HarnessRepository", None)
        if callable(repository_class):
            return repository_class(connection)
    except Exception:
        return None
    return None


def _harness_request(
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    agent_type: str | None,
    purpose: str,
    payload: dict[str, Any],
) -> Any:
    payload_key = _harness_payload_key(payload)
    data = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": round_id,
        "node_id": f"{interview_id}:{round_id or 'interview'}:{node_type}",
        "node_type": node_type,
        "agent_type": agent_type or node_type,
        "purpose": purpose,
        "context_refs": payload,
        "input_payload": payload,
        "execution_mode": "normal",
        "idempotency_key": f"{interview_id}:{round_id or 0}:{node_type}:{purpose}:{payload_key}",
    }
    try:
        contracts = import_module("app.harness.contracts")
        request_class = getattr(contracts, "HarnessExecutionRequest", None)
        if callable(request_class):
            return request_class(**data)
    except Exception:
        pass
    return data


def _harness_checkpoint(
    *,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    snapshot: dict[str, Any],
) -> Any:
    data = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": round_id,
        "trace_id": None,
        "node_id": f"{interview_id}:{round_id or 'interview'}:{node_type}",
        "checkpoint_type": node_type,
        "snapshot": snapshot,
    }
    contracts = import_module("app.harness.contracts")
    return contracts.CheckpointCreate(**data)


def _harness_business_result(result: Any) -> Any:
    if result is None:
        return None
    if hasattr(result, "business_result"):
        return result.business_result
    if isinstance(result, dict) and "business_result" in result:
        return result["business_result"]
    return result


def _harness_payload_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _snapshot_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]


def _extract_int_attr(value: Any, name: str) -> int | None:
    if value is None:
        return None
    raw_value = getattr(value, name, None)
    if raw_value is None and isinstance(value, dict):
        raw_value = value.get(name)
    return int(raw_value) if raw_value is not None else None


def _snapshot_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: _snapshot_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_snapshot_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _recommendation(score: int) -> str:
    if score >= 85:
        return "强烈建议录用"
    if score >= 75:
        return "建议录用"
    if score >= 65:
        return "谨慎录用"
    if score >= 60:
        return "暂缓决定"
    return "不建议录用"


def _require_multi_round(interview: InterviewRecord) -> None:
    if interview.mode != "multi_round":
        raise _status_error()


def _status_error() -> AppError:
    return AppError(
        ErrorCode.BUSINESS_ERROR,
        status.HTTP_400_BAD_REQUEST,
        message="面试状态不允许当前操作。",
    )
