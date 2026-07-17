from datetime import datetime
from typing import Any

import pytest
from app.core.config import Settings
from app.repositories.interviews import InterviewRecord, InterviewRoundRecord, QARecord
from app.schemas.short_term_memory import ShortTermMemorySnapshot
from app.services.short_term_memory import ShortTermMemoryService
from app.services.short_term_memory_store import ShortTermMemoryStoreError


class FakeRepository:
    connection = None

    def __init__(self, qa_records: list[QARecord]) -> None:
        self.interview = InterviewRecord(
            id=10,
            user_id=3,
            resume_id=2,
            target_position="后端工程师",
            status="in_progress",
            question_count=len(qa_records),
            started_at=datetime.utcnow(),
            ended_at=None,
            current_round="technical",
            overall_status="in_progress",
        )
        self.rounds = [
            InterviewRoundRecord(
                id=100,
                interview_id=10,
                agent_type="resume_interviewer",
                round_type="resume",
                status="completed",
                min_main_questions=0,
                max_main_questions=40,
                min_total_questions=0,
                max_total_questions=40,
                score=80,
                result="passed",
                summary={
                    "score": 80,
                    "result": "passed",
                    "strengths": ["经历具体"],
                    "main_issues": ["量化证据不足"],
                },
                is_reference_only=False,
                started_at=datetime.utcnow(),
                ended_at=datetime.utcnow(),
            ),
            InterviewRoundRecord(
                id=200,
                interview_id=10,
                agent_type="technical_interviewer",
                round_type="technical",
                status="in_progress",
                min_main_questions=0,
                max_main_questions=40,
                min_total_questions=0,
                max_total_questions=40,
                score=None,
                result=None,
                summary=None,
                is_reference_only=False,
                started_at=datetime.utcnow(),
                ended_at=None,
            ),
        ]
        self.qa_records = qa_records

    def get_interview_for_user(self, interview_id: int, user_id: int) -> InterviewRecord | None:
        if interview_id == self.interview.id and user_id == self.interview.user_id:
            return self.interview
        return None

    def list_rounds(self, interview_id: int) -> list[InterviewRoundRecord]:
        return self.rounds if interview_id == self.interview.id else []

    def list_qa(self, interview_id: int) -> list[QARecord]:
        return self.qa_records if interview_id == self.interview.id else []


class FakeEvaluationService:
    def question_scores_by_id(self, interview_id: int) -> dict[int, dict[str, Any]]:
        return {
            qa_id: {
                "total_score": 60 + qa_id,
                "strengths": [f"优点{qa_id}"],
                "issues": [f"问题{qa_id}"],
                "should_follow_up": qa_id == 2,
                "follow_up_direction": "补充并发控制" if qa_id == 2 else None,
            }
            for qa_id in range(1, 8)
        }


class MemoryStore:
    def __init__(self) -> None:
        self.snapshot: ShortTermMemorySnapshot | None = None
        self.deleted = False

    def load(self, user_id: int, interview_id: int) -> ShortTermMemorySnapshot | None:
        return self.snapshot

    def compare_and_set(
        self,
        snapshot: ShortTermMemorySnapshot,
        *,
        expected_version: int | None,
    ) -> ShortTermMemorySnapshot:
        current = self.snapshot.version if self.snapshot is not None else None
        assert current == expected_version
        self.snapshot = snapshot.model_copy(update={"version": (current or 0) + 1})
        return self.snapshot

    def delete(self, user_id: int, interview_id: int) -> bool:
        self.deleted = self.snapshot is not None
        self.snapshot = None
        return self.deleted


class FailingStore(MemoryStore):
    def load(self, user_id: int, interview_id: int) -> ShortTermMemorySnapshot | None:
        raise ShortTermMemoryStoreError("redis unavailable")


def _qa_records(answer_size: int = 24) -> list[QARecord]:
    return [
        QARecord(
            id=index,
            interview_id=10,
            round_id=200,
            sequence=index,
            question_type=f"topic_{index}",
            question=f"第 {index} 个技术问题",
            answer=f"回答 {index} " + "细节" * answer_size,
            created_at=datetime.utcnow(),
        )
        for index in range(1, 8)
    ]


def _service(store: MemoryStore, answer_size: int = 24) -> ShortTermMemoryService:
    return ShortTermMemoryService(
        FakeRepository(_qa_records(answer_size)),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        FakeEvaluationService(),  # type: ignore[arg-type]
        Settings(
            app_env="test",
            short_memory_recent_qa_limit=5,
            short_memory_token_budget=8000,
        ),
    )


def test_sync_keeps_five_recent_qa_and_compresses_older_answers() -> None:
    store = MemoryStore()
    status = _service(store).sync(3, 10)

    assert status.status == "recovered"
    assert status.compressed is True
    assert store.snapshot is not None
    assert [item.question_id for item in store.snapshot.recent_qa] == [3, 4, 5, 6, 7]
    assert store.snapshot.rolling_summary.evidence_question_ids == [1, 2]
    assert "补充并发控制" in store.snapshot.rolling_summary.pending_follow_ups
    assert store.snapshot.completed_rounds[0].round_type == "resume"


