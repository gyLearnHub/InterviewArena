from __future__ import annotations

from time import perf_counter
from typing import Any

from app.harness.context_builder import ContextBuilder, ContextIsolationError
from app.harness.contracts import (
    CheckpointCreate,
    HarnessExecutionRequest,
    HarnessExecutionResult,
)
from app.harness.output_validation import OutputValidationResult, OutputValidator
from app.harness.rules import RuleEvaluator
from app.harness.state import CheckpointError, CheckpointManager
from app.harness.tools import ToolExecutionResult, ToolRegistry, ToolRegistryError
from app.harness.trace import TraceRecorder
from app.repositories.harness import HarnessRepository


class HarnessExecutionService:
    def __init__(
        self,
        repository: HarnessRepository,
        *,
        tool_registry: ToolRegistry | None = None,
        context_builder: ContextBuilder | None = None,
        output_validator: OutputValidator | None = None,
        trace_recorder: TraceRecorder | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        rule_evaluator: RuleEvaluator | None = None,
    ) -> None:
        self.repository = repository
        self.tool_registry = tool_registry or ToolRegistry()
        self.context_builder = context_builder or ContextBuilder()
        self.output_validator = output_validator or OutputValidator()
        self.trace_recorder = trace_recorder or TraceRecorder(repository)
        self.checkpoint_manager = checkpoint_manager or CheckpointManager(repository)
        self.rule_evaluator = rule_evaluator or RuleEvaluator(repository)

    def execute(self, request: HarnessExecutionRequest) -> HarnessExecutionResult:
        started_at = perf_counter()
        trace_id = self.trace_recorder.create_trace(request)
        event_write_failed = False
        retry_records: list[dict[str, Any]] = []
        degradation_records: list[dict[str, Any]] = []
        checkpoint_id: int | None = None
        context_summary: dict[str, Any] = {}
        tool_summary: dict[str, Any] = {}
        business_result: Any = None
        validation = OutputValidationResult(validation_status="pending")
        status = "running"
        error_code: str | None = None
        error_detail: str | None = None

        try:
            context_result = self.context_builder.build(request)
            context_summary = context_result.summary
            event_write_failed |= self._event_failed(
                trace_id,
                "context_built",
                {"summary": context_summary},
            )

            tool_result, retries = self._execute_tool_with_retries(
                request,
                {
                    "input": request.input_payload,
                    "context": context_result.context,
                    "context_summary": context_summary,
                },
            )
            retry_records.extend(retries)
            tool_summary = {
                "tool_name": tool_result.tool_name,
                "status": tool_result.status,
                "error_message": tool_result.error_message,
            }
            event_write_failed |= self._event_failed(trace_id, "tool_called", tool_summary)

            if tool_result.status != "succeeded":
                raise RuntimeError(tool_result.error_message or "tool execution failed")

            business_result = tool_result.output
            validation = self.output_validator.validate(business_result, request.expected_schema)
            event_write_failed |= self._event_failed(
                trace_id,
                "output_validated",
                {
                    "validation_status": validation.validation_status,
                    "errors": validation.errors,
                },
            )
            if validation.validation_status == "failed":
                raise RuntimeError("; ".join(validation.errors) or "output validation failed")

            checkpoint_id = self._create_checkpoint(
                request=request,
                trace_id=trace_id,
                business_result=validation.normalized_output,
                context_summary=context_summary,
                tool_summary=tool_summary,
            )
            event_write_failed |= self._event_failed(
                trace_id,
                "checkpoint_saved",
                {"checkpoint_id": checkpoint_id},
            )
            status = "completed"
        except ContextIsolationError as exc:
            status = "failed"
            error_code = "CONTEXT_ISOLATION_FAILED"
            error_detail = str(exc)
        except CheckpointError as exc:
            status = "paused"
            error_code = "CHECKPOINT_SAVE_FAILED"
            error_detail = str(exc)
        except ToolRegistryError as exc:
            status = "failed"
            error_code = "TOOL_REGISTRY_FAILED"
            error_detail = str(exc)
        except Exception as exc:
            status = "failed"
            error_code = "HARNESS_EXECUTION_FAILED"
            error_detail = str(exc)

        elapsed_ms = int((perf_counter() - started_at) * 1000)
        evaluations = self.rule_evaluator.evaluate_node(
            request,
            trace_id=trace_id,
            checkpoint_id=checkpoint_id,
            output_validation=validation,
            retry_count=len(retry_records),
            event_write_failed=event_write_failed,
        )
        self.rule_evaluator.save_all(
            user_id=request.user_id,
            interview_id=request.interview_id,
            trace_id=trace_id,
            evaluations=evaluations,
        )
        event_write_failed |= self._event_failed(
            trace_id,
            "rule_evaluated",
            {"count": len(evaluations)},
        )
        if event_write_failed:
            status = "degraded" if status == "completed" else status
            degradation_records.append(
                {
                    "code": "TRACE_EVENT_WRITE_FAILED",
                    "detail": "one or more trace events failed to persist",
                }
            )

        self.repository.update_trace_status(
            trace_id,
            status=status,
            validation_status=validation.validation_status,
            output_snapshot={"result": business_result} if business_result is not None else None,
            context_summary=context_summary,
            tool_summary=tool_summary,
            retry_records=retry_records,
            degradation_records=degradation_records,
            elapsed_ms=elapsed_ms,
            error_code=error_code,
            error_detail=error_detail,
            event_write_failed=event_write_failed,
        )
        return HarnessExecutionResult(
            trace_id=trace_id,
            business_result=business_result,
            validation_status=validation.validation_status,
            injected_context_summary=context_summary,
            tool_call_summary=tool_summary,
            elapsed_ms=elapsed_ms,
            retry_records=retry_records,
            degradation_records=degradation_records,
            rule_evaluations=evaluations,
            checkpoint_id=checkpoint_id,
            source_trace_id=request.source_trace_id,
            event_write_failed=event_write_failed,
            status=status,  # type: ignore[arg-type]
            error_code=error_code,
            error_detail=error_detail,
        )

    def _execute_tool_with_retries(
        self,
        request: HarnessExecutionRequest,
        payload: dict[str, Any],
    ) -> tuple[ToolExecutionResult, list[dict[str, Any]]]:
        retries: list[dict[str, Any]] = []
        attempts = request.retry_policy.max_retries + 1
        last_result: ToolExecutionResult | None = None
        for attempt in range(1, attempts + 1):
            last_result = self.tool_registry.execute(request, payload)
            if last_result.status == "succeeded":
                return last_result, retries
            if attempt < attempts:
                retries.append(
                    {
                        "attempt": attempt,
                        "tool_name": last_result.tool_name,
                        "error_message": last_result.error_message,
                    }
                )
        if last_result is None:
            raise RuntimeError("tool was not executed")
        return last_result, retries

    def _create_checkpoint(
        self,
        *,
        request: HarnessExecutionRequest,
        trace_id: int,
        business_result: Any,
        context_summary: dict[str, Any],
        tool_summary: dict[str, Any],
    ) -> int:
        return self.checkpoint_manager.create_checkpoint(
            CheckpointCreate(
                user_id=request.user_id,
                interview_id=request.interview_id,
                round_id=request.round_id,
                trace_id=trace_id,
                node_id=request.node_id,
                checkpoint_type=request.node_type,
                snapshot={
                    "node_id": request.node_id,
                    "node_type": request.node_type,
                    "business_result": business_result,
                    "context_summary": context_summary,
                    "tool_summary": tool_summary,
                },
                resume_version=request.prompt_version,
            )
        )

    def _event_failed(
        self,
        trace_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> bool:
        result = self.trace_recorder.record_event(trace_id, event_type, payload)
        return result.status == "failed"
