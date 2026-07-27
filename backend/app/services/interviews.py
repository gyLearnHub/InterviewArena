import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from typing import Any, cast

from fastapi import status

from app.agents import ROUND_ORDER, count_questions, get_round_agent
from app.autonomous_evolution.catalog import bootstrap_artifacts
from app.autonomous_evolution.observation import (
    is_hard_runtime_error,
    observe_completed_interview,
    record_runtime_execution,
    validate_runtime_output,
)
from app.autonomous_evolution.repository import AutonomousEvolutionRepository
from app.autonomous_evolution.runtime import (
    prepare_interview_evolution_context,
    resolve_artifact_version,
    resolve_interview_harness_policy,
    resolve_round_spec,
)
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, safe_error_code
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.harness.events import (
    build_harness_request as _harness_request,
)
from app.harness.events import (
    get_harness_repository as _get_harness_repository,
)
from app.harness.events import (
    record_harness_event,
)
from app.harness.events import (
    save_fallback_rule_evaluations as _save_fallback_rule_evaluations,
)
from app.harness.events import (
    snapshot_harness_value as _snapshot_value,
)
from app.repositories.interviews import (
    FeedbackReportRecord,
    InterviewRecord,
    InterviewRepository,
    InterviewRoundRecord,
    QARecord,
    ReanswerAttemptLimitError,
)
from app.repositories.preferences import PreferencesRepository
from app.schemas.interview import (
    DEFAULT_INTERVIEW_DIFFICULTY,
    DEFAULT_INTERVIEW_EXPERIENCE_MODE,
    DEFAULT_INTERVIEW_GOAL,
    DEFAULT_TIME_LIMIT_MINUTES,
    JOB_DESCRIPTION_MAX_LENGTH,
    ROUND_ANSWER_MAX_LENGTH,
    AnswerDraftResponse,
    AnswerReanswerListResponse,
    AnswerReanswerResponse,
    FeedbackReportResponse,
    InterviewDifficulty,
    InterviewExperienceMode,
    InterviewGoal,
    InterviewStateResponse,
    RoundAnswerResponse,
    RoundQuestionResponse,
    TimeLimitMinutes,
)
from app.schemas.memory import MemoryRetrievalRequest
from app.services.evaluations import EvaluationSchedulerService
from app.services.interview_helpers import (
    ACTIVE_QUESTION_STATUS,
    ACTIVE_ROUND_STATUSES,
    FINAL_QUESTION_TYPE,
    FINISHED_ROUND_STATUSES,
    ROUND_CLOSING_WINDOW_SECONDS,
    _active_round_answer_evaluation,
    _answer_action_for_question,
    _answer_evaluation_response,
    _elapsed_seconds,
    _elapsed_seconds_uncapped,
    _fallback_answer_evaluation,
    _feedback_report_response,
    _final_round_question,
    _has_answer_evidence,
    _is_final_question,
    _merge_generation_history,
    _next_question_kind,
    _normalize_experience_mode,
    _normalize_interview_difficulty,
    _normalize_interview_goal,
    _normalize_optional_practice_text,
    _normalize_practice_text,
    _normalize_selected_rounds,
    _normalize_time_limit_minutes,
    _ordered_rounds,
    _overall_report,
    _parent_answer,
    _practice_job_description,
    _practice_rounds,
    _qa_history,
    _qa_state_item,
    _reanswer_attempt_response,
    _report_reliability_status,
    _require_resume,
    _round_question_response,
    _round_remaining_seconds,
    _round_response,
    _round_rows,
    _with_final_question_notice,
)
from app.services.interview_strategy import interview_strategy_payload
from app.services.llm import LLMClient
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.memory_tasks import MemoryTaskService
from app.services.short_term_memory import ShortTermMemoryService
from app.services.weakness_practice_progress import (
    classify_practice_status,
    weakness_key,
)
from app.skills import DEFAULT_SKILL_RUNNER, SkillContext, SkillRunBundle
from app.skills.types import SkillStage

LOGGER = logging.getLogger(__name__)

