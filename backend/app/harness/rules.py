from __future__ import annotations

from app.harness.contracts import (
    HarnessExecutionRequest,
    RuleEvaluation,
    find_long_term_memory_keys,
    is_scoring_node,
)
from app.harness.output_validation import OutputValidationResult
from app.repositories.harness import HarnessRepository


class RuleEvaluator:
    def __init__(self, repository: HarnessRepository | None = None) -> None:
        self.repository = repository

    def evaluate_node(
        self,
        request: HarnessExecutionRequest,
        *,
        trace_id: int | None,
        checkpoint_id: int | None,
        output_validation: OutputValidationResult,
        retry_count: int,
        event_write_failed: bool,
    ) -> list[RuleEvaluation]:
        evaluations = [
            RuleEvaluation(
                rule_name="output_schema_valid",
                status="passed" if output_validation.validation_status != "failed" else "failed",
                severity="hard",
                evidence={"validation_status": output_validation.validation_status},
                failure_reason="; ".join(output_validation.errors) or None,
                overall_grade="FAIL"
                if output_validation.validation_status == "failed"
                else "PASS",
            ),
            RuleEvaluation(
                rule_name="trace_created",
                status="passed" if trace_id is not None else "failed",
                severity="hard",
                evidence={"trace_id": trace_id},
                failure_reason=None if trace_id is not None else "trace main record is required",
                overall_grade="PASS" if trace_id is not None else "FAIL",
            ),
            RuleEvaluation(
                rule_name="checkpoint_created",
                status="passed" if checkpoint_id is not None else "warning",
                severity="warning",
                evidence={"checkpoint_id": checkpoint_id},
                failure_reason=None if checkpoint_id is not None else "checkpoint was not created",
                overall_grade="PASS" if checkpoint_id is not None else "PASS_WITH_WARNINGS",
            ),
            RuleEvaluation(
                rule_name="retry_limit",
                status="passed" if retry_count <= request.retry_policy.max_retries else "failed",
                severity="hard",
                evidence={
                    "retry_count": retry_count,
                    "max_retries": request.retry_policy.max_retries,
                },
                failure_reason=None
                if retry_count <= request.retry_policy.max_retries
                else "retry limit exceeded",
                overall_grade="PASS"
                if retry_count <= request.retry_policy.max_retries
                else "FAIL",
            ),
        ]
        if event_write_failed:
            evaluations.append(
                RuleEvaluation(
                    rule_name="trace_event_write",
                    status="warning",
                    severity="warning",
                    evidence={"event_write_failed": True},
                    failure_reason="one or more trace events failed to persist",
                    overall_grade="PASS_WITH_WARNINGS",
                )
            )
        illegal_memory = find_long_term_memory_keys(
            {
                "context_refs": request.context_refs,
                "retrieval_params": request.retrieval_params,
                "input_payload": request.input_payload,
            }
        )
        if is_scoring_node(request.node_type):
            evaluations.append(
                RuleEvaluation(
                    rule_name="scoring_long_term_memory_forbidden",
                    status="failed" if illegal_memory else "passed",
                    severity="hard",
                    evidence={"illegal_keys": sorted(illegal_memory)},
                    failure_reason="scoring nodes cannot use long-term memory"
                    if illegal_memory
                    else None,
                    overall_grade="FAIL" if illegal_memory else "PASS",
                )
            )
        return evaluations

    def save_all(
        self,
        *,
        user_id: int,
        interview_id: int,
        trace_id: int | None,
        evaluations: list[RuleEvaluation],
    ) -> None:
        if self.repository is None:
            return
        for evaluation in evaluations:
            self.repository.save_rule_evaluation(
                user_id=user_id,
                interview_id=interview_id,
                trace_id=trace_id,
                evaluation=evaluation,
            )