def test_prompt_context_hides_old_raw_answers_and_filters_role_view() -> None:
    store = MemoryStore()
    service = _service(store)
    service.sync(3, 10)
    repository = service.repository
    history = [
        {
            "id": qa.id,
            "question": qa.question,
            "question_type": qa.question_type,
            "question_kind": qa.question_kind,
            "answer": qa.answer,
        }
        for qa in repository.qa_records  # type: ignore[attr-defined]
    ]

    context, generation_history, status = service.prompt_context(
        user_id=3,
        interview=repository.interview,  # type: ignore[attr-defined]
        round_record=repository.rounds[1],  # type: ignore[attr-defined]
        qa_history=history,
    )

    assert status.source == "redis"
    assert "answer" not in generation_history[0]
    assert generation_history[-1]["answer"].startswith("回答 7")
    assert len(context["recent_qa"]) == 5
    assert "covered_topics" in context["rolling_summary"]
    assert context["completed_rounds"][0]["round_type"] == "resume"
    manager_view = service._role_view(  # noqa: SLF001 - focused role-filter contract test.
        store.snapshot.rolling_summary.model_dump(),  # type: ignore[union-attr]
        "manager",
    )
    assert "covered_topics" not in manager_view
    assert "strengths" in manager_view


def test_prompt_context_compresses_answer_that_just_left_recent_window() -> None:
    store = MemoryStore()
    service = _service(store)
    repository = service.repository
    repository.qa_records = repository.qa_records[:5]  # type: ignore[attr-defined]
    service.sync(3, 10)
    repository.qa_records.append(_qa_records()[5])  # type: ignore[attr-defined]
    history = [
        {
            "id": qa.id,
            "question": qa.question,
            "question_type": qa.question_type,
            "question_kind": qa.question_kind,
            "answer": qa.answer,
        }
        for qa in repository.qa_records  # type: ignore[attr-defined]
    ]

    context, generation_history, _ = service.prompt_context(
        user_id=3,
        interview=repository.interview,  # type: ignore[attr-defined]
        round_record=repository.rounds[1],  # type: ignore[attr-defined]
        qa_history=history,
    )

    assert [item["id"] for item in context["recent_qa"]] == [2, 3, 4, 5, 6]
    assert any("Q1 " in item for item in context["rolling_summary"]["key_facts"])
    assert "answer" not in generation_history[0]


def test_sync_from_records_checks_revision_before_rebuilding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore()
    service = _service(store)
    repository = service.repository
    scores = service.evaluation_service.question_scores_by_id(10)  # type: ignore[union-attr]
    first = service.sync_from_records(
        3,
        repository.interview,  # type: ignore[attr-defined]
        rounds=repository.rounds,  # type: ignore[attr-defined]
        qa_records=repository.qa_records,  # type: ignore[attr-defined]
        score_by_id=scores,
    )
    monkeypatch.setattr(
        service,
        "_build_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cache hit must not rebuild the snapshot")
        ),
    )

    second = service.sync_from_records(
        3,
        repository.interview,  # type: ignore[attr-defined]
        rounds=repository.rounds,  # type: ignore[attr-defined]
        qa_records=repository.qa_records,  # type: ignore[attr-defined]
        score_by_id=scores,
    )

    assert first.status == "recovered"
    assert second.source == "redis"


def test_redis_failure_uses_mysql_snapshot_without_blocking_prompt() -> None:
    service = _service(FailingStore())
    repository = service.repository
    history = [
        {"id": qa.id, "question": qa.question, "answer": qa.answer}
        for qa in repository.qa_records  # type: ignore[attr-defined]
    ]

    context, _, status = service.prompt_context(
        user_id=3,
        interview=repository.interview,  # type: ignore[attr-defined]
        round_record=repository.rounds[1],  # type: ignore[attr-defined]
        qa_history=history,
    )

    assert status.status == "degraded"
    assert status.source == "mysql"
    assert status.fallback_used is True
    assert context["recent_qa"]


def test_token_threshold_truncates_large_recent_answers() -> None:
    store = MemoryStore()
    service = _service(store, answer_size=3000)
    service.sync(3, 10)

    assert store.snapshot is not None
    assert store.snapshot.estimated_tokens < 7200
    assert any(item.answer_truncated for item in store.snapshot.recent_qa)


def test_delete_removes_only_redis_snapshot() -> None:
    store = MemoryStore()
    service = _service(store)
    service.sync(3, 10)

    status = service.delete(3, 10)

    assert status.status == "healthy"
    assert store.deleted is True
    assert service.repository.list_qa(10)
