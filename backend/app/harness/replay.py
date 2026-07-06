from __future__ import annotations

from typing import Any

from app.harness.contracts import ReplayRequest
from app.repositories.harness import HarnessRepository


class ReplayService:
    def __init__(self, repository: HarnessRepository) -> None:
        self.repository = repository

    def replay(
        self,
        request: ReplayRequest,
        executor: Any | None = None,
    ) -> int:
        source = self.repository.get_trace(request.source_trace_id)
        if source is None:
            raise ValueError("source trace not found")
        try:
            result = executor(source, request.parameters) if executor is not None else None
            diff_summary = _diff(source.output_snapshot, result)
            return self.repository.create_replay_run(
                user_id=source.user_id,
                interview_id=source.interview_id,
                source_trace_id=source.id,
                mode=request.mode,
                parameters=request.parameters,
                status="completed",
                result_snapshot={"result": result},
                diff_summary=diff_summary,
            )
        except Exception as exc:
            return self.repository.create_replay_run(
                user_id=source.user_id,
                interview_id=source.interview_id,
                source_trace_id=source.id,
                mode=request.mode,
                parameters=request.parameters,
                status="failed",
                diff_summary={},
                error_message=str(exc),
            )


def _diff(old: Any, new: Any) -> dict[str, Any]:
    return {
        "changed": old != new,
        "old_type": type(old).__name__,
        "new_type": type(new).__name__,
    }
