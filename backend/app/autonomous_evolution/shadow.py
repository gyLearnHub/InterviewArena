from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.autonomous_evolution.anonymization import contains_direct_identifier
from app.autonomous_evolution.contracts import ShadowResult
from app.autonomous_evolution.repository import ArtifactRecord
from app.harness.contracts import HarnessExecutionRequest, RetryPolicy
from app.harness.output_validation import OutputValidationResult
from app.harness.rules import RuleEvaluator
from app.schemas.evaluation import (
    FinalEvaluationOutput,
    QuestionEvaluationOutput,
    RoundEvaluationOutput,
)


class ShadowExecutor:
    def __init__(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def execute(self, artifact: ArtifactRecord, sample: dict[str, Any]) -> ShadowResult:
        if artifact.artifact_type == "prompt":
            result = self._execute_prompt(artifact, sample)
        elif artifact.artifact_type == "flow_config":
            result = self._execute_flow(artifact, sample)
        elif artifact.artifact_type == "harness_policy":
            result = self._execute_harness_policy(artifact, sample)
        else:
            raise ValueError(f"unsupported artifact type: {artifact.artifact_type}")
        harness_errors = _harness_rule_errors(artifact, sample, result)
        metrics = {
            **result.metrics,
            "harness_gate_passed": 0.0 if harness_errors else 1.0,
        }
        return result.model_copy(
            update={
                "metrics": metrics,
                "hard_gate_passed": result.hard_gate_passed and not harness_errors,
                "hard_gate_errors": [*result.hard_gate_errors, *harness_errors],
            }
        )

    def execute_bundle(
        self,
        artifacts: list[ArtifactRecord],
        target_artifact_key: str,
        sample: dict[str, Any],
    ) -> ShadowResult:
        by_key = {artifact.artifact_key: artifact for artifact in artifacts}
        target = by_key.get(target_artifact_key)
        if target is None:
            raise ValueError(f"target artifact is missing from bundle: {target_artifact_key}")

        chain: list[tuple[str, ShadowResult]] = []
        working_sample = dict(sample)
        target_result = self.execute(target, working_sample)
        chain.append((target_artifact_key, target_result))

        if target_artifact_key.startswith("interviewer."):
            round_type = target_artifact_key.rsplit(".", 1)[-1]
            working_sample = _sample_with_generated_question(
                working_sample,
                round_type,
                target_result.output,
            )
            self._append_evaluation_chain(
                chain,
                by_key,
                working_sample,
                start_at="question",
            )
        elif target_artifact_key == "evaluation.question":
            chain = self._generate_full_evaluation_chain(by_key, working_sample)
            target_result = chain[0][1]
        elif target_artifact_key.startswith("evaluation.round."):
            working_sample["_shadow_round_evaluations"] = [target_result.output]
            self._append_evaluation_chain(
                chain,
                by_key,
                working_sample,
                start_at="final",
            )
        elif target_artifact_key == "flow.rounds":
            working_sample["_shadow_flow_config"] = target.content.get("config") or {}
            chain.extend(self._generate_full_evaluation_chain(by_key, working_sample))
        elif target_artifact_key == "harness.policy":
            generated = self._generate_full_evaluation_chain(by_key, working_sample)
            chain.extend(generated)
            replay_sample = dict(working_sample)
            replay_sample["_shadow_traces"] = [
                {
                    "node_type": _node_type(key),
                    "status": "completed" if result.hard_gate_passed else "failed",
                    "validation_status": "passed"
                    if result.hard_gate_passed
                    else "failed",
                    "retry_records": [],
                    "output_snapshot": result.output,
                }
                for key, result in generated
            ]
            target_result = self.execute(target, replay_sample)
            chain[0] = (target_artifact_key, target_result)

        errors = [
            f"{key}: {error}"
            for key, result in chain
            for error in result.hard_gate_errors
        ]
        output = dict(target_result.output)
        output["affected_chain"] = [
            {
                "artifact_key": key,
                "output": result.output,
                "hard_gate_passed": result.hard_gate_passed,
            }
            for key, result in chain
        ]
        metric_keys = {
            key
            for _, result in chain
            for key in result.metrics
        }
        metrics = {
            key: sum(result.metrics.get(key, 0.0) for _, result in chain) / len(chain)
            for key in metric_keys
        }
        metrics["affected_chain_passed"] = 0.0 if errors else 1.0
        metrics["affected_nodes_executed"] = float(len(chain))
        return ShadowResult(
            output=output,
            metrics=metrics,
            hard_gate_passed=not errors,
            hard_gate_errors=errors,
        )

    def _append_evaluation_chain(
        self,
        chain: list[tuple[str, ShadowResult]],
        by_key: dict[str, ArtifactRecord],
        sample: dict[str, Any],
        *,
        start_at: str,
    ) -> None:
        round_type = str(_last_answered_qa(sample).get("round_type") or "technical")
        if start_at == "question":
            artifact = by_key.get("evaluation.question")
            if artifact is None:
                raise ValueError("bundle is missing evaluation.question")
            result = self.execute(artifact, sample)
            chain.append((artifact.artifact_key, result))
            sample["_shadow_question_evaluations"] = [result.output]
        if start_at in {"question", "round"}:
            artifact = by_key.get(f"evaluation.round.{round_type}")
            if artifact is None:
                raise ValueError(f"bundle is missing evaluation.round.{round_type}")
            result = self.execute(artifact, sample)
            chain.append((artifact.artifact_key, result))
            sample["_shadow_round_evaluations"] = [result.output]
        artifact = by_key.get("evaluation.final")
        if artifact is None:
            raise ValueError("bundle is missing evaluation.final")
        result = self.execute(artifact, sample)
        chain.append((artifact.artifact_key, result))

    def _generate_full_evaluation_chain(
        self,
        by_key: dict[str, ArtifactRecord],
        sample: dict[str, Any],
    ) -> list[tuple[str, ShadowResult]]:
        chain: list[tuple[str, ShadowResult]] = []
        question_artifact = by_key.get("evaluation.question")
        final_artifact = by_key.get("evaluation.final")
        if question_artifact is None or final_artifact is None:
            raise ValueError("bundle is missing the complete evaluation chain")
        round_outputs: list[dict[str, Any]] = []
        for round_type in _evaluation_round_types(sample):
            round_sample = _sample_for_round(sample, round_type)
            question_result = self.execute(question_artifact, round_sample)
            chain.append((question_artifact.artifact_key, question_result))
            round_sample["_shadow_question_evaluations"] = [question_result.output]
            round_artifact = by_key.get(f"evaluation.round.{round_type}")
            if round_artifact is None:
                raise ValueError(f"bundle is missing evaluation.round.{round_type}")
            round_result = self.execute(round_artifact, round_sample)
            chain.append((round_artifact.artifact_key, round_result))
            round_outputs.append({"round_type": round_type, **round_result.output})
        final_sample = dict(sample)
        final_sample["_shadow_round_evaluations"] = round_outputs
        final_result = self.execute(final_artifact, final_sample)
        chain.append((final_artifact.artifact_key, final_result))
        return chain

    def _execute_prompt(
        self,
        artifact: ArtifactRecord,
        sample: dict[str, Any],
    ) -> ShadowResult:
        prompt = str(artifact.content.get("text") or "").strip()
        if not prompt:
            return ShadowResult(
                output={"error": "empty prompt"},
                metrics={"valid_output": 0.0, "privacy_safe": 1.0},
                hard_gate_passed=False,
                hard_gate_errors=["prompt is empty"],
            )
        if artifact.artifact_key.startswith("interviewer."):
            output = self._generate_question(artifact.artifact_key, prompt, sample)
            errors = _question_errors(output, sample)
            metrics = {
                "valid_output": 0.0 if errors else 1.0,
                "privacy_safe": 0.0 if contains_direct_identifier(output) else 1.0,
                "duplicate_free": 0.0 if "duplicate question" in errors else 1.0,
            }
        elif artifact.artifact_key == "evaluation.question":
            output = self.llm_client.generate_json(prompt, _question_evaluation_input(sample))
            errors = _model_errors(QuestionEvaluationOutput, output)
            metrics = _evaluation_metrics(output, errors)
        elif artifact.artifact_key.startswith("evaluation.round."):
            output = self.llm_client.generate_json(prompt, _round_evaluation_input(sample))
            errors = _model_errors(RoundEvaluationOutput, output)
            metrics = _evaluation_metrics(output, errors)
        elif artifact.artifact_key == "evaluation.final":
            output = self.llm_client.generate_json(prompt, _final_evaluation_input(sample))
            errors = _model_errors(FinalEvaluationOutput, output)
            metrics = _evaluation_metrics(output, errors)
        else:
            raise ValueError(f"unsupported prompt artifact: {artifact.artifact_key}")
        if contains_direct_identifier(output):
            errors.append("output contains a direct identifier")
        return ShadowResult(
            output=output,
            metrics=metrics,
            hard_gate_passed=not errors,
            hard_gate_errors=errors,
        )

    def _generate_question(
        self,
        artifact_key: str,
        prompt: str,
        sample: dict[str, Any],
    ) -> dict[str, Any]:
        round_type = artifact_key.rsplit(".", 1)[-1]
        qa_history = [
            _compact_shadow_value(item)
            for item in sample.get("qa_history") or []
            if not item.get("round_type") or item.get("round_type") == round_type
        ][-12:]
        resume = dict(_compact_shadow_value(dict(sample.get("resume") or {})))
        resume["_job_description"] = sample.get("job_description") or ""
        resume["_interview_round"] = round_type
        return dict(
            self.llm_client.generate_question(
                resume=resume,
                target_position=str(sample.get("target_position") or "通用岗位"),
                qa_history=qa_history,
                previous_answer=_last_answer(qa_history),
                system_prompt=prompt,
            )
        )

    def _execute_flow(
        self,
        artifact: ArtifactRecord,
        sample: dict[str, Any],
    ) -> ShadowResult:
        config = artifact.content.get("config")
        errors = _flow_config_errors(config)
        qa_history = sample.get("qa_history") or []
        decisions: list[dict[str, Any]] = []
        if isinstance(config, dict):
            for round_type, round_config in config.items():
                round_items = [item for item in qa_history if item.get("round_type") == round_type]
                main_count = sum(item.get("question_kind") == "main" for item in round_items)
                total_count = len(round_items)
                minimum = int((round_config or {}).get("min_total_questions") or 1)
                maximum = int((round_config or {}).get("max_total_questions") or 40)
                decisions.append(
                    {
                        "round_type": round_type,
                        "main_count": main_count,
                        "total_count": total_count,
                        "would_finish": total_count >= minimum,
                        "within_maximum": total_count <= maximum,
                    }
                )
        within_maximum = all(item["within_maximum"] for item in decisions) if decisions else False
        return ShadowResult(
            output={"decisions": decisions, "config_valid": not errors},
            metrics={
                "valid_output": 0.0 if errors else 1.0,
                "privacy_safe": 1.0,
                "flow_limit_compliance": 1.0 if within_maximum else 0.0,
            },
            hard_gate_passed=not errors,
            hard_gate_errors=errors,
        )

    def _execute_harness_policy(
        self,
        artifact: ArtifactRecord,
        sample: dict[str, Any],
    ) -> ShadowResult:
        config = artifact.content.get("config")
        errors = _harness_policy_errors(config)
        traces = sample.get("_shadow_traces") or sample.get("harness_traces") or []
        max_retries = int((config or {}).get("max_retries") or 0) if isinstance(config, dict) else 0
        evaluated = []
        for trace in traces:
            retries = trace.get("retry_records") or []
            evaluated.append(
                {
                    "node_type": trace.get("node_type"),
                    "status": trace.get("status"),
                    "retry_count": len(retries),
                    "retry_within_policy": len(retries) <= max_retries,
                    "validation_passed": trace.get("validation_status") != "failed",
                    "privacy_safe": not contains_direct_identifier(
                        trace.get("output_snapshot")
                    ),
                }
            )
        compliant = all(
            item["retry_within_policy"]
            and item["validation_passed"]
            and item["privacy_safe"]
            for item in evaluated
        )
        return ShadowResult(
            output={"trace_decisions": evaluated, "policy_valid": not errors},
            metrics={
                "valid_output": 0.0 if errors else 1.0,
                "privacy_safe": 1.0,
                "harness_compliance": 1.0 if compliant else 0.0,
            },
            hard_gate_passed=not errors,
            hard_gate_errors=errors,
        )


def validate_candidate_content(artifact_type: str, content: dict[str, Any]) -> list[str]:
    if contains_direct_identifier(content):
        return ["candidate content contains a direct identifier"]
    if artifact_type == "prompt":
        text = content.get("text")
        if not isinstance(text, str) or len(text.strip()) < 20:
            return ["candidate prompt is missing or too short"]
        if "JSON" not in text.upper():
            return ["candidate prompt no longer requires JSON output"]
        return []
    if artifact_type == "flow_config":
        return _flow_config_errors(content.get("config"))
    if artifact_type == "harness_policy":
        return _harness_policy_errors(content.get("config"))
    return ["unsupported artifact type"]


def _harness_rule_errors(
    artifact: ArtifactRecord,
    sample: dict[str, Any],
    result: ShadowResult,
) -> list[str]:
    node_type = _node_type(artifact.artifact_key)
    retry_config = (
        artifact.content.get("config")
        if artifact.artifact_type == "harness_policy"
        else {}
    )
    max_retries = int((retry_config or {}).get("max_retries") or 0)
    try:
        request = HarnessExecutionRequest(
            user_id=max(1, int(sample.get("user_id") or 1)),
            interview_id=max(1, int(sample.get("id") or 1)),
            node_id=f"shadow:{artifact.artifact_key}"[:128],
            node_type=node_type,
            agent_type="autonomous_evolution_shadow",
            purpose="candidate_hard_gate",
            input_payload=sample,
            retry_policy=RetryPolicy(max_retries=max_retries),
            execution_mode="replay",
        )
    except ValidationError as exc:
        return [f"Harness request validation failed: {exc.error_count()} errors"]
    validation = OutputValidationResult(
        validation_status="passed" if result.hard_gate_passed else "failed",
        errors=list(result.hard_gate_errors),
    )
    evaluations = RuleEvaluator().evaluate_node(
        request,
        trace_id=1,
        checkpoint_id=1,
        output_validation=validation,
        retry_count=0,
        event_write_failed=False,
    )
    return [
        f"Harness rule failed: {item.rule_name}"
        for item in evaluations
        if item.severity == "hard" and item.status == "failed"
    ]


def _node_type(artifact_key: str) -> str:
    if artifact_key == "evaluation.question":
        return "question_evaluation"
    if artifact_key.startswith("evaluation.round."):
        return "round_evaluation"
    if artifact_key == "evaluation.final":
        return "final_evaluation"
    if artifact_key.startswith("interviewer."):
        return "question_generation"
    return "harness_policy_evaluation"


def _question_errors(output: dict[str, Any], sample: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    question = output.get("question")
    if not isinstance(question, str) or not question.strip():
        errors.append("question is empty")
        return errors
    normalized = _normalize_question(question)
    old_questions = {
        _normalize_question(str(item.get("question") or ""))
        for item in sample.get("qa_history") or []
    }
    if normalized in old_questions:
        errors.append("duplicate question")
    if not isinstance(output.get("question_type"), str):
        errors.append("question_type is missing")
    return errors


def _model_errors(model: Any, output: dict[str, Any]) -> list[str]:
    try:
        model.model_validate(output)
    except ValidationError as exc:
        return [f"schema validation failed: {exc.error_count()} errors"]
    return []


def _evaluation_metrics(output: dict[str, Any], errors: list[str]) -> dict[str, float]:
    score = output.get("total_score")
    score_valid = isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 100
    return {
        "valid_output": 0.0 if errors else 1.0,
        "privacy_safe": 0.0 if contains_direct_identifier(output) else 1.0,
        "score_boundary_valid": 1.0 if score_valid else 0.0,
        "evidence_present": 1.0 if output.get("evidence") else 0.0,
    }


def _question_evaluation_input(sample: dict[str, Any]) -> dict[str, Any]:
    qa = _last_answered_qa(sample)
    return {
        "interview_id": int(sample.get("id") or 0),
        "round_id": int(qa.get("round_id") or 0),
        "question_id": int(qa.get("id") or 0),
        "round_type": str(qa.get("round_type") or "technical"),
        "dimensions": _dimensions(sample, str(qa.get("round_type") or "technical")),
        "resume": dict(_compact_shadow_value(dict(sample.get("resume") or {}))),
        "target_position": str(sample.get("target_position") or "通用岗位"),
        "job_description": sample.get("job_description"),
        "interview_strategy": _strategy(sample),
        "question": str(qa.get("question") or ""),
        "answer": str(qa.get("answer") or ""),
    }


def _round_evaluation_input(sample: dict[str, Any]) -> dict[str, Any]:
    qa = _last_answered_qa(sample)
    round_type = str(qa.get("round_type") or "technical")
    round_qa = [
        item
        for item in sample.get("qa_history") or []
        if item.get("round_type") == round_type
    ]
    return {
        "interview_id": int(sample.get("id") or 0),
        "round_id": int(qa.get("round_id") or 0),
        "round_type": round_type,
        "dimensions": _dimensions(sample, round_type),
        "qa_history": _compact_shadow_value(round_qa),
        "question_evaluations": list(sample.get("_shadow_question_evaluations") or []),
        "interview_strategy": _strategy(sample),
        "is_reference_only": False,
    }


def _final_evaluation_input(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "interview_id": int(sample.get("id") or 0),
        "resume_summary": dict(_compact_shadow_value(dict(sample.get("resume") or {}))),
        "target_position": str(sample.get("target_position") or "通用岗位"),
        "job_description": sample.get("job_description"),
        "interview_strategy": _strategy(sample),
        "round_evaluations": list(
            sample.get("_shadow_round_evaluations") or sample.get("rounds") or []
        ),
        "has_incomplete_rounds": False,
        "has_reference_only_rounds": any(
            bool(item.get("is_reference_only")) for item in sample.get("rounds") or []
        ),
    }


def _flow_config_errors(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["flow config must be an object"]
    errors: list[str] = []
    for round_type in ("resume", "technical", "manager", "hr"):
        item = value.get(round_type)
        if not isinstance(item, dict):
            errors.append(f"missing round config: {round_type}")
            continue
        for minimum_key, maximum_key in (
            ("min_main_questions", "max_main_questions"),
            ("min_total_questions", "max_total_questions"),
        ):
            minimum = item.get(minimum_key)
            maximum = item.get(maximum_key)
            if not _bounded_question_count(minimum) or not _bounded_question_count(maximum):
                errors.append(f"invalid question bounds: {round_type}")
            elif isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
                errors.append(f"minimum exceeds maximum: {round_type}")
        dimensions = item.get("dimensions")
        if not isinstance(dimensions, list) or not all(
            isinstance(value, str) and value.strip() for value in dimensions
        ):
            errors.append(f"invalid dimensions: {round_type}")
        topics = item.get("core_topics")
        if not isinstance(topics, dict) or not topics or not all(
            isinstance(topic, str)
            and topic.strip()
            and isinstance(aliases, list)
            and aliases
            and all(isinstance(alias, str) and alias.strip() for alias in aliases)
            for topic, aliases in (topics or {}).items()
        ):
            errors.append(f"invalid core topics: {round_type}")
        if all(
            _bounded_question_count(item.get(key))
            for key in (
                "min_main_questions",
                "max_main_questions",
                "min_total_questions",
                "max_total_questions",
            )
        ) and (
            int(item["min_main_questions"]) > int(item["min_total_questions"])
            or int(item["max_main_questions"]) > int(item["max_total_questions"])
        ):
            errors.append(f"main question bounds exceed total bounds: {round_type}")
    return errors


def _harness_policy_errors(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["Harness policy must be an object"]
    errors: list[str] = []
    retries = value.get("max_retries")
    if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= 3:
        errors.append("max_retries must be between 0 and 3")
    for key in (
        "require_json_object",
        "forbid_scoring_memory",
        "checkpoint_required",
        "privacy_gate",
    ):
        if value.get(key) is not True:
            errors.append(f"safety invariant cannot be disabled: {key}")
    return errors


def _last_answered_qa(sample: dict[str, Any]) -> dict[str, Any]:
    answered = [
        item
        for item in sample.get("qa_history") or []
        if str(item.get("answer") or "").strip()
    ]
    return dict(answered[-1]) if answered else {}


def _sample_with_generated_question(
    sample: dict[str, Any],
    round_type: str,
    question_output: dict[str, Any],
) -> dict[str, Any]:
    result = dict(sample)
    history = [dict(item) for item in sample.get("qa_history") or []]
    previous = _last_answered_qa(sample)
    history.append(
        {
            "id": int(previous.get("id") or 0) + 1,
            "round_id": int(previous.get("round_id") or 0),
            "round_type": round_type,
            "question": str(question_output.get("question") or ""),
            "answer": str(previous.get("answer") or "匿名回放回答"),
            "question_kind": "follow_up",
        }
    )
    result["qa_history"] = history
    return result


def _evaluation_round_types(sample: dict[str, Any]) -> list[str]:
    supported = {"resume", "technical", "manager", "hr"}
    result: list[str] = []
    for item in sample.get("qa_history") or []:
        round_type = str(item.get("round_type") or "")
        if round_type in supported and str(item.get("answer") or "").strip():
            if round_type not in result:
                result.append(round_type)
    return result or ["technical"]


def _sample_for_round(sample: dict[str, Any], round_type: str) -> dict[str, Any]:
    result = dict(sample)
    result["qa_history"] = [
        dict(item)
        for item in sample.get("qa_history") or []
        if item.get("round_type") == round_type
    ]
    return result


def _last_answer(qa_history: list[dict[str, Any]]) -> str | None:
    for item in reversed(qa_history):
        answer = str(item.get("answer") or "").strip()
        if answer:
            return answer
    return None


def _dimensions(sample: dict[str, Any], round_type: str) -> list[str]:
    flow_config = sample.get("_shadow_flow_config")
    if isinstance(flow_config, dict):
        round_config = flow_config.get(round_type)
        if isinstance(round_config, dict):
            dimensions = round_config.get("dimensions")
            if isinstance(dimensions, list):
                values = [
                    str(dimension).strip()
                    for dimension in dimensions
                    if str(dimension).strip()
                ]
                if values:
                    return values
    for item in sample.get("rounds") or []:
        if item.get("round_type") == round_type:
            summary = item.get("summary") or {}
            reviews = summary.get("dimension_reviews") or summary.get("dimension_scores") or []
            values = [str(review.get("dimension") or "").strip() for review in reviews]
            if any(values):
                return [value for value in values if value]
    return ["岗位相关性", "回答质量", "证据充分性"]


def _strategy(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "interview_goal": sample.get("interview_goal") or "campus",
        "difficulty": sample.get("difficulty") or "normal",
        "time_limit_minutes": int(sample.get("time_limit_minutes") or 45),
    }


def _bounded_question_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 40


def _normalize_question(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _compact_shadow_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, dict):
        return {
            str(key)[:128]: _compact_shadow_value(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [
            _compact_shadow_value(item, depth=depth + 1)
            for item in list(value)[:20]
        ]
    return value
