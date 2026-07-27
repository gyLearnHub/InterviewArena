import logging
import re
import threading
import uuid
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER = logging.getLogger("interviewarena.http")
REQUEST_ID_HEADER = b"x-request-id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
current_request_id: ContextVar[str | None] = ContextVar(
    "interviewarena_request_id",
    default=None,
)


@dataclass
class _RequestMetric:
    count: int = 0
    duration_seconds_sum: float = 0.0
    duration_seconds_max: float = 0.0


class HttpMetricsRegistry:
    """Small process-local HTTP registry with bounded route labels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_requests = 0
        self._requests: dict[tuple[str, str, int], _RequestMetric] = defaultdict(
            _RequestMetric
        )

    def start_request(self) -> None:
        with self._lock:
            self._active_requests += 1

    def finish_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        key = (method, route, status_code)
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            metric = self._requests[key]
            metric.count += 1
            metric.duration_seconds_sum += duration_seconds
            metric.duration_seconds_max = max(
                metric.duration_seconds_max,
                duration_seconds,
            )

    def render_prometheus(self) -> str:
        with self._lock:
            active_requests = self._active_requests
            rows = [
                (key, _RequestMetric(**vars(metric)))
                for key, metric in self._requests.items()
            ]

        lines = [
            "# HELP interviewarena_http_requests_in_progress Current HTTP requests.",
            "# TYPE interviewarena_http_requests_in_progress gauge",
            f"interviewarena_http_requests_in_progress {active_requests}",
            "# HELP interviewarena_http_requests_total Completed HTTP requests.",
            "# TYPE interviewarena_http_requests_total counter",
        ]
        for (method, route, status_code), metric in sorted(rows):
            labels = _metric_labels(method, route, status_code)
            lines.append(
                f"interviewarena_http_requests_total{{{labels}}} {metric.count}"
            )
        lines.extend(
            [
                (
                    "# HELP interviewarena_http_request_duration_seconds "
                    "HTTP request duration by route."
                ),
                "# TYPE interviewarena_http_request_duration_seconds summary",
            ]
        )
        for (method, route, status_code), metric in sorted(rows):
            labels = _metric_labels(method, route, status_code)
            lines.append(
                "interviewarena_http_request_duration_seconds_sum"
                f"{{{labels}}} {metric.duration_seconds_sum:.6f}"
            )
            lines.append(
                "interviewarena_http_request_duration_seconds_count"
                f"{{{labels}}} {metric.count}"
            )
        lines.extend(
            [
                (
                    "# HELP interviewarena_http_request_duration_max_seconds "
                    "Maximum observed HTTP request duration by route."
                ),
                "# TYPE interviewarena_http_request_duration_max_seconds gauge",
            ]
        )
        for (method, route, status_code), metric in sorted(rows):
            labels = _metric_labels(method, route, status_code)
            lines.append(
                "interviewarena_http_request_duration_max_seconds"
                f"{{{labels}}} {metric.duration_seconds_max:.6f}"
            )
        return "\n".join(lines) + "\n"

    def reset_for_tests(self) -> None:
        with self._lock:
            self._active_requests = 0
            self._requests.clear()


HTTP_METRICS = HttpMetricsRegistry()


class RequestObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        token = current_request_id.set(request_id)
        method = str(scope.get("method") or "UNKNOWN").upper()
        started_at = perf_counter()
        status_code = 500
        HTTP_METRICS.start_request()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() != REQUEST_ID_HEADER
                ]
                headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            LOGGER.error(
                (
                    "http_request_failed request_id=%s method=%s path=%s "
                    "error_type=%s"
                ),
                request_id,
                method,
                _safe_request_path(scope),
                exc.__class__.__name__,
            )
            raise
        finally:
            duration_seconds = max(0.0, perf_counter() - started_at)
            route = _route_template(scope)
            HTTP_METRICS.finish_request(
                method=method,
                route=route,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            LOGGER.info(
                (
                    "http_request request_id=%s method=%s route=%s "
                    "status_code=%s duration_ms=%.2f"
                ),
                request_id,
                method,
                route,
                status_code,
                duration_seconds * 1000,
            )
            current_request_id.reset(token)


def _request_id_from_scope(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.lower() != REQUEST_ID_HEADER:
            continue
        candidate = str(value.decode("ascii", errors="ignore").strip())
        if REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
        break
    return str(uuid.uuid4().hex)


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return "__unmatched__"


def _safe_request_path(scope: Scope) -> str:
    path = str(scope.get("path") or "")
    return path[:256]


def _metric_labels(method: str, route: str, status_code: int) -> str:
    return (
        f'method="{_escape_label(method)}",'
        f'route="{_escape_label(route)}",'
        f'status_code="{status_code}"'
    )


def _escape_label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