class InterviewService:
    def __init__(
        self,
        repository: InterviewRepository,
        llm_client: LLMClient,
        evaluation_service: EvaluationSchedulerService | None = None,
        memory_task_service: MemoryTaskService | None = None,
        memory_retrieval_service: MemoryRetrievalService | None = None,
        preferences_repository: PreferencesRepository | None = None,
        short_term_memory_service: ShortTermMemoryService | None = None,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.evaluation_service = evaluation_service
        self.memory_task_service = memory_task_service
        self.memory_retrieval_service = memory_retrieval_service
        self.preferences_repository = preferences_repository
        self.short_term_memory_service = short_term_memory_service

    def create_interview(
        self,
        user_id: int,
        resume_id: int,
        target_position: str,
        job_description: str | None = None,
        selected_rounds: list[str] | None = None,
        interview_goal: str = DEFAULT_INTERVIEW_GOAL,
        difficulty: str = DEFAULT_INTERVIEW_DIFFICULTY,
        experience_mode: str = DEFAULT_INTERVIEW_EXPERIENCE_MODE,
        time_limit_minutes: int = DEFAULT_TIME_LIMIT_MINUTES,
        resume_snapshot: dict[str, Any] | None = None,
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
        source_resume = _require_resume(
            self.repository,
            resume_id,
            user_id,
            snapshot=resume_snapshot,
        )
        immutable_resume_snapshot = dict(
            resume_snapshot
            if resume_snapshot is not None
            else source_resume.structured_data
        )
        rounds = _normalize_selected_rounds(selected_rounds)
        goal = _normalize_interview_goal(interview_goal)
        difficulty_value = _normalize_interview_difficulty(difficulty)
        experience_mode_value = _normalize_experience_mode(experience_mode)
        time_limit = _normalize_time_limit_minutes(time_limit_minutes)
        try:
            interview = self.repository.create_interview(
                user_id,
                resume_id,
                target,
                mode="multi_round",
                job_description=clean_job_description,
                selected_rounds=rounds,
                interview_goal=goal,
                difficulty=difficulty_value,
                experience_mode=experience_mode_value,
                time_limit_minutes=time_limit,
                resume_snapshot=immutable_resume_snapshot,
            )
        except TypeError:
            try:
                interview = self.repository.create_interview(
                    user_id,
                    resume_id,
                    target,
                    mode="multi_round",
                    job_description=clean_job_description,
                    selected_rounds=rounds,
                    interview_goal=goal,
                    difficulty=difficulty_value,
                    experience_mode=experience_mode_value,
                    time_limit_minutes=time_limit,
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
            interview = InterviewRecord(
                **{
                    **interview.__dict__,
                    "interview_goal": goal,
                    "difficulty": difficulty_value,
                    "experience_mode": experience_mode_value,
                    "time_limit_minutes": time_limit,
                    "resume_snapshot": immutable_resume_snapshot,
                }
            )
        specs = {
            round_type: resolve_round_spec(
                getattr(self.repository, "connection", None),
                interview.harness_bundle_id,
                round_type,
            )
            for round_type in ROUND_ORDER
        }
        self.repository.create_rounds(
            _round_rows(
                interview.id,
                rounds,
                specs=specs,
                difficulty=difficulty_value,
                time_limit_minutes=time_limit,
            )
        )
        self._update_interview_harness(interview.id, harness_status="pending")
        self._record_checkpoint(
            user_id=user_id,
            interview=interview,
            round_record=None,
            node_type="create_interview",
            snapshot={
                "resume_id": resume_id,
                "selected_rounds": rounds,
                "interview_strategy": interview_strategy_payload(interview),
            },
        )
        return interview

    def create_weakness_practice(
        self,
        *,
        user_id: int,
        source_interview_id: int,
        weakness: str,
        suggestion: str | None = None,
        round_type: str | None = None,
    ) -> InterviewRecord:
        source = self._require_interview(user_id, source_interview_id)
        _require_multi_round(source)
        source_report = self.repository.get_feedback_report(source.id)
        if source_report is None:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="需要先生成面试报告，才能按薄弱项再练。",
            )
        return self._create_practice_interview(
            user_id=user_id,
            source=source,
            weakness=weakness,
            suggestion=suggestion,
            round_type=round_type,
            source_score=source_report.score,
        )

    def create_review_bookmark_practice(
        self,
        *,
        user_id: int,
        source_interview_id: int,
        weakness: str,
        suggestion: str | None = None,
        round_type: str | None = None,
        source_score: int | None = None,
    ) -> InterviewRecord:
        source = self._require_interview(user_id, source_interview_id)
        _require_multi_round(source)
        return self._create_practice_interview(
            user_id=user_id,
            source=source,
            weakness=weakness,
            suggestion=suggestion,
            round_type=round_type,
            source_score=source_score,
        )

    def _create_practice_interview(
        self,
        *,
        user_id: int,
        source: InterviewRecord,
        weakness: str,
        suggestion: str | None,
        round_type: str | None,
        source_score: int | None,
    ) -> InterviewRecord:
        practice_focus = _normalize_practice_text(weakness)
        practice_suggestion = _normalize_optional_practice_text(suggestion)
        practice_rounds = _practice_rounds(source, round_type)
        practice_job_description = _practice_job_description(
            original_job_description=source.job_description,
            weakness=practice_focus,
            suggestion=practice_suggestion,
            round_type=round_type,
        )
        practice = self.create_interview(
            user_id=user_id,
            resume_id=source.resume_id,
            target_position=source.target_position,
            job_description=practice_job_description,
            selected_rounds=practice_rounds,
            interview_goal=_normalize_interview_goal(source.interview_goal),
            difficulty=_normalize_interview_difficulty(source.difficulty),
            time_limit_minutes=_normalize_time_limit_minutes(source.time_limit_minutes),
            resume_snapshot=source.resume_snapshot,
        )
        create_progress = getattr(self.repository, "create_weakness_practice_progress", None)
        if callable(create_progress):
            create_progress(
                user_id=user_id,
                source_interview_id=source.id,
                practice_interview_id=practice.id,
                weakness_title=practice_focus,
                weakness_key=weakness_key(practice_focus),
                suggestion=practice_suggestion,
                round_type=round_type,
                source_score=source_score,
            )
        return practice

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
        short_term_memory = (
            self.short_term_memory_service.sync_from_records(
                user_id,
                interview,
                rounds=rounds,
                qa_records=qa_history,
                score_by_id=question_scores,
            )
            if self.short_term_memory_service is not None
            and interview.overall_status not in {"finished", "completed", "cancelled"}
            else None
        )
        return InterviewStateResponse(
            interview_id=interview.id,
            mode=interview.mode,
            overall_status=interview.overall_status,
            target_position=interview.target_position,
            job_description=interview.job_description,
            interview_goal=cast(InterviewGoal, interview.interview_goal),
            difficulty=cast(InterviewDifficulty, interview.difficulty),
            experience_mode=cast(InterviewExperienceMode, interview.experience_mode),
            time_limit_minutes=cast(TimeLimitMinutes, interview.time_limit_minutes),
            current_round=interview.current_round,
            elapsed_seconds=_elapsed_seconds_uncapped(interview, datetime.utcnow()),
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
            short_term_memory=short_term_memory,
        )

    def create_reanswer(
        self,
        user_id: int,
        interview_id: int,
        question_id: int,
        answer: str,
    ) -> AnswerReanswerResponse:
        clean_answer = answer.strip()
        if not clean_answer or len(clean_answer) > ROUND_ANSWER_MAX_LENGTH:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        interview, round_record, original_qa = self._require_reanswer_source(
            user_id,
            interview_id,
            question_id,
        )
        try:
            attempt = self.repository.create_reanswer_attempt(
                interview_id=interview.id,
                question_id=original_qa.id,
                answer=clean_answer,
            )
        except ReanswerAttemptLimitError as exc:
            raise AppError(
                ErrorCode.CONFLICT,
                409,
                message="该题最多可保留 20 次重新作答记录。",
            ) from exc
        reanswer_qa = QARecord(
            **{
                **original_qa.__dict__,
                "answer": clean_answer,
            }
        )
        resume = _require_resume(
            self.repository,
            interview.resume_id,
            user_id,
            snapshot=interview.resume_snapshot,
        )
        score_reanswer = getattr(self.evaluation_service, "score_reanswer_attempt", None)
        question_score = (
            score_reanswer(
                interview=interview,
                round_record=round_record,
                qa=reanswer_qa,
                resume=resume,
                attempt_id=attempt.id,
            )
            if callable(score_reanswer)
            else None
        )
        evaluation = _answer_evaluation_response(
            reanswer_qa,
            round_record,
            question_score,
        )
        evaluation["reanswer_attempt_id"] = attempt.id
        attempt = self.repository.update_reanswer_evaluation(
            interview.id,
            original_qa.id,
            attempt.id,
            evaluation,
        )
        original_evaluation = self._original_question_evaluation(
            interview,
            round_record,
            original_qa,
        )
        return AnswerReanswerResponse(
            interview_id=interview.id,
            question_id=original_qa.id,
            question=original_qa.question,
            original_answer=original_qa.answer or "",
            original_evaluation=original_evaluation,
            attempt=_reanswer_attempt_response(attempt, original_evaluation),
        )

    def list_reanswers(
        self,
        user_id: int,
        interview_id: int,
        question_id: int,
    ) -> AnswerReanswerListResponse:
        interview, round_record, original_qa = self._require_reanswer_source(
            user_id,
            interview_id,
            question_id,
        )
        original_evaluation = self._original_question_evaluation(
            interview,
            round_record,
            original_qa,
        )
        attempts = self.repository.list_reanswer_attempts(interview.id, original_qa.id)
        return AnswerReanswerListResponse(
            interview_id=interview.id,
            question_id=original_qa.id,
            question=original_qa.question,
            original_answer=original_qa.answer or "",
            original_evaluation=original_evaluation,
            attempts=[
                _reanswer_attempt_response(
                    item,
                    original_evaluation,
                    fallback_qa=original_qa,
                    round_record=round_record,
                )
                for item in attempts
            ],
        )

    def _require_reanswer_source(
        self,
        user_id: int,
        interview_id: int,
        question_id: int,
    ) -> tuple[InterviewRecord, InterviewRoundRecord, QARecord]:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        if interview.overall_status not in {"finished", "completed"}:
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="面试完成后才能重新作答。",
            )
        original_qa = self.repository.get_qa_by_id(interview.id, question_id)
        if original_qa is None or original_qa.round_id is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if original_qa.answer is None or not original_qa.answer.strip():
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="该题没有原回答，不能重新作答。",
            )
        round_record = self._require_round(interview.id, original_qa.round_id)
        return interview, round_record, original_qa

    def _original_question_evaluation(
        self,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa: QARecord,
    ) -> dict[str, Any]:
        scores_by_id = getattr(self.evaluation_service, "question_scores_by_id", None)
        if callable(scores_by_id):
            evaluation = scores_by_id(interview.id).get(qa.id)
            if isinstance(evaluation, dict):
                return evaluation
        return _fallback_answer_evaluation(qa, round_record)

    def list_rounds(self, interview: InterviewRecord) -> list[InterviewRoundRecord]:
        return _ordered_rounds(interview, self.repository.list_rounds(interview.id))

    def start_round(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        difficulty: str | None = None,
        time_limit_minutes: int | None = None,
        started_at: datetime | None = None,
    ) -> RoundQuestionResponse:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
        self._ensure_interview_not_paused(interview)
        self._ensure_harness_can_continue(interview)
        connection = getattr(self.repository, "connection", None)
        if (
            connection is not None
            and interview.harness_bundle_id is None
            and get_settings().evolution_enabled
        ):
            bound = prepare_interview_evolution_context(
                connection=connection,
                llm_client=self.llm_client,
                user_id=user_id,
                interview_id=interview.id,
                target_position=interview.target_position,
                job_description=interview.job_description,
            )
            if bound is not None:
                interview = self._require_interview(user_id, interview_id)
        round_record = self._require_round(interview.id, round_id)
        if round_record.status == "skipped":
            raise _status_error()
        if round_record.status in FINISHED_ROUND_STATUSES:
            raise _status_error()
        self._ensure_previous_rounds_finished(interview, round_record)

        existing_question = self.repository.get_unanswered_round_question(interview.id, round_id)
        if round_record.status == "in_progress" and existing_question is not None:
            return _round_question_response(existing_question)

        if round_record.status == "pending":
            round_difficulty = _normalize_interview_difficulty(
                difficulty or round_record.difficulty or interview.difficulty
            )
            round_time_limit = _normalize_time_limit_minutes(
                time_limit_minutes
                or round_record.time_limit_minutes
                or interview.time_limit_minutes
            )
            configure_round = getattr(self.repository, "configure_round", None)
            if callable(configure_round):
                configure_round(
                    interview.id,
                    round_id,
                    round_difficulty,
                    round_time_limit,
                )
            now = started_at or datetime.utcnow()
            self.repository.mark_round_started(
                interview_id=interview.id,
                round_id=round_id,
                round_type=round_record.round_type,
                started_at=now,
                elapsed_seconds=_elapsed_seconds(interview, now),
            )
            self.repository.commit()
            round_record = InterviewRoundRecord(
                **{
                    **round_record.__dict__,
                    "status": "in_progress",
                    "started_at": round_record.started_at or now,
                    "difficulty": round_difficulty,
                    "time_limit_minutes": round_time_limit,
                }
            )
        else:
            self._ensure_round_time_remaining(interview, round_record)

        resume = _require_resume(
            self.repository,
            interview.resume_id,
            user_id,
            snapshot=interview.resume_snapshot,
        )
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
        question_type = question.question_type
        question_text = question.question
        if round_record.max_total_questions <= 1:
            question_type, question_text = _with_final_question_notice(
                question_type,
                question_text,
            )
        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        qa = create_qa(
            interview_id=interview.id,
            round_id=round_id,
            sequence=len(history) + 1,
            question_type=question_type,
            question=question_text,
            question_kind="main",
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

    def get_answer_draft(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> AnswerDraftResponse:
        self._require_current_draft_question(user_id, interview_id, round_id, question_id)
        draft = self.repository.get_answer_draft(user_id, interview_id, round_id, question_id)
        return AnswerDraftResponse(
            question_id=question_id,
            answer=draft.answer if draft is not None else None,
            updated_at=draft.updated_at if draft is not None else None,
        )

    def save_answer_draft(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
        answer: str,
    ) -> AnswerDraftResponse:
        if len(answer) > ROUND_ANSWER_MAX_LENGTH:
            raise AppError(ErrorCode.VALIDATION_ERROR, HTTP_422_UNPROCESSABLE_CONTENT)
        self._require_current_draft_question(user_id, interview_id, round_id, question_id)
        if not answer.strip():
            self.repository.delete_answer_draft(user_id, interview_id, round_id, question_id)
            self.repository.commit()
            return AnswerDraftResponse(question_id=question_id)
        draft = self.repository.upsert_answer_draft(
            user_id,
            interview_id,
            round_id,
            question_id,
            answer,
        )
        self.repository.commit()
        return AnswerDraftResponse(
            question_id=question_id,
            answer=draft.answer,
            updated_at=draft.updated_at,
        )

    def delete_answer_draft(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> None:
        self._require_current_draft_question(user_id, interview_id, round_id, question_id)
        self.repository.delete_answer_draft(user_id, interview_id, round_id, question_id)
        self.repository.commit()

    def _require_current_draft_question(
        self,
        user_id: int,
        interview_id: int,
        round_id: int,
        question_id: int,
    ) -> tuple[InterviewRecord, InterviewRoundRecord, QARecord]:
        interview = self._require_interview(user_id, interview_id)
        _require_multi_round(interview)
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
                message="只能保存当前未回答问题的草稿。",
            )
        return interview, round_record, current_qa

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
            self.repository.delete_answer_draft(user_id, interview.id, round_id, current_qa.id)
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

        self.repository.delete_answer_draft(user_id, interview.id, round_id, current_qa.id)
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
        self._ensure_round_time_remaining(interview, round_record)

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

        resume = _require_resume(
            self.repository,
            interview.resume_id,
            user_id,
            snapshot=interview.resume_snapshot,
        )
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
        replacement_type = question.question_type
        replacement_text = question.question
        if _is_final_question(current_qa):
            replacement_type, replacement_text = _with_final_question_notice(
                replacement_type,
                replacement_text,
            )
        updated = self.repository.update_question_status(current_qa.id, "regenerated")
        if not updated:
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="当前问题状态已变化，请刷新后重试。",
            )
        self.repository.delete_answer_draft(user_id, interview.id, round_id, current_qa.id)

        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        next_qa = create_qa(
            interview_id=interview.id,
            round_id=round_record.id,
            sequence=len(all_history) + 1,
            question_type=replacement_type,
            question=replacement_text,
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
        self._ensure_round_time_remaining(interview, round_record)

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

        resume = _require_resume(
            self.repository,
            interview.resume_id,
            user_id,
            snapshot=interview.resume_snapshot,
        )
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
        replacement_type = question.question_type
        replacement_text = question.question
        if _is_final_question(current_qa):
            replacement_type, replacement_text = _with_final_question_notice(
                replacement_type,
                replacement_text,
            )
        updated = self.repository.update_question_status(current_qa.id, "skipped")
        if not updated:
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message="当前问题状态已变化，请刷新后重试。",
            )
        self.repository.delete_answer_draft(user_id, interview.id, round_id, current_qa.id)

        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        next_qa = create_qa(
            interview_id=interview.id,
            round_id=round_record.id,
            sequence=len(all_history) + 1,
            question_type=replacement_type,
            question=replacement_text,
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
        resume = _require_resume(
            self.repository,
            interview.resume_id,
            user_id,
            snapshot=interview.resume_snapshot,
        )
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
        answer_evaluation = _answer_evaluation_response(
            answered_qa,
            round_record,
            question_score,
        )
        remaining_seconds = _round_remaining_seconds(
            round_record,
            interview,
            datetime.utcnow(),
        )
        if finish_after_answer or _is_final_question(answered_qa) or remaining_seconds <= 0:
            summary = self._generate_round_summary(
                interview=interview,
                round_record=round_record,
                history=history,
                resume=resume,
                is_reference_only=False,
            )
            self.repository.finish_round(interview.id, round_record.id, "completed", summary, now)
            return RoundAnswerResponse(
                action="finish_round",
                round_summary=summary,
                answer_evaluation=answer_evaluation,
            )

        agent = get_round_agent(
            round_record.round_type,
            self.llm_client,
            spec=resolve_round_spec(
                getattr(self.repository, "connection", None),
                interview.harness_bundle_id,
                round_record.round_type,
            ),
        )
        if agent.should_finish(
            round_record,
            history,
            latest_question_score=question_score,
            remaining_seconds=remaining_seconds,
            closing_window_seconds=ROUND_CLOSING_WINDOW_SECONDS,
            resume=resume.structured_data,
        ):
            if count_questions(history)["total"] >= round_record.max_total_questions:
                summary = self._generate_round_summary(
                    interview=interview,
                    round_record=round_record,
                    history=history,
                    resume=resume,
                    is_reference_only=False,
                )
                self.repository.finish_round(
                    interview.id,
                    round_record.id,
                    "completed",
                    summary,
                    now,
                )
                return RoundAnswerResponse(
                    action="finish_round",
                    round_summary=summary,
                    answer_evaluation=answer_evaluation,
                )
            create_qa = getattr(
                self.repository,
                "create_qa_idempotent",
                self.repository.create_qa,
            )
            final_qa = create_qa(
                interview_id=interview.id,
                round_id=round_record.id,
                sequence=len(history) + 1,
                question_type=FINAL_QUESTION_TYPE,
                question=_final_round_question(
                    round_record.round_type,
                    resume.structured_data,
                    history,
                ),
                question_kind="main",
            )
            self.repository.update_question_count(
                interview.id,
                len(self.repository.list_qa(interview.id)),
            )
            return RoundAnswerResponse(
                action="next_question",
                question=_round_question_response(final_qa),
                answer_evaluation=_active_round_answer_evaluation(
                    interview,
                    answer_evaluation,
                ),
            )

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
        next_question_type = question.question_type
        next_question_text = question.question
        next_question_is_last = (
            _round_remaining_seconds(round_record, interview, datetime.utcnow())
            <= ROUND_CLOSING_WINDOW_SECONDS
            or count_questions(history)["total"] + 1 >= round_record.max_total_questions
        )
        if next_question_is_last:
            next_question_type, next_question_text = _with_final_question_notice(
                next_question_type,
                next_question_text,
            )
        create_qa = getattr(self.repository, "create_qa_idempotent", self.repository.create_qa)
        next_qa = create_qa(
            interview_id=interview.id,
            round_id=round_record.id,
            sequence=len(history) + 1,
            question_type=next_question_type,
            question=next_question_text,
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
            answer_evaluation=_active_round_answer_evaluation(interview, answer_evaluation),
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
        if finish_type in {"early", "timeout"}:
            skipped_question = self.repository.get_unanswered_round_question(interview.id, round_id)
            if skipped_question is not None:
                self.repository.update_question_status(skipped_question.id, "skipped")
                self.repository.delete_answer_draft(
                    user_id,
                    interview.id,
                    round_id,
                    skipped_question.id,
                )
        history = self.repository.list_round_qa(interview.id, round_id)
        if finish_type == "normal" and not _has_answer_evidence(history):
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="正常结束轮次需要至少一条有效回答。",
            )
        resume = _require_resume(
            self.repository,
            interview.resume_id,
            user_id,
            snapshot=interview.resume_snapshot,
        )
        summary = self._generate_round_summary(
            interview=interview,
            round_record=round_record,
            history=history,
            resume=resume,
            is_reference_only=(finish_type == "early" or not _has_answer_evidence(history)),
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
            self._update_weakness_practice_progress(
                interview=interview,
                report=existing_report,
                practiced_at=datetime.utcnow(),
            )
            return _feedback_report_response(existing_report)

        self._assert_final_report_allowed(interview, rounds, finish_type)
        if self.evaluation_service is not None:
            resume = _require_resume(
                self.repository,
                interview.resume_id,
                user_id,
                snapshot=interview.resume_snapshot,
            )
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
        self._update_weakness_practice_progress(
            interview=interview,
            report=saved_report,
            practiced_at=now,
        )
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
        self._enqueue_autonomous_evolution(interview)
        connection = getattr(self.repository, "connection", None)
        if connection is not None:
            observe_completed_interview(connection, interview.id)
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
            LOGGER.exception(
                "failed to enqueue memory summary for interview %s",
                interview_id,
            )
            return

    def _enqueue_autonomous_evolution(self, interview: InterviewRecord) -> None:
        settings = get_settings()
        if not settings.evolution_enabled or not interview.job_family_key:
            return
        try:
            repository = AutonomousEvolutionRepository(self.repository.connection)
            if (
                repository.get_active_bundle(
                    interview.job_family_key,
                    user_id=interview.user_id,
                )
                is None
            ):
                repository.ensure_bootstrap_bundle(
                    interview.job_family_key,
                    bootstrap_artifacts(),
                    user_id=interview.user_id,
                )
            repository.enqueue_if_due(
                user_id=interview.user_id,
                job_family_key=interview.job_family_key,
                trigger_every=settings.evolution_trigger_interviews,
                max_retries=settings.evolution_task_max_retries,
            )
        except Exception:
            LOGGER.exception(
                "failed to enqueue autonomous evolution for interview %s",
                interview.id,
            )
            return

    def _update_weakness_practice_progress(
        self,
        *,
        interview: InterviewRecord,
        report: FeedbackReportRecord,
        practiced_at: datetime,
    ) -> None:
        get_progress = getattr(self.repository, "get_weakness_practice_progress_by_practice", None)
        update_progress = getattr(self.repository, "update_weakness_practice_progress_result", None)
        if not callable(get_progress) or not callable(update_progress):
            return
        try:
            progress = get_progress(interview.id)
            if progress is None:
                return
            update_progress(
                practice_interview_id=interview.id,
                status=classify_practice_status(progress.weakness_title, report),
                practice_score=report.score,
                last_practiced_at=practiced_at,
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
                    position_key=interview.target_position,
                    scenario=scene,
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
            record_harness_event(
                connection=getattr(self.repository, "connection", None),
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
        prompt_version = resolve_artifact_version(
            getattr(self.repository, "connection", None),
            interview.harness_bundle_id,
            f"interviewer.{round_record.round_type}",
            f"interviewer-{round_record.round_type}-v1",
        )
        agent = get_round_agent(
            round_record.round_type,
            self.llm_client,
            spec=resolve_round_spec(
                getattr(self.repository, "connection", None),
                interview.harness_bundle_id,
                round_record.round_type,
            ),
        )
        fallback_error: AppError | None = None
        remaining_seconds = _round_remaining_seconds(
            round_record,
            interview,
            datetime.utcnow(),
        )
        strategy_payload = interview_strategy_payload(
            interview,
            round_record,
            remaining_seconds=remaining_seconds,
            closing_window_seconds=ROUND_CLOSING_WINDOW_SECONDS,
        )
        resume_payload = {
            **resume_data,
            "_job_description": interview.job_description or "",
            "_interview_strategy": strategy_payload,
        }
        if self.short_term_memory_service is not None:
            short_memory_context, qa_history_payload, _ = (
                self.short_term_memory_service.prompt_context(
                    user_id=user_id,
                    interview=interview,
                    round_record=round_record,
                    qa_history=qa_history_payload,
                )
            )
            resume_payload["_short_term_memory"] = short_memory_context
        skill_bundle = self._run_skill_layer(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            payload=payload,
            qa_history_payload=qa_history_payload,
            resume_data=resume_data,
            previous_answer=previous_answer,
            effective_memories=effective_memories,
            question_kind=question_kind,
            interview_strategy=strategy_payload,
        )
        resume_payload["_skill_context"] = skill_bundle.agent_context()

        def generate_or_fallback() -> Any:
            nonlocal fallback_error
            try:
                return agent.generate_question(
                    resume=resume_payload,
                    target_position=interview.target_position,
                    qa_history=qa_history_payload,
                    previous_answer=previous_answer,
                    effective_memories=effective_memories,
                    question_kind=question_kind,
                )
            except AppError as exc:
                if exc.code not in {
                    ErrorCode.BUSINESS_ERROR,
                    ErrorCode.NETWORK_TIMEOUT,
                }:
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
            payload={
                **payload,
                "prompt_version": prompt_version,
                "interview_strategy": strategy_payload,
                "skill_trace_id": skill_bundle.trace_id,
                "skill_call_count": len(skill_bundle.calls),
                "selected_skills": [item.name for item in skill_bundle.selected],
            },
            prompt_version=prompt_version,
            operation=generate_or_fallback,
        )
        if fallback_error is not None:
            fallback = agent.fallback_question(qa_history_payload, question_kind)
            self._update_interview_harness(
                interview.id,
                harness_status="degraded",
                last_harness_error=safe_error_code(fallback_error),
                had_degradation=True,
            )
            self._update_round_execution(round_record.id, execution_status="degraded")
            record_harness_event(
                connection=getattr(self.repository, "connection", None),
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

    def _run_skill_layer(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        payload: dict[str, Any],
        qa_history_payload: list[dict[str, Any]],
        resume_data: dict[str, Any],
        previous_answer: str | None,
        effective_memories: list[dict[str, Any]],
        question_kind: str,
        interview_strategy: dict[str, Any],
    ) -> SkillRunBundle:
        stage: SkillStage = "post_answer" if previous_answer else "pre_question"
        context = SkillContext(
            user_id=user_id,
            interview_id=interview.id,
            round_id=round_record.id,
            round_type=round_record.round_type,
            stage=stage,
            target_position=interview.target_position,
            job_description=interview.job_description or "",
            resume=resume_data,
            qa_history=qa_history_payload,
            previous_answer=previous_answer,
            question_kind=question_kind,
            effective_memories=effective_memories,
            interview_strategy=interview_strategy,
        )
        try:
            bundle = DEFAULT_SKILL_RUNNER.run(context=context, llm_client=self.llm_client)
        except Exception as exc:
            trace_id = uuid.uuid4().hex
            record_harness_event(
                connection=getattr(self.repository, "connection", None),
                user_id=user_id,
                interview_id=interview.id,
                round_id=round_record.id,
                node_type="skill_runner",
                event_type="degraded",
                payload={
                    "trace_id": trace_id,
                    "reason": "skill_runner_failed",
                    "error": safe_error_code(exc),
                },
            )
            return SkillRunBundle(trace_id=trace_id, selected=[], calls=[])
        self._record_skill_call_traces(
            user_id=user_id,
            interview=interview,
            round_record=round_record,
            question_id=_skill_question_id(payload),
            bundle=bundle,
        )
        if bundle.calls:
            record_harness_event(
                connection=getattr(self.repository, "connection", None),
                user_id=user_id,
                interview_id=interview.id,
                round_id=round_record.id,
                node_type="skill_runner",
                event_type="skill_calls_completed",
                payload={
                    "trace_id": bundle.trace_id,
                    "stage": stage,
                    "skill_names": [call.skill_name for call in bundle.calls],
                    "failed_count": sum(1 for call in bundle.calls if call.error_message),
                },
            )
        return bundle

    def _record_skill_call_traces(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        question_id: int | None,
        bundle: SkillRunBundle,
    ) -> None:
        create_trace = getattr(self.repository, "create_skill_call_trace", None)
        if not callable(create_trace):
            return
        for call in bundle.calls:
            try:
                create_trace(
                    user_id=user_id,
                    interview_id=interview.id,
                    round_id=round_record.id,
                    question_id=question_id,
                    trace_id=call.trace_id,
                    round_type=call.round_type,
                    stage=call.stage,
                    skill_name=call.skill_name,
                    selection_source=call.selection_source,
                    selection_reason=call.selection_reason,
                    input_summary=call.input_summary,
                    output_summary=call.output_summary,
                    structured_signals=call.structured_signals,
                    confidence=call.confidence,
                    llm_enhanced=call.llm_enhanced,
                    elapsed_ms=call.elapsed_ms,
                    error_message=call.error_message,
                )
            except Exception:
                continue

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
            agent = get_round_agent(
                round_record.round_type,
                self.llm_client,
                spec=resolve_round_spec(
                    getattr(self.repository, "connection", None),
                    interview.harness_bundle_id,
                    round_record.round_type,
                ),
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
                    payload={
                        "history_count": len(history),
                        "is_reference_only": is_reference_only,
                    },
                    prompt_version=resolve_artifact_version(
                        getattr(self.repository, "connection", None),
                        interview.harness_bundle_id,
                        f"interviewer.{round_record.round_type}",
                        f"interviewer-{round_record.round_type}-v1",
                    ),
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
        prompt_version: str | None = None,
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
                prompt_version=prompt_version,
                operation=operation,
            )
        except AppError as exc:
            self._update_interview_harness(
                interview.id,
                harness_status="pending",
                last_harness_error=safe_error_code(exc),
            )
            if round_record is not None:
                self._update_round_execution(round_record.id, execution_status="failed")
            raise
        except Exception as exc:
            self._update_interview_harness(
                interview.id,
                harness_status="failed",
                last_harness_error=safe_error_code(exc),
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
                last_harness_error=safe_error_code(exc),
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

    def _ensure_round_time_remaining(
        self,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
    ) -> None:
        if _round_remaining_seconds(round_record, interview, datetime.utcnow()) <= 0:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_409_CONFLICT,
                message="本轮面试已达到限时，请提交当前回答或结束本轮。",
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
    prompt_version: str | None = None,
    operation: Callable[[], Any],
) -> Any:
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
        prompt_version=prompt_version,
    )
    try:
        trace_id = repository.create_trace(request)
    except Exception:
        return operation()
    if connection is not None:
        connection.commit()
    policy = resolve_interview_harness_policy(connection, interview_id)
    max_retries = min(3, max(0, int(policy.get("max_retries") or 0)))
    retry_records: list[dict[str, Any]] = []
    result: Any = None
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            result = operation()
            validate_runtime_output(_snapshot_value(result))
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt <= max_retries:
                retry_records.append(
                    {
                        "attempt": attempt,
                        "error": safe_error_code(exc),
                    }
                )
    if last_error is not None:
        try:
            repository.update_trace_status(
                trace_id,
                status="failed",
                validation_status="failed",
                error_code="BUSINESS_EXECUTION_FAILED",
                error_detail=safe_error_code(last_error),
                retry_records=retry_records,
            )
            _save_fallback_rule_evaluations(
                repository=repository,
                request=request,
                trace_id=trace_id,
                validation_status="failed",
                error_detail=safe_error_code(last_error),
            )
        except Exception:
            pass
        if connection is not None:
            record_runtime_execution(
                connection,
                interview_id,
                succeeded=False,
                hard_error=is_hard_runtime_error(last_error),
            )
        raise last_error
    try:
        repository.update_trace_status(
            trace_id,
            status="completed",
            validation_status="passed",
            output_snapshot={"result": _snapshot_value(result)},
            retry_records=retry_records,
        )
        _save_fallback_rule_evaluations(
            repository=repository,
            request=request,
            trace_id=trace_id,
            validation_status="passed",
        )
    except Exception:
        pass
    if connection is not None:
        record_runtime_execution(connection, interview_id, succeeded=True)
    return result


def _save_harness_checkpoint(
    *,
    connection: Any | None = None,
    user_id: int,
    interview_id: int,
    round_id: int | None,
    node_type: str,
    snapshot: dict[str, Any],
) -> int | None:
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


def _skill_question_id(payload: dict[str, Any]) -> int | None:
    for key in (
        "answered_question_id",
        "regenerated_question_id",
        "skipped_question_id",
    ):
        value = payload.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _require_multi_round(interview: InterviewRecord) -> None:
    if interview.mode != "multi_round":
        raise _status_error()


def _status_error() -> AppError:
    return AppError(
        ErrorCode.BUSINESS_ERROR,
        status.HTTP_400_BAD_REQUEST,
        message="面试状态不允许当前操作。",
    )
