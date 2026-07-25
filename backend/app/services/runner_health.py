from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock


@dataclass
class RunnerHealthState:
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    iterations: int = 0


_states: dict[str, RunnerHealthState] = {}
_lock = Lock()


def record_runner_success(name: str) -> None:
    with _lock:
        state = _states.setdefault(name, RunnerHealthState())
        state.last_success_at = datetime.now(UTC)
        state.iterations += 1


def record_runner_failure(name: str, exc: Exception) -> None:
    with _lock:
        state = _states.setdefault(name, RunnerHealthState())
        state.last_failure_at = datetime.now(UTC)
        state.last_error = exc.__class__.__name__
        state.iterations += 1


def runner_health(name: str) -> dict[str, object]:
    with _lock:
        state = _states.get(name)
        if state is None:
            return {"status": "degraded", "reason": "runner is starting"}
        failed_latest = (
            state.last_failure_at is not None
            and (
                state.last_success_at is None
                or state.last_failure_at > state.last_success_at
            )
        )
        result: dict[str, object] = {
            "status": "failed" if failed_latest else "ok",
            "iterations": state.iterations,
            "last_success_at": _iso(state.last_success_at),
        }
        if state.last_failure_at is not None:
            result["last_failure_at"] = _iso(state.last_failure_at)
            result["last_error"] = state.last_error
        return result


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None
