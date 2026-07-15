from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from app.agents.final_evaluation import FinalEvaluationAgent
from app.agents.question_evaluation import QuestionEvaluationAgent
from app.agents.round_evaluation import RoundEvaluationAgent
from app.autonomous_evolution.observation import (
    is_hard_runtime_error,
    record_runtime_execution,
    validate_runtime_output,
)
from app.autonomous_evolution.runtime import (
    resolve_artifact_version,
    resolve_interview_harness_policy,
    resolve_prompt,
    resolve_round_spec,
)
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
from app.prompts.loader import load_prompt
from app.repositories.evaluations import EvaluationRecord
from app.repositories.interviews import (
    InterviewRecord,
    InterviewRoundRecord,
    QARecord,
    ResumeRecord,
)
from app.schemas.evaluation import (
    DimensionScore,
    FinalActionPlan,
    FinalEvaluationInput,
    FinalEvaluationOutput,
    FinalProblemDiagnosis,
    FinalRoundReview,
    FinalRoundScore,
    QuestionEvaluationInput,
    QuestionEvaluationOutput,
    RoundEvaluationInput,
    RoundEvaluationOutput,
)
from app.services.interview_strategy import (
    interview_strategy_payload,
)
from app.services.interview_strategy import (
    recommendation_for_score as _recommendation,
)
from app.services.interview_strategy import (
    round_label as _round_label,
)
from app.services.llm import LLMClient

QUESTION_EVALUATION_TYPE = "question"
ROUND_EVALUATION_TYPE = "round"
FINAL_EVALUATION_TYPE = "final"

QUESTION_PROMPT_VERSION = "question-light-v1"
ROUND_PROMPT_VERSIONS = {
    "resume": "round-resume-v1",
    "technical": "round-technical-v1",
    "manager": "round-manager-v1",
    "hr": "round-hr-v1",
}
FINAL_PROMPT_VERSION = "final-v1"
EARLY_FINISH_COEFFICIENT = 0.6
QUESTION_QUALITY_WEIGHTS = {
    "正确性": 0.35,
    "相关性": 0.25,
    "完整性": 0.20,
    "逻辑性": 0.10,
    "深度": 0.10,
}
QUESTION_QUALITY_ALIASES = {
    "准确性": "正确性",
    "事实正确性": "正确性",
    "关联性": "相关性",
    "问题相关性": "相关性",
    "回答相关性": "相关性",
    "覆盖完整性": "完整性",
    "结构逻辑": "逻辑性",
    "逻辑清晰度": "逻辑性",
    "技术深度": "深度",
    "分析深度": "深度",
}
UNKNOWN_ONLY_SCORE = 10
OFF_TOPIC_SCORE = 20
UNKNOWN_ANSWER_MARKERS = (
    "不知道",
    "不会",
    "不清楚",
    "不了解",
    "没想过",
    "没有思路",
    "答不上来",
)
UNKNOWN_FILLER_TOKENS = (
    "我",
    "这个",
    "这题",
    "问题",
    "真的",
    "暂时",
    "目前",
    "也",
    "还",
    "太",
    "了",
    "的",
    "啊",
    "呢",
    "。",
    "，",
    ",",
    ".",
    " ",
)
OFF_TOPIC_MARKERS = (
    "天气",
    "旅游",
    "打篮球",
    "篮球",
    "吃饭",
    "电影",
    "唱歌",
    "游戏",
    "睡觉",
)


class EvaluationRepositoryProtocol(Protocol):
    def get_by_key(self, evaluation_type: str, evaluation_key: str) -> EvaluationRecord | None:
        ...

    def list_by_interview(
        self,
        interview_id: int,
        evaluation_type: str | None = None,
        round_id: int | None = None,
    ) -> list[EvaluationRecord]:
        ...

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
        ...

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
        ...


