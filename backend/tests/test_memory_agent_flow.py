from datetime import datetime
from typing import Any

from app.schemas.memory import MemoryRetrievalResult, RetrievedMemory
from app.services.interviews import InterviewService
from test_interview import FakeInterviewRepository


def test_each_round_agent_receives_only_stage_appropriate_effective_memories() -> None:
    expected_types = {
        "resume": "project_highlight",
        "technical": "technical_weakness",
        "manager": "collaboration",
        "hr": "career_plan",
    }

    for round_type, memory_type in expected_types.items():
        repository = FakeInterviewRepository()
        repository.add_resume(resume_id=1, user_id=7)
        llm = _RecordingLLM()
        memory_service = _MemoryRetrievalService(memory_type)
        service = InterviewService(
            repository=repository,  # type: ignore[arg-type]
            llm_client=llm,  # type: ignore[arg-type]
            memory_retrieval_service=memory_service,  # type: ignore[arg-type]
            preferences_repository=_Preferences(True),  # type: ignore[arg-type]
        )
        interview = service.create_interview(
            user_id=7,
            resume_id=1,
            target_position="backend engineer",
            selected_rounds=[round_type],
        )
        round_record = repository.list_rounds(interview.id)[0]

        question = service.start_round(7, interview.id, round_record.id)

        assert question.round_id == round_record.id
        assert memory_service.requests[-1].agent_type == round_type
        assert memory_service.requests[-1].usage_scene == "new_question"
        assert memory_service.requests[-1].user_id == 7
        effective_memories = llm.calls[-1]["resume"]["_effective_memories"]
        assert [memory["memory_type"] for memory in effective_memories] == [memory_type]


def test_memory_disabled_passes_disabled_flag_and_does_not_break_question_flow() -> None:
    repository = FakeInterviewRepository()
    repository.add_resume(resume_id=1, user_id=7)
    llm = _RecordingLLM()
    memory_service = _MemoryRetrievalService("technical_weakness")
    service = InterviewService(
        repository=repository,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        memory_retrieval_service=memory_service,  # type: ignore[arg-type]
        preferences_repository=_Preferences(False),  # type: ignore[arg-type]
    )
    interview = service.create_interview(7, 1, "backend engineer", selected_rounds=["technical"])
    round_record = repository.list_rounds(interview.id)[0]

    question = service.start_round(7, interview.id, round_record.id)

    assert question.question
    assert memory_service.requests[-1].memory_enabled is False


def test_memory_recall_exception_does_not_interrupt_interview_flow() -> None:
    repository = FakeInterviewRepository()
    repository.add_resume(resume_id=1, user_id=7)
    llm = _RecordingLLM()
    service = InterviewService(
        repository=repository,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        memory_retrieval_service=_FailingMemoryRetrievalService(),  # type: ignore[arg-type]
        preferences_repository=_Preferences(True),  # type: ignore[arg-type]
    )
    interview = service.create_interview(7, 1, "backend engineer", selected_rounds=["resume"])
    round_record = repository.list_rounds(interview.id)[0]

    question = service.start_round(7, interview.id, round_record.id)

    assert question.question
    assert llm.calls[-1]["resume"]["_effective_memories"] == []


class _RecordingLLM:
    model_name = "recording-llm"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "resume": resume,
                "target_position": target_position,
                "qa_history": qa_history,
                "previous_answer": previous_answer,
                "system_prompt": system_prompt,
            }
        )
        return {"question_type": "memory_probe", "question": "Explain a relevant case."}


class _MemoryRetrievalService:
    def __init__(self, memory_type: str) -> None:
        self.memory_type = memory_type
        self.requests: list[Any] = []

    def retrieve(self, request: Any) -> MemoryRetrievalResult:
        self.requests.append(request)
        if not request.memory_enabled:
            return MemoryRetrievalResult(request_id="req-disabled", memories=[])
        return MemoryRetrievalResult(
            request_id="req-ok",
            memories=[
                RetrievedMemory(
                    collection="candidate_memories",
                    memory_id=1,
                    memory_type=self.memory_type,
                    title=self.memory_type,
                    content=f"content for {self.memory_type}",
                    confidence=0.9,
                    score=0.95,
                    created_at=datetime(2026, 6, 18, 9, 0, 0),
                )
            ],
        )


class _FailingMemoryRetrievalService:
    def retrieve(self, request: Any) -> MemoryRetrievalResult:
        raise RuntimeError("retrieval unavailable")


class _Preferences:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def get_memory_enabled(self, user_id: int) -> bool:
        return self.enabled
