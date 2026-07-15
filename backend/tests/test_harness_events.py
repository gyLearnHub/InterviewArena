from types import SimpleNamespace
from typing import Any

import app.harness.events as events_module
from app.harness.events import build_harness_request, record_harness_event


class RecordingHarnessRepository:
    def __init__(self, existing_trace_id: int | None = None) -> None:
        self.existing_trace_id = existing_trace_id
        self.created_requests: list[Any] = []
        self.events: list[dict[str, Any]] = []
        self.status_updates: list[dict[str, Any]] = []

    def latest_user_trace_for_node(self, *, node_id: str, user_id: int) -> Any | None:
        if self.existing_trace_id is None:
            return None
        return SimpleNamespace(id=self.existing_trace_id)

    def create_trace(self, request: Any) -> int:
        self.created_requests.append(request)
        return 41

    def create_trace_event(
        self,
        trace_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        self.events.append(
            {"trace_id": trace_id, "event_type": event_type, "payload": payload}
        )
        return 51

    def update_trace_status(self, trace_id: int, **values: Any) -> None:
        self.status_updates.append({"trace_id": trace_id, **values})


def test_build_harness_request_records_prompt_version_in_trace_identity() -> None:
    base = {
        "user_id": 1,
        "interview_id": 2,
        "round_id": 3,
        "node_type": "round_question_generator",
        "agent_type": "technical",
        "purpose": "generate_question",
        "payload": {"question_index": 1},
    }

    first = build_harness_request(**base, prompt_version="interviewer-technical-v1")
    evolved = build_harness_request(
        **base,
        prompt_version="interviewer-technical-v1|b7|abcdef123456",
    )

    assert first.prompt_version == "interviewer-technical-v1"
    assert evolved.prompt_version == "interviewer-technical-v1|b7|abcdef123456"
    assert first.idempotency_key != evolved.idempotency_key


def test_record_harness_event_creates_trace_and_event(
    monkeypatch: Any,
) -> None:
    repository = RecordingHarnessRepository()
    monkeypatch.setattr(events_module, "HarnessRepository", lambda connection: repository)

    recorded = record_harness_event(
        connection=object(),
        user_id=1,
        interview_id=2,
        round_id=3,
        node_type="skill_runner",
        event_type="skill_calls_completed",
        payload={"skills": ["resume"]},
    )

    assert recorded is True
    assert repository.created_requests[0].node_id == "2:3:skill_runner"
    assert repository.events == [
        {
            "trace_id": 41,
            "event_type": "skill_calls_completed",
            "payload": {"skills": ["resume"]},
        }
    ]
    assert repository.status_updates[0]["status"] == "completed"


def test_record_harness_event_reuses_existing_trace(monkeypatch: Any) -> None:
    repository = RecordingHarnessRepository(existing_trace_id=88)
    monkeypatch.setattr(events_module, "HarnessRepository", lambda connection: repository)

    recorded = record_harness_event(
        connection=object(),
        user_id=1,
        interview_id=2,
        round_id=None,
        node_type="memory_write_tracker",
        event_type="memory_summary_written",
        payload={"created_or_updated": 2},
    )

    assert recorded is True
    assert repository.created_requests == []
    assert repository.events[0]["trace_id"] == 88
    assert repository.status_updates == []


def test_record_harness_event_without_connection_is_skipped() -> None:
    assert (
        record_harness_event(
            connection=None,
            user_id=1,
            interview_id=2,
            round_id=None,
            node_type="memory_write_tracker",
            event_type="memory_summary_written",
            payload={},
        )
        is False
    )