class EvaluationSchedulerService:
    def __init__(self, repository: EvaluationRepositoryProtocol, llm_client: LLMClient) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.question_agent = QuestionEvaluationAgent(llm_client)
        self.round_agent = RoundEvaluationAgent(llm_client)
        self.final_agent = FinalEvaluationAgent(llm_client)

    def score_question(
        self,
        *,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa: QARecord,
        resume: ResumeRecord,
    ) -> QuestionEvaluationOutput | None:
        if qa.round_id is None:
            return None
        key = question_evaluation_key(interview.id, round_record.id, qa.id)
        existing = self.repository.get_by_key(QUESTION_EVALUATION_TYPE, key)
        if existing is not None and existing.status == "succeeded" and existing.result:
            existing_result = _validate_existing(existing.result, QuestionEvaluationOutput)
            if existing_result is not None:
                return _enforce_question_score(
                    existing_result,
                    qa.answer,
                    qa.question,
                    self._round_spec(interview, round_record.round_type).dimensions,
                )

        prompt_version = self._artifact_version(
            interview,
            "evaluation.question",
            QUESTION_PROMPT_VERSION,
        )
        try:
            result = _enforce_question_score(
                self._execute_harness_call(
                    user_id=interview.user_id,
                    interview_id=interview.id,
                    round_id=round_record.id,
                    node_type="question_evaluator",
                    agent_type=round_record.agent_type,
                    purpose="score_question",
                    payload={"question_id": qa.id, "prompt_version": prompt_version},
                    operation=lambda: self._generate_question_score(
                        interview,
                        round_record,
                        qa,
                        resume,
                    ),
                ),
                qa.answer,
                qa.question,
                self._round_spec(interview, round_record.round_type).dimensions,
            )
        except Exception as exc:
            self.repository.save_failure(
                evaluation_type=QUESTION_EVALUATION_TYPE,
                evaluation_key=key,
                interview_id=interview.id,
                round_id=round_record.id,
                question_id=qa.id,
                error_message=str(exc) or exc.__class__.__name__,
                prompt_version=prompt_version,
                model_name=_model_name(self.llm_client),
            )
            return None

        self.repository.save_success(
            evaluation_type=QUESTION_EVALUATION_TYPE,
            evaluation_key=key,
            interview_id=interview.id,
            round_id=round_record.id,
            question_id=qa.id,
            dimension_scores=[item.model_dump() for item in result.dimension_scores],
            total_score=result.total_score,
            evidence=result.evidence,
            result=result.model_dump(),
            prompt_version=prompt_version,
            model_name=_model_name(self.llm_client),
        )
        return result

    def fill_missing_question_scores(
        self,
        *,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa_history: list[QARecord],
        resume: ResumeRecord,
    ) -> list[dict[str, Any]]:
        for qa in qa_history:
            self.score_question(
                interview=interview,
                round_record=round_record,
                qa=qa,
                resume=resume,
            )
        return self.question_scores_for_round(interview.id, round_record.id)

    def question_scores_for_round(self, interview_id: int, round_id: int) -> list[dict[str, Any]]:
        records = self.repository.list_by_interview(
            interview_id,
            evaluation_type=QUESTION_EVALUATION_TYPE,
            round_id=round_id,
        )
        return [
            _question_score_payload(record)
            for record in records
            if record.status == "succeeded"
        ]

    def question_scores_by_id(self, interview_id: int) -> dict[int, dict[str, Any]]:
        records = self.repository.list_by_interview(
            interview_id,
            evaluation_type=QUESTION_EVALUATION_TYPE,
        )
        return {
            int(record.question_id): _question_score_payload(record)
            for record in records
            if record.status == "succeeded" and record.question_id is not None
        }

    def generate_round_summary(
        self,
        *,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa_history: list[QARecord],
        question_scores: list[dict[str, Any]],
        is_reference_only: bool,
    ) -> dict[str, Any]:
        key = round_evaluation_key(interview.id, round_record.id)
        existing = self.repository.get_by_key(ROUND_EVALUATION_TYPE, key)
        if existing is not None and existing.status == "succeeded" and existing.result:
            return _round_summary_payload(existing.result, question_scores)

        prompt_version = self._artifact_version(
            interview,
            f"evaluation.round.{round_record.round_type}",
            ROUND_PROMPT_VERSIONS[round_record.round_type],
        )
        try:
            result = self._execute_harness_call(
                user_id=interview.user_id,
                interview_id=interview.id,
                round_id=round_record.id,
                node_type="round_evaluator",
                agent_type=round_record.agent_type,
                purpose="generate_round_summary",
                payload={
                    "qa_count": len(qa_history),
                    "question_score_count": len(question_scores),
                    "prompt_version": prompt_version,
                },
                operation=lambda: self._generate_round_summary(
                    interview=interview,
                    round_record=round_record,
                    qa_history=qa_history,
                    question_scores=question_scores,
                    is_reference_only=is_reference_only,
                ),
            )
        except Exception as exc:
            self.repository.save_failure(
                evaluation_type=ROUND_EVALUATION_TYPE,
                evaluation_key=key,
                interview_id=interview.id,
                round_id=round_record.id,
                question_id=None,
                error_message=str(exc) or exc.__class__.__name__,
                prompt_version=prompt_version,
                model_name=_model_name(self.llm_client),
            )
            result = _fallback_round_result(
                self._round_spec(interview, round_record.round_type).dimensions,
                qa_history,
                question_scores,
                is_reference_only,
                round_record.min_main_questions,
            )

        self.repository.save_success(
            evaluation_type=ROUND_EVALUATION_TYPE,
            evaluation_key=key,
            interview_id=interview.id,
            round_id=round_record.id,
            question_id=None,
            dimension_scores=[item.model_dump() for item in result.dimension_scores],
            total_score=result.total_score,
            evidence=result.evidence,
            result=result.model_dump(),
            prompt_version=prompt_version,
            model_name=_model_name(self.llm_client),
        )
        return _round_summary_payload(result.model_dump(), question_scores)

    def generate_final_report(
        self,
        *,
        interview: InterviewRecord,
        resume: ResumeRecord,
        rounds: list[InterviewRoundRecord],
        effective_history_memory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        key = final_evaluation_key(interview.id)
        if effective_history_memory:
            record_harness_event(
                connection=getattr(self.repository, "connection", None),
                user_id=interview.user_id,
                interview_id=interview.id,
                round_id=None,
                node_type="final_evaluator",
                event_type="scoring_memory_ignored",
                payload={
                    "rule": "scoring_memory_isolation",
                    "memory_count": len(effective_history_memory),
                },
            )
        existing = self.repository.get_by_key(FINAL_EVALUATION_TYPE, key)
        if existing is not None and existing.status == "succeeded" and existing.result:
            return _final_report_payload(interview.id, existing.result)

        round_payloads = [_round_record_payload(round_record) for round_record in rounds]
        has_incomplete = any(
            round_record.status not in {"completed", "skipped"} for round_record in rounds
        )
        has_reference = any(round_record.is_reference_only for round_record in rounds)
        prompt_version = self._artifact_version(
            interview,
            "evaluation.final",
            FINAL_PROMPT_VERSION,
        )
        try:
            result = self._execute_harness_call(
                user_id=interview.user_id,
                interview_id=interview.id,
                round_id=None,
                node_type="final_evaluator",
                agent_type="final_evaluation",
                purpose="generate_final_report",
                payload={
                    "round_count": len(round_payloads),
                    "prompt_version": prompt_version,
                },
                operation=lambda: self._generate_final_report(
                    interview=interview,
                    resume=resume,
                    round_payloads=round_payloads,
                    has_incomplete_rounds=has_incomplete,
                    has_reference_only_rounds=has_reference,
                ),
            )
        except Exception as exc:
            self.repository.save_failure(
                evaluation_type=FINAL_EVALUATION_TYPE,
                evaluation_key=key,
                interview_id=interview.id,
                round_id=None,
                question_id=None,
                error_message=str(exc) or exc.__class__.__name__,
                prompt_version=prompt_version,
                model_name=_model_name(self.llm_client),
            )
            result = _fallback_final_result(
                round_payloads,
                has_incomplete_rounds=has_incomplete,
                has_reference_only_rounds=has_reference,
                selected_round_types=interview.selected_rounds,
            )

        self.repository.save_success(
            evaluation_type=FINAL_EVALUATION_TYPE,
            evaluation_key=key,
            interview_id=interview.id,
            round_id=None,
            question_id=None,
            dimension_scores=[],
            total_score=result.total_score,
            evidence=[],
            result=result.model_dump(),
            prompt_version=prompt_version,
            model_name=_model_name(self.llm_client),
        )
        return _final_report_payload(interview.id, result.model_dump())

    def _generate_question_score(
        self,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa: QARecord,
        resume: ResumeRecord,
    ) -> QuestionEvaluationOutput:
        spec = self._round_spec(interview, round_record.round_type)
        evaluation_input = QuestionEvaluationInput(
            interview_id=interview.id,
            round_id=round_record.id,
            question_id=qa.id,
            round_type=round_record.round_type,
            dimensions=spec.dimensions,
            resume=resume.structured_data,
            target_position=interview.target_position,
            job_description=interview.job_description,
            interview_strategy=interview_strategy_payload(interview),
            question=qa.question,
            answer=qa.answer or "",
        )
        payload = evaluation_input.model_dump()
        _ensure_scoring_memory_isolated(payload)
        invalid_result = _invalid_question_result_if_needed(
            answer=qa.answer,
            question=qa.question,
            dimensions=spec.dimensions,
        )
        if invalid_result is not None:
            return invalid_result
        return self.question_agent.evaluate(
            payload,
            system_prompt=self._effective_prompt(
                interview,
                QuestionEvaluationAgent.prompt_file,
                aliases={"question_evaluation", "question_scoring"},
            ),
        )

    def _generate_round_summary(
        self,
        *,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa_history: list[QARecord],
        question_scores: list[dict[str, Any]],
        is_reference_only: bool,
    ) -> RoundEvaluationOutput:
        spec = self._round_spec(interview, round_record.round_type)
        evaluation_input = RoundEvaluationInput(
            interview_id=interview.id,
            round_id=round_record.id,
            round_type=round_record.round_type,
            dimensions=spec.dimensions,
            qa_history=_qa_payloads(qa_history),
            question_evaluations=question_scores,
            interview_strategy=interview_strategy_payload(interview),
            is_reference_only=is_reference_only,
        )
        payload = evaluation_input.model_dump()
        _ensure_scoring_memory_isolated(payload)
        result = self.round_agent.evaluate(
            round_record.round_type,
            payload,
            system_prompt=self._effective_prompt(
                interview,
                RoundEvaluationAgent.prompt_file_for(round_record.round_type),
                aliases={"round_evaluation", round_record.round_type},
            ),
        )
        return _enforce_round_result(
            generated=result,
            dimensions=spec.dimensions,
            qa_history=qa_history,
            question_scores=question_scores,
            is_reference_only=is_reference_only,
            min_valid_answers=round_record.min_main_questions,
        )

    def _generate_final_report(
        self,
        *,
        interview: InterviewRecord,
        resume: ResumeRecord,
        round_payloads: list[dict[str, Any]],
        has_incomplete_rounds: bool,
        has_reference_only_rounds: bool,
    ) -> FinalEvaluationOutput:
        evaluation_input = FinalEvaluationInput(
            interview_id=interview.id,
            resume_summary=resume.structured_data,
            target_position=interview.target_position,
            job_description=interview.job_description,
            interview_strategy=interview_strategy_payload(interview),
            round_evaluations=round_payloads,
            has_incomplete_rounds=has_incomplete_rounds,
            has_reference_only_rounds=has_reference_only_rounds,
        )
        payload = evaluation_input.model_dump()
        _ensure_scoring_memory_isolated(payload)
        result = self.final_agent.evaluate(
            payload,
            system_prompt=self._effective_prompt(
                interview,
                FinalEvaluationAgent.prompt_file,
                aliases={"final_evaluation", "final_report", "final_report_reliability"},
            ),
        )
        return _enforce_final_result(
            generated=result,
            round_payloads=round_payloads,
            selected_round_types=interview.selected_rounds,
            has_incomplete_rounds=has_incomplete_rounds,
            has_reference_only_rounds=has_reference_only_rounds,
        )

    def _round_spec(self, interview: InterviewRecord, round_type: str) -> Any:
        return resolve_round_spec(
            getattr(self.repository, "connection", None),
            interview.harness_bundle_id,
            round_type,
        )

    def _artifact_version(
        self,
        interview: InterviewRecord,
        artifact_key: str,
        fallback_version: str,
    ) -> str:
        return resolve_artifact_version(
            getattr(self.repository, "connection", None),
            interview.harness_bundle_id,
            artifact_key,
            fallback_version,
        )

    def _effective_prompt(
        self,
        interview: InterviewRecord,
        prompt_file: str,
        *,
        aliases: set[str],
    ) -> str:
        fallback = load_prompt(prompt_file)
        if prompt_file == QuestionEvaluationAgent.prompt_file:
            artifact_key = "evaluation.question"
        elif prompt_file == FinalEvaluationAgent.prompt_file:
            artifact_key = "evaluation.final"
        elif prompt_file.startswith("round_evaluation_"):
            round_type = prompt_file.removeprefix("round_evaluation_").removesuffix(".md")
            artifact_key = f"evaluation.round.{round_type}"
        else:
            return fallback
        return resolve_prompt(
            getattr(self.repository, "connection", None),
            interview.harness_bundle_id,
            artifact_key,
            fallback,
        )

    def _execute_harness_call(
        self,
        *,
        user_id: int,
        interview_id: int,
        round_id: int | None,
        node_type: str,
        agent_type: str | None,
        purpose: str,
        payload: dict[str, Any],
        operation: Callable[[], Any],
    ) -> Any:
        connection = getattr(self.repository, "connection", None)
        if connection is not None:
            connection.commit()
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
            prompt_version=(
                str(payload["prompt_version"])
                if isinstance(payload.get("prompt_version"), str)
                and payload["prompt_version"]
                else None
            ),
        )
        trace_id = repository.create_trace(request)
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
                            "error": str(exc) or exc.__class__.__name__,
                        }
                    )
        if last_error is not None:
            repository.update_trace_status(
                trace_id,
                status="failed",
                validation_status="failed",
                error_code="BUSINESS_EXECUTION_FAILED",
                error_detail=str(last_error) or last_error.__class__.__name__,
                retry_records=retry_records,
            )
            _save_fallback_rule_evaluations(
                repository=repository,
                request=request,
                trace_id=trace_id,
                validation_status="failed",
                error_detail=str(last_error) or last_error.__class__.__name__,
            )
            if connection is not None:
                record_runtime_execution(
                    connection,
                    interview_id,
                    succeeded=False,
                    hard_error=is_hard_runtime_error(last_error),
                )
            raise last_error
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
        if connection is not None:
            record_runtime_execution(connection, interview_id, succeeded=True)
        return result


