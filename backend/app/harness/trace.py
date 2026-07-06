from __future__ import annotations

from typing import Any

from app.harness.contracts import HarnessExecutionRequest, TraceEventResult
from app.repositories.harness import HarnessRepository


class HarnessTraceError(RuntimeError):
    pass


class TraceRecorder:
    def __init__(self, repository: HarnessRepository) -> None:
        self.repository = repository

    def create_trace(self, request: HarnessExecutionRequest) -> int:
        try:
            return self.repository.create_trace(request)
        except Exception as exc:
            raise HarnessTraceError("failed to create harness trace") from exc

    def record_event(
        self,
        trace_id: int,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        status: str = "succeeded",
        error_message: str | None = None,
    ) -> TraceEventResult:
        try:
            event_id = self.repository.create_trace_event(
                trace_id,
                event_type,
                payload or {},
                status=status,
                error_message=error_message,
            )
            return TraceEventResult(event_id=event_id, status="succeeded")
        except Exception as exc:
            try:
                self.repository.update_trace_status(
                    trace_id,
                    status="running",
                    event_write_failed=True,
                    error_code="TRACE_EVENT_WRITE_FAILED",
                    error_detail=str(exc),
                )
            except Exception:
                pass
            return TraceEventResult(status="failed", error_message=str(exc))