def question_evaluation_key(interview_id: int, round_id: int, question_id: int) -> str:
    return f"{interview_id}:{round_id}:{question_id}"


def round_evaluation_key(interview_id: int, round_id: int) -> str:
    return f"{interview_id}:{round_id}"


def final_evaluation_key(interview_id: int) -> str:
    return str(interview_id)


def _model_name(llm_client: LLMClient) -> str:
    return getattr(llm_client, "model_name", "unknown")


FORBIDDEN_SCORING_MEMORY_KEYS = {
    "memory",
    "memories",
    "long_term_memory",
    "candidate_memory",
    "candidate_memories",
    "interviewer_memory",
    "interviewer_memories",
    "agent_memory",
    "agent_memories",
    "effective_history_memory",
}


def _ensure_scoring_memory_isolated(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in FORBIDDEN_SCORING_MEMORY_KEYS:
                raise ValueError("scoring input contains long-term memory")
            _ensure_scoring_memory_isolated(value)
    elif isinstance(payload, list):
        for item in payload:
            _ensure_scoring_memory_isolated(item)


def _validate_existing(
    payload: dict[str, Any],
    schema: type[QuestionEvaluationOutput],
) -> QuestionEvaluationOutput | None:
    try:
        return schema.model_validate(payload)
    except ValidationError:
        return None


def _qa_payloads(qa_history: list[QARecord]) -> list[dict[str, Any]]:
    return [
        {
            "id": qa.id,
            "sequence": qa.sequence,
            "question_type": qa.question_type,
            "question": qa.question,
            "answer": qa.answer,
            "question_kind": qa.question_kind,
            "parent_question_id": qa.parent_question_id,
        }
        for qa in qa_history
    ]


def _question_score_payload(record: EvaluationRecord) -> dict[str, Any]:
    result = record.result or {}
    return {
        **result,
        "evaluation_id": record.id,
        "question_id": record.question_id,
        "round_id": record.round_id,
        "status": record.status,
        "prompt_version": record.prompt_version,
        "model_name": record.model_name,
    }


def _round_summary_payload(
    result: dict[str, Any],
    question_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    total_score = result.get("total_score", result.get("score", 0))
    return {
        "score": total_score,
        "result": result.get("result", "pending"),
        "dimension_reviews": result.get("dimension_scores", []),
        "strengths": result.get("strengths", []),
        "main_issues": result.get("weaknesses", []),
        "suggestions": result.get("suggestions", []),
        "evidence": result.get("evidence", []),
        "is_reference_only": bool(result.get("is_reference_only", False)),
        "reference_note": result.get("reference_note"),
        "question_evaluations": question_scores,
    }


def _round_record_payload(round_record: InterviewRoundRecord) -> dict[str, Any]:
    summary = _round_summary_for_final(round_record.summary)
    return {
        "round_id": round_record.id,
        "round_type": round_record.round_type,
        "status": round_record.status,
        "score": round_record.score,
        "result": round_record.result,
        "summary": summary,
        "is_reference_only": round_record.is_reference_only,
    }


def _round_summary_for_final(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        key: value
        for key, value in summary.items()
        if key != "question_evaluations"
    }


def _final_report_payload(interview_id: int, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "interview_id": interview_id,
        "score": result.get("total_score", result.get("score", 0)),
        "weaknesses": result.get("main_risks", []),
        "suggestions": result.get("improvement_plan", []),
        "recommendation": result.get("final_conclusion"),
        "round_scores": result.get("round_scores", []),
        "strengths": result.get("core_strengths", []),
        "reference_note": result.get("reference_note"),
        "ability_analysis": result.get("ability_analysis", []),
        "job_match": result.get("job_match"),
        "final_conclusion": result.get("final_conclusion"),
        "confidence": result.get("confidence"),
        "detailed_feedback": _detailed_feedback_payload(result),
    }


def _detailed_feedback_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "problem_diagnosis": result.get("problem_diagnosis", []),
        "round_reviews": result.get("round_reviews", []),
        "action_plan": result.get("action_plan", []),
        "follow_up_questions": result.get("follow_up_questions", []),
    }


def _fallback_round_result(
    dimensions: list[str],
    qa_history: list[QARecord],
    question_scores: list[dict[str, Any]],
    is_reference_only: bool,
    min_valid_answers: int,
) -> RoundEvaluationOutput:
    total_score, dimension_scores, valid_count = _calculate_round_scores(
        dimensions,
        qa_history,
        question_scores,
        min_valid_answers,
    )
    result = _round_result_for_score(total_score)
    has_strength_evidence = valid_count > 0 and any(
        item.get("evidence") for item in question_scores
    )
    return RoundEvaluationOutput(
        total_score=total_score,
        result=result,
        dimension_scores=dimension_scores,
        strengths=["已完成回答存在可验证的岗位相关证据。"] if has_strength_evidence else [],
        weaknesses=[] if valid_count else ["本轮没有足够有效回答，评价证据不足。"],
        suggestions=["继续补充可量化的项目细节和复盘证据。"],
        evidence=[qa.question for qa in qa_history if qa.answer][:5],
        is_reference_only=is_reference_only,
        reference_note="本轮提前结束，评价仅供参考。" if is_reference_only else None,
    )


def _fallback_final_result(
    round_payloads: list[dict[str, Any]],
    has_incomplete_rounds: bool,
    has_reference_only_rounds: bool,
    selected_round_types: list[str] | None = None,
) -> FinalEvaluationOutput:
    total_score, has_effective_round = _calculate_final_score(
        round_payloads,
        selected_round_types,
    )
    reference_note = (
        "存在未完成或提前结束轮次，最终结论置信度已降低。"
        if has_incomplete_rounds or has_reference_only_rounds
        else None
    )
    round_reviews = [_round_review_from_payload(item) for item in round_payloads]
    problem_diagnosis = _fallback_problem_diagnosis(round_payloads, has_effective_round)
    action_plan = _fallback_action_plan(problem_diagnosis, has_effective_round)
    return FinalEvaluationOutput(
        total_score=total_score,
        round_scores=[
            FinalRoundScore(
                round_type=str(item.get("round_type")),
                score=item.get("score") if isinstance(item.get("score"), int) else None,
                result=str(item.get("result")) if item.get("result") is not None else None,
                is_reference_only=bool(item.get("is_reference_only")),
                status=str(item.get("status")) if item.get("status") is not None else None,
            )
            for item in round_payloads
        ],
        ability_analysis=["已根据完成轮次的结构化总评形成综合判断。"]
        if has_effective_round
        else ["本次面试缺少有效回答证据。"],
        job_match="需要结合完成轮次表现继续验证岗位匹配度。"
        if has_effective_round
        else "本次面试缺少有效回答证据，无法确认岗位匹配。",
        core_strengths=["已完成轮次中存在可验证的岗位相关证据。"] if has_effective_round else [],
        main_risks=[_diagnosis_to_text(item) for item in problem_diagnosis],
        improvement_plan=[_action_plan_to_text(item) for item in action_plan],
        final_conclusion=_recommendation(total_score),
        confidence="low" if not has_effective_round else ("medium" if reference_note else "high"),
        reference_note=reference_note,
        problem_diagnosis=problem_diagnosis,
        round_reviews=round_reviews,
        action_plan=action_plan,
        follow_up_questions=_fallback_follow_up_questions(round_payloads),
    )


def _enforce_question_score(
    result: QuestionEvaluationOutput,
    answer: str | None,
    question: str,
    dimensions: list[str],
) -> QuestionEvaluationOutput:
    score_cap = _answer_score_cap(answer, question)
    quality_scores = _quality_score_map(result.dimension_scores)
    total_score = _weighted_question_score(result.dimension_scores)
    total_score = _apply_question_band_caps(total_score, quality_scores)
    strengths = list(result.strengths)
    issues = list(result.issues)
    evidence = list(result.evidence)
    should_follow_up = result.should_follow_up
    follow_up_direction = result.follow_up_direction
    capped_by_validity = False

    if not evidence and total_score > 15:
        total_score = 15
        strengths = []
        issues.append("当前回答缺少可用于评分的有效证据。")
        should_follow_up = True
        follow_up_direction = follow_up_direction or "要求候选人直接回答当前问题并给出具体依据。"

    if score_cap is not None and total_score > score_cap:
        total_score = score_cap
        strengths = []
        should_follow_up = True
        capped_by_validity = True
        if score_cap == 0:
            issues.append("当前题目未获得有效回答。")
            evidence = []
            follow_up_direction = follow_up_direction or "请候选人补充当前问题的直接回答。"
        elif score_cap == OFF_TOPIC_SCORE:
            issues.append("当前回答与问题要求明显不匹配，按答非所问处理。")
            evidence = evidence or ["回答内容未覆盖当前问题要求。"]
            follow_up_direction = follow_up_direction or "请候选人回到当前问题，给出直接回答。"
        else:
            issues.append("候选人明确表示不知道、不会或不清楚。")
            evidence = evidence or ["回答明确表示不知道、不会或不清楚。"]
            follow_up_direction = follow_up_direction or "确认候选人是否能补充任何相关基础认知。"

    if total_score < 60 and strengths:
        strengths = []
    if total_score < 60 and not issues:
        issues.append("回答存在关键缺失或错误，未达到基本正确标准。")
    if total_score >= 60 and not evidence:
        total_score = 59
        issues.append("评分理由缺少可验证依据，不能给及格分。")
        should_follow_up = True

    dimension_scores = _normalized_question_dimensions(
        result.dimension_scores,
        dimensions,
    )
    if capped_by_validity:
        dimension_scores = [
            item.model_copy(update={"score": min(item.score, total_score)})
            for item in dimension_scores
        ]
    if not dimension_scores:
        dimension_scores = _question_dimension_scores(
            dimensions,
            total_score,
            "缺少维度评分，按总分同步。",
        )

    return result.model_copy(
        update={
            "total_score": total_score,
            "dimension_scores": dimension_scores,
            "strengths": strengths,
            "issues": _dedupe_strings(issues),
            "evidence": evidence,
            "should_follow_up": should_follow_up,
            "follow_up_direction": follow_up_direction,
        }
    )


def _invalid_question_result_if_needed(
    *,
    answer: str | None,
    question: str,
    dimensions: list[str],
) -> QuestionEvaluationOutput | None:
    cap = _answer_score_cap(answer, question)
    if cap is None:
        return None
    if cap == 0:
        reason = "空回答或无有效内容，不能形成评分证据。"
        evidence: list[str] = []
        follow_up = "请候选人补充当前问题的直接回答。"
    elif cap == OFF_TOPIC_SCORE:
        reason = "回答与当前问题缺少有效关联，按答非所问处理。"
        evidence = ["回答内容未覆盖当前问题要求。"]
        follow_up = "请候选人回到当前问题，给出直接回答。"
    else:
        reason = "候选人仅表达不知道、不会或不清楚，没有提供有效内容。"
        evidence = ["回答明确表示不知道、不会或不清楚。"]
        follow_up = "确认候选人是否能补充任何相关基础认知。"
    return QuestionEvaluationOutput(
        total_score=cap,
        dimension_scores=_question_dimension_scores(dimensions, cap, reason),
        strengths=[],
        issues=[reason],
        evidence=evidence,
        should_follow_up=True,
        follow_up_direction=follow_up,
    )


def _answer_score_cap(answer: str | None, question: str | None = None) -> int | None:
    if answer is None or not answer.strip():
        return 0
    normalized = "".join(answer.strip().lower().split())
    if _is_unknown_only_answer(normalized):
        return UNKNOWN_ONLY_SCORE
    if question and _is_likely_off_topic(question, answer):
        return OFF_TOPIC_SCORE
    return None


def _is_unknown_only_answer(normalized_answer: str) -> bool:
    if not any(marker in normalized_answer for marker in UNKNOWN_ANSWER_MARKERS):
        return False
    remaining = normalized_answer
    for marker in UNKNOWN_ANSWER_MARKERS:
        remaining = remaining.replace(marker, "")
    for token in UNKNOWN_FILLER_TOKENS:
        remaining = remaining.replace(token, "")
    return len(remaining) <= 2


def _is_likely_off_topic(question: str, answer: str) -> bool:
    question_terms = _significant_terms(question)
    answer_terms = _significant_terms(answer)
    if not question_terms or not answer_terms:
        return False
    overlap = question_terms & answer_terms
    overlap_ratio = len(overlap) / max(1, min(len(question_terms), len(answer_terms)))
    if overlap_ratio >= 0.15:
        return False
    normalized_answer = "".join(answer.lower().split())
    return any(marker in normalized_answer for marker in OFF_TOPIC_MARKERS)


def _significant_terms(text: str) -> set[str]:
    normalized = "".join(
        ch.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff" else " "
        for ch in text
    )
    ascii_terms = {item for item in normalized.split() if len(item) >= 3}
    compact = "".join(ch for ch in normalized if "\u4e00" <= ch <= "\u9fff")
    chinese_terms = {compact[index : index + 2] for index in range(max(0, len(compact) - 1))}
    return ascii_terms | chinese_terms


def _weighted_question_score(dimension_scores: list[DimensionScore]) -> int:
    quality_scores = _quality_score_map(dimension_scores)
    if quality_scores:
        weight_total = sum(QUESTION_QUALITY_WEIGHTS[name] for name in quality_scores)
        weighted = sum(
            quality_scores[name] * QUESTION_QUALITY_WEIGHTS[name] for name in quality_scores
        )
        return int(round(weighted / weight_total)) if weight_total else 0
    if not dimension_scores:
        return 0
    return int(round(sum(item.score for item in dimension_scores) / len(dimension_scores)))


def _quality_score_map(dimension_scores: list[DimensionScore]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for item in dimension_scores:
        dimension = QUESTION_QUALITY_ALIASES.get(item.dimension, item.dimension)
        if dimension in QUESTION_QUALITY_WEIGHTS:
            scores[dimension] = max(0, min(100, item.score))
    return scores


def _apply_question_band_caps(total_score: int, quality_scores: dict[str, int]) -> int:
    if not quality_scores:
        return max(0, min(100, total_score))
    score = max(0, min(100, total_score))
    correctness = quality_scores.get("正确性")
    relevance = quality_scores.get("相关性")
    completeness = quality_scores.get("完整性")
    logic = quality_scores.get("逻辑性")
    depth = quality_scores.get("深度")
    if relevance is not None and relevance <= 25:
        score = min(score, 25)
    if correctness is not None and correctness < 30:
        score = min(score, 29)
    if (
        (correctness is not None and correctness < 60)
        or (completeness is not None and completeness < 60)
    ):
        score = min(score, 59)
    core_scores = [
        value
        for value in (correctness, relevance, completeness, logic)
        if value is not None
    ]
    if score >= 75 and core_scores and min(core_scores) < 75:
        score = min(score, 74)
    if score >= 90 and (
        depth is None
        or depth < 85
        or any(value is not None and value < 85 for value in (correctness, relevance, completeness))
    ):
        score = min(score, 89)
    return score


def _normalized_question_dimensions(
    dimension_scores: list[DimensionScore],
    round_dimensions: list[str],
) -> list[DimensionScore]:
    seen: set[str] = set()
    result: list[DimensionScore] = []
    for item in dimension_scores:
        dimension = QUESTION_QUALITY_ALIASES.get(item.dimension, item.dimension)
        normalized = item.model_copy(update={"dimension": dimension})
        if normalized.dimension not in seen:
            result.append(normalized)
            seen.add(normalized.dimension)
    for dimension in QUESTION_QUALITY_WEIGHTS:
        if dimension not in seen:
            result.append(
                DimensionScore(
                    dimension=dimension,
                    score=0,
                    reason="模型未提供该标准质量维度，按 0 分计入本地加权。",
                )
            )
            seen.add(dimension)
    for dimension in round_dimensions:
        if dimension not in seen:
            result.append(
                DimensionScore(
                    dimension=dimension,
                    score=_weighted_question_score(dimension_scores),
                    reason="该轮能力维度未单独评分，按本题本地加权总分折算。",
                )
            )
            seen.add(dimension)
    return result


def _question_dimension_scores(
    round_dimensions: list[str],
    score: int,
    reason: str,
) -> list[DimensionScore]:
    dimensions = [*QUESTION_QUALITY_WEIGHTS.keys()]
    for dimension in round_dimensions:
        if dimension not in dimensions:
            dimensions.append(dimension)
    return [
        DimensionScore(dimension=dimension, score=score, reason=reason)
        for dimension in dimensions
    ]


def _enforce_round_result(
    *,
    generated: RoundEvaluationOutput,
    dimensions: list[str],
    qa_history: list[QARecord],
    question_scores: list[dict[str, Any]],
    is_reference_only: bool,
    min_valid_answers: int,
) -> RoundEvaluationOutput:
    total_score, dimension_scores, valid_count = _calculate_round_scores(
        dimensions,
        qa_history,
        question_scores,
        min_valid_answers,
    )
    evidence = list(generated.evidence)
    strengths = list(generated.strengths) if valid_count > 0 and evidence else []
    reference_note = generated.reference_note
    if is_reference_only:
        reference_note = reference_note or "本轮提前结束，评价仅供参考。"
    return generated.model_copy(
        update={
            "total_score": total_score,
            "result": _round_result_for_score(total_score),
            "dimension_scores": dimension_scores,
            "strengths": strengths,
            "evidence": evidence if valid_count > 0 else [],
            "is_reference_only": is_reference_only or generated.is_reference_only,
            "reference_note": reference_note,
        }
    )


def _calculate_round_scores(
    dimensions: list[str],
    qa_history: list[QARecord],
    question_scores: list[dict[str, Any]],
    min_valid_answers: int,
) -> tuple[int, list[DimensionScore], int]:
    total_questions = len(qa_history)
    if total_questions == 0:
        return 0, _zero_dimension_scores(dimensions, "本轮没有产生问答记录。"), 0

    score_by_question_id = {
        int(item["question_id"]): item
        for item in question_scores
        if isinstance(item.get("question_id"), int)
    }
    question_totals = [
        _question_total_score(qa, score_by_question_id.get(qa.id)) for qa in qa_history
    ]
    if all(not (qa.answer and qa.answer.strip()) for qa in qa_history):
        return 0, _zero_dimension_scores(dimensions, "本轮全部题目未回答。"), 0

    valid_count = sum(1 for score in question_totals if score >= 30)
    invalid_count = total_questions - valid_count
    dimension_scores = [
        DimensionScore(
            dimension=dimension,
            score=_dimension_average(dimension, qa_history, score_by_question_id),
            reason="由该维度下全部单题评分汇总，未回答或无该维度证据的题目按 0 分计入。",
        )
        for dimension in dimensions
    ]
    total_score = (
        int(round(sum(item.score for item in dimension_scores) / len(dimension_scores)))
        if dimension_scores
        else int(round(sum(question_totals) / total_questions))
    )
    if invalid_count > total_questions / 2:
        total_score = min(total_score, 40)
    if valid_count < min_valid_answers:
        total_score = min(total_score, 59)
    if valid_count == 0:
        total_score = 0
    return total_score, dimension_scores, valid_count


def _question_total_score(qa: QARecord, score_payload: dict[str, Any] | None) -> int:
    if _answer_score_cap(qa.answer, qa.question) == 0:
        return 0
    if score_payload is None or not isinstance(score_payload.get("total_score"), int):
        return 0
    score = int(score_payload["total_score"])
    cap = _answer_score_cap(qa.answer, qa.question)
    if cap is not None:
        score = min(score, cap)
    return max(0, min(100, score))


def _dimension_average(
    dimension: str,
    qa_history: list[QARecord],
    score_by_question_id: dict[int, dict[str, Any]],
) -> int:
    scores: list[int] = []
    for qa in qa_history:
        question_score = _question_total_score(qa, score_by_question_id.get(qa.id))
        if question_score == 0:
            scores.append(0)
            continue
        score_payload = score_by_question_id.get(qa.id) or {}
        if "dimension_scores" not in score_payload:
            scores.append(question_score)
            continue
        dimension_scores = score_payload.get("dimension_scores")
        score = 0
        if isinstance(dimension_scores, list):
            for item in dimension_scores:
                if (
                    isinstance(item, dict)
                    and item.get("dimension") == dimension
                    and isinstance(item.get("score"), int)
                ):
                    score = min(int(item["score"]), question_score)
                    break
        scores.append(score)
    return int(round(sum(scores) / len(scores))) if scores else 0


def _zero_dimension_scores(dimensions: list[str], reason: str) -> list[DimensionScore]:
    return [
        DimensionScore(dimension=dimension, score=0, reason=reason)
        for dimension in dimensions
    ]


def _round_result_for_score(score: int) -> Literal["passed", "pending", "failed"]:
    if score >= 70:
        return "passed"
    if score >= 60:
        return "pending"
    return "failed"


def _enforce_final_result(
    *,
    generated: FinalEvaluationOutput,
    round_payloads: list[dict[str, Any]],
    selected_round_types: list[str] | None,
    has_incomplete_rounds: bool,
    has_reference_only_rounds: bool,
) -> FinalEvaluationOutput:
    total_score, has_effective_round = _calculate_final_score(round_payloads, selected_round_types)
    round_scores = [_final_round_score(item) for item in round_payloads]
    round_reviews = _merge_round_reviews(generated.round_reviews, round_payloads)
    problem_diagnosis = _merge_problem_diagnosis(
        generated.problem_diagnosis,
        round_payloads,
        has_effective_round,
    )
    action_plan = _merge_action_plan(generated.action_plan, problem_diagnosis, has_effective_round)
    follow_up_questions = _merge_follow_up_questions(generated.follow_up_questions, round_payloads)
    reference_note = generated.reference_note
    if has_incomplete_rounds or has_reference_only_rounds:
        reference_note = reference_note or "存在未完成或提前结束轮次，最终结论置信度已降低。"
    confidence = generated.confidence
    if not has_effective_round:
        confidence = "low"
    elif (has_incomplete_rounds or has_reference_only_rounds) and confidence == "high":
        confidence = "medium"
    return generated.model_copy(
        update={
            "total_score": total_score,
            "round_scores": round_scores,
            "ability_analysis": _enriched_ability_analysis(
                generated.ability_analysis,
                round_reviews,
                has_effective_round,
            ),
            "core_strengths": list(generated.core_strengths)
            if has_effective_round and total_score >= 60
            else [],
            "main_risks": [*_dedupe_strings(generated.main_risks), *[
                _diagnosis_to_text(item) for item in problem_diagnosis
            ]][:6],
            "improvement_plan": [*_dedupe_strings(generated.improvement_plan), *[
                _action_plan_to_text(item) for item in action_plan
            ]][:6],
            "final_conclusion": _recommendation(total_score),
            "confidence": confidence,
            "reference_note": reference_note,
            "problem_diagnosis": problem_diagnosis,
            "round_reviews": round_reviews,
            "action_plan": action_plan,
            "follow_up_questions": follow_up_questions,
        }
    )


def _merge_round_reviews(
    generated_reviews: list[FinalRoundReview],
    round_payloads: list[dict[str, Any]],
) -> list[FinalRoundReview]:
    generated_by_type = {item.round_type: item for item in generated_reviews}
    reviews: list[FinalRoundReview] = []
    for item in round_payloads:
        round_type = str(item.get("round_type"))
        fallback = _round_review_from_payload(item)
        generated = generated_by_type.get(round_type)
        if generated is None:
            reviews.append(fallback)
            continue
        reviews.append(
            generated.model_copy(
                update={
                    "score": fallback.score,
                    "result": fallback.result,
                    "status": fallback.status,
                    "strengths": _dedupe_strings([*generated.strengths, *fallback.strengths])[:4],
                    "issues": _dedupe_strings([*generated.issues, *fallback.issues])[:5],
                    "evidence": _dedupe_strings([*generated.evidence, *fallback.evidence])[:5],
                    "suggestions": _dedupe_strings(
                        [*generated.suggestions, *fallback.suggestions]
                    )[:4],
                    "is_reference_only": fallback.is_reference_only or generated.is_reference_only,
                }
            )
        )
    return reviews


def _round_review_from_payload(item: dict[str, Any]) -> FinalRoundReview:
    summary = _summary_payload(item)
    return FinalRoundReview(
        round_type=str(item.get("round_type")),
        score=_round_score(item) if item.get("status") in {"completed", "finished_early"} else None,
        result=(
            str(item.get("result") or summary.get("result"))
            if item.get("result") or summary.get("result")
            else None
        ),
        status=str(item.get("status")) if item.get("status") is not None else None,
        strengths=_string_list(summary.get("strengths")),
        issues=_string_list(summary.get("main_issues") or summary.get("weaknesses")),
        evidence=_string_list(summary.get("evidence")),
        suggestions=_string_list(summary.get("suggestions")),
        is_reference_only=bool(item.get("is_reference_only") or summary.get("is_reference_only")),
    )


def _merge_problem_diagnosis(
    generated_items: list[FinalProblemDiagnosis],
    round_payloads: list[dict[str, Any]],
    has_effective_round: bool,
) -> list[FinalProblemDiagnosis]:
    fallback_items = _fallback_problem_diagnosis(round_payloads, has_effective_round)
    merged = [*generated_items, *fallback_items]
    result: list[FinalProblemDiagnosis] = []
    seen: set[str] = set()
    for item in merged:
        key = item.title.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result[:6]


def _fallback_problem_diagnosis(
    round_payloads: list[dict[str, Any]],
    has_effective_round: bool,
) -> list[FinalProblemDiagnosis]:
    if not has_effective_round:
        return [
            FinalProblemDiagnosis(
                title="有效回答证据不足",
                severity="high",
                evidence=["本次面试缺少可用于评分的有效回答。"],
                impact="无法可靠判断岗位匹配度和关键能力水平。",
                suggestion="重新完成至少一个核心轮次，并用具体项目、技术方案、结果数据支撑回答。",
            )
        ]
    items: list[FinalProblemDiagnosis] = []
    for round_payload in round_payloads:
        review = _round_review_from_payload(round_payload)
        if not review.issues and review.score is not None and review.score >= 70:
            continue
        issue_title = review.issues[0] if review.issues else "表现证据不足"
        title = f"{_round_label(review.round_type)}问题：{issue_title}"
        severity: Literal["high", "medium", "low"] = (
            "high" if (review.score or 0) < 60 else "medium"
        )
        items.append(
            FinalProblemDiagnosis(
                title=title,
                severity=severity,
                evidence=review.evidence[:3] or ["该轮总结或题目评分显示证据覆盖不足。"],
                impact=f"影响对{_round_label(review.round_type)}相关能力的判断，可能拉低最终录用建议。",
                suggestion=(
                    review.suggestions[0]
                    if review.suggestions
                    else "补充更具体的背景、行动、技术取舍和结果数据。"
                ),
            )
        )
    if not items:
        items.append(
            FinalProblemDiagnosis(
                title="回答深度仍需继续验证",
                severity="low",
                evidence=["已完成轮次具备基础证据，但仍可补充更细的项目复盘。"],
                impact="当前结论可用，但高阶能力和稳定性还需要更多题目支撑。",
                suggestion="继续补充关键决策、失败复盘、量化收益和与岗位职责相关的工程细节。",
            )
        )
    return items[:6]


def _merge_action_plan(
    generated_items: list[FinalActionPlan],
    problem_diagnosis: list[FinalProblemDiagnosis],
    has_effective_round: bool,
) -> list[FinalActionPlan]:
    fallback_items = _fallback_action_plan(problem_diagnosis, has_effective_round)
    result: list[FinalActionPlan] = []
    seen: set[str] = set()
    for item in [*generated_items, *fallback_items]:
        key = item.title.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result[:5]


def _fallback_action_plan(
    problem_diagnosis: list[FinalProblemDiagnosis],
    has_effective_round: bool,
) -> list[FinalActionPlan]:
    if not has_effective_round:
        return [
            FinalActionPlan(
                title="补齐有效面试证据",
                priority="high",
                steps=[
                    "重新完成核心轮次，避免空回答、泛泛而谈或答非所问。",
                    "每个回答至少包含背景、行动、结果和个人贡献。",
                    "对技术问题补充方案选择、边界条件和失败处理。",
                ],
                expected_outcome="让报告具备足够证据支撑，提升评分和结论可信度。",
            )
        ]
    first_issue = problem_diagnosis[0].title if problem_diagnosis else "关键问题"
    return [
        FinalActionPlan(
            title="补强项目表达证据",
            priority="high",
            steps=[
                "围绕最相关项目准备 2 到 3 个可量化结果。",
                "说明个人负责的模块、关键决策和具体产出。",
                "把回答从“做过什么”升级为“为什么这么做、效果如何”。",
            ],
            expected_outcome=f"直接改善“{first_issue}”对应的证据不足问题。",
        ),
        FinalActionPlan(
            title="补齐技术深度和复盘",
            priority="medium",
            steps=[
                "为高频技术问题准备方案对比、性能瓶颈和异常处理。",
                "复盘一次线上问题、延期或方案调整，说明原因和改进。",
                "回答时主动给出边界条件，避免只停留在结论。",
            ],
            expected_outcome="让技术面和主管面对深度、逻辑和问题解决能力有更稳定的评分依据。",
        ),
    ]


def _merge_follow_up_questions(
    generated_questions: list[str],
    round_payloads: list[dict[str, Any]],
) -> list[str]:
    fallback = _fallback_follow_up_questions(round_payloads)
    return _dedupe_strings([*generated_questions, *fallback])[:6]


def _fallback_follow_up_questions(round_payloads: list[dict[str, Any]]) -> list[str]:
    questions = []
    for item in round_payloads:
        round_type = str(item.get("round_type"))
        summary = _summary_payload(item)
        issue = _string_list(summary.get("main_issues") or summary.get("weaknesses"))
        if issue:
            questions.append(f"{_round_label(round_type)}中提到“{issue[0]}”，请补充一个具体案例和结果数据。")
    if not questions:
        questions.append("请选一个最能代表岗位能力的项目，说明你的具体贡献、关键取舍和量化结果。")
    return questions


def _summary_payload(item: dict[str, Any]) -> dict[str, Any]:
    summary = item.get("summary")
    return summary if isinstance(summary, dict) else {}


def _enriched_ability_analysis(
    generated_items: list[str],
    round_reviews: list[FinalRoundReview],
    has_effective_round: bool,
) -> list[str]:
    if not has_effective_round:
        return ["本次面试缺少有效回答证据，暂不能形成可靠能力画像。"]
    fallback = [
        f"{_round_label(item.round_type)}：得分{item.score if item.score is not None else '暂无'}，"
        f"主要问题为{item.issues[0] if item.issues else '未发现明显短板'}。"
        for item in round_reviews
        if item.status in {"completed", "finished_early"}
    ]
    return _dedupe_strings([*generated_items, *fallback])[:8]


def _diagnosis_to_text(item: FinalProblemDiagnosis) -> str:
    evidence = f"证据：{'；'.join(item.evidence[:2])}。" if item.evidence else ""
    return f"{item.title}。影响：{item.impact}。{evidence}建议：{item.suggestion}"


def _action_plan_to_text(item: FinalActionPlan) -> str:
    steps = "；".join(item.steps[:3]) if item.steps else "补充具体行动。"
    outcome = f"目标：{item.expected_outcome}" if item.expected_outcome else ""
    return f"{item.title}：{steps}。{outcome}".strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _calculate_final_score(
    round_payloads: list[dict[str, Any]],
    selected_round_types: list[str] | None,
) -> tuple[int, bool]:
    considered = _considered_rounds(round_payloads, selected_round_types)
    if not considered:
        return 0, False
    weight = 1 / len(considered)
    weighted_score = 0.0
    has_effective_round = False
    for item in considered:
        score = _round_score(item)
        coefficient = _completion_coefficient(item, score)
        weighted_score += score * coefficient * weight
        if coefficient > 0 and score > 0:
            has_effective_round = True
    if not has_effective_round:
        return 0, False
    return int(round(weighted_score)), True


def _considered_rounds(
    round_payloads: list[dict[str, Any]],
    selected_round_types: list[str] | None,
) -> list[dict[str, Any]]:
    if selected_round_types:
        selected = set(selected_round_types)
        return [item for item in round_payloads if item.get("round_type") in selected]
    return [item for item in round_payloads if item.get("status") != "skipped"]


def _round_score(item: dict[str, Any]) -> int:
    summary = item.get("summary")
    if isinstance(summary, dict):
        score = summary.get("score")
        if isinstance(score, int):
            return max(0, min(100, score))
    score = item.get("score")
    return max(0, min(100, int(score))) if isinstance(score, int) else 0


def _completion_coefficient(item: dict[str, Any], score: int) -> float:
    if score <= 0:
        return 0.0
    status = item.get("status")
    if status == "completed":
        return 1.0
    if status == "finished_early":
        return EARLY_FINISH_COEFFICIENT
    return 0.0


def _final_round_score(item: dict[str, Any]) -> FinalRoundScore:
    return FinalRoundScore(
        round_type=str(item.get("round_type")),
        score=_round_score(item) if isinstance(item.get("score"), int) else None,
        result=str(item.get("result")) if item.get("result") is not None else None,
        is_reference_only=bool(item.get("is_reference_only")),
        status=str(item.get("status")) if item.get("status") is not None else None,
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
