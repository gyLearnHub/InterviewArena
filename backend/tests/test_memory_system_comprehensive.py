from datetime import datetime
from typing import Any

from app.repositories.memories import MemoryRecord
from app.schemas.memory import MemoryItem, MemoryRetrievalRequest
from app.services.memory_lifecycle import MemoryLifecycleService
from app.services.memory_query_rewriter import MemoryQueryRewriter
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.memory_summary import MemorySummaryService
from app.services.memory_usage_policy import MemoryUsagePolicy


def test_memory_disabled_stops_candidate_recall_but_keeps_flow_degraded() -> None:
    repository = _MemoryRepository(
        [
            _memory(1, "candidate knows Python concurrency", "technical_weakness", user_id=7),
            _memory(
                2,
                "system technical interviewer rubric",
                "technical_trend",
                collection="interviewer_memories",
                agent_type="technical",
                user_id=None,
            ),
        ]
    )
    vector = _RecordingVectorIndex([])
    service = MemoryRetrievalService(
        memory_repository=repository,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
        reranker=_KeywordReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=7,
            memory_enabled=False,
            usage_scene="new_question",
            intent="ask a technical question",
            query_text="Python concurrency",
            agent_type="technical",
        )
    )

    assert all(memory.collection != "candidate_memories" for memory in result.memories)
    assert result.memories == []
    assert repository.candidate_calls == []
    assert vector.calls == []


def test_enabled_recall_with_empty_memory_store_skips_vector_search() -> None:
    audit = _RecordingAuditRepository()
    repository = _MemoryRepository([])
    vector = _RecordingVectorIndex([])
    service = MemoryRetrievalService(
        memory_repository=repository,  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
        reranker=_KeywordReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=7,
            memory_enabled=True,
            usage_scene="new_question",
            intent="ask the first technical question",
            query_text="Python concurrency",
            agent_type="technical",
        )
    )

    assert result.memories == []
    assert repository.candidate_calls
    assert vector.calls == []
    assert audit.calls[-1]["candidate_memory_ids"] == []
    assert audit.calls[-1]["injected_memory_ids"] == []
    assert audit.calls[-1]["timings"]["candidate_count"] == 0


def test_low_relevance_memories_are_filtered_and_audited() -> None:
    audit = _RecordingAuditRepository()
    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository(
            [_memory(1, "salary negotiation and office location", "career_plan", confidence=0.95)]
        ),  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=_RecordingVectorIndex([]),  # type: ignore[arg-type]
        reranker=_KeywordReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=7,
            usage_scene="new_question",
            intent="ask about distributed transaction isolation",
            query_text="distributed transaction isolation",
            agent_type="technical",
            memory_types=["career_plan"],
            collections=["candidate_memories"],
            top_k=5,
        )
    )

    assert result.memories == []
    assert audit.calls[-1]["candidate_memory_ids"] == ["candidate_memories:1"]
    assert audit.calls[-1]["injected_memory_ids"] == []
    assert audit.calls[-1]["timings"]["filtered_count"] == 1


def test_hybrid_retrieval_deduplicates_reranks_and_records_metrics() -> None:
    audit = _RecordingAuditRepository()
    repository = _MemoryRepository(
        [
            _memory(1, "Python concurrency lock queue project", "technical_weakness"),
            _memory(2, "Python syntax basics", "technical_weakness"),
        ]
    )
    vector = _RecordingVectorIndex([("candidate_memories", 2, 0.2)])
    service = MemoryRetrievalService(
        memory_repository=repository,  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
        reranker=_KeywordReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=7,
            usage_scene="new_question",
            intent="ask about Python concurrency",
            query_text="Python concurrency project",
            agent_type="technical",
            collections=["candidate_memories"],
            top_k=5,
        )
    )

    ids = [memory.memory_id for memory in result.memories]
    assert ids[0] == 1
    assert ids == list(dict.fromkeys(ids))
    assert repository.candidate_calls[-1]["user_id"] == 7
    assert vector.calls[-1]["top_k"] == 15
    assert result.memories[0].score >= result.memories[-1].score
    timings = audit.calls[-1]["timings"]
    assert {"rewrite_ms", "initial_recall_ms", "reranker_ms", "total_ms"} <= set(timings)
    assert timings["candidate_count"] == 2
    assert timings["injected_count"] == len(result.memories)
    assert audit.calls[-1]["rewritten_query"] == "Python concurrency project"


def test_reranker_failure_degrades_to_initial_sort_without_breaking_recall() -> None:
    audit = _RecordingAuditRepository()
    service = MemoryRetrievalService(
        memory_repository=_MemoryRepository(
            [_memory(1, "Python concurrency project", "technical_weakness")]
        ),  # type: ignore[arg-type]
        audit_repository=audit,  # type: ignore[arg-type]
        vector_index=_RecordingVectorIndex([]),  # type: ignore[arg-type]
        reranker=_FailingReranker(),
    )

    result = service.retrieve(
        MemoryRetrievalRequest(
            user_id=7,
            usage_scene="new_question",
            intent="ask about Python concurrency",
            query_text="Python concurrency",
            agent_type="technical",
            collections=["candidate_memories"],
        )
    )

    assert [memory.memory_id for memory in result.memories] == [1]
    assert result.fallback_reason == "reranker_fallback"
    assert audit.calls[-1]["timings"]["degradation_count"] == 1


def test_agent_memory_type_policy_and_dynamic_top_k_are_stage_aware() -> None:
    policy = MemoryUsagePolicy()

    assert {
        "resume_key_fact",
        "project_highlight",
        "experience_authenticity",
        "project_follow_up",
        "unresolved_question",
        "scoring_rubric",
        "agent_behavior",
    }.issubset(policy.allowed_memory_types(_request(agent_type="resume")))
    assert "technical_weakness" in policy.allowed_memory_types(_request(agent_type="technical"))
    assert "collaboration" in policy.allowed_memory_types(_request(agent_type="manager"))
    assert "career_plan" in policy.allowed_memory_types(_request(agent_type="hr"))
    assert policy.top_k(_request(usage_scene="new_question")) == 4
    assert policy.top_k(_request(usage_scene="feedback")) == 6
    assert policy.top_k(_request(top_k=99)) == 10
    assert policy.top_k(_request(top_k=0)) == 1


def test_query_rewriter_uses_llm_json_and_template_fallbacks() -> None:
    request = _request(intent="find weak points before a follow up", agent_type="technical")

    rewriter = MemoryQueryRewriter(
        _LLM({"query_text": "structured technical weak points"})
    )
    query, fallback = rewriter.rewrite(request)
    assert query == "structured technical weak points"
    assert fallback is None

    fallback_query, fallback_reason = MemoryQueryRewriter(_LLM(RuntimeError("timeout"))).rewrite(
        request
    )
    assert "find weak points before a follow up" in fallback_query
    assert fallback_reason == "RuntimeError"

    invalid_query, invalid_reason = MemoryQueryRewriter(_LLM({"keywords": ["missing"]})).rewrite(
        request
    )
    assert "technical" in invalid_query
    assert invalid_reason == "template_rewriter"


def test_memory_summary_writes_valid_items_and_ignores_empty_output() -> None:
    lifecycle = _RecordingLifecycle()
    service = MemorySummaryService(
        interview_repository=_SummaryInterviewRepository(),
        evaluation_repository=_SummaryEvaluationRepository(),
        lifecycle_service=lifecycle,  # type: ignore[arg-type]
        llm_client=_LLM(
            {
                "candidate_memories": [
                    {
                        "collection": "candidate_memories",
                        "memory_type": "technical_weakness",
                        "title": "Python concurrency weakness",
                        "content": "Needs practice with locks and queues.",
                        "confidence": 0.82,
                    }
                ],
                "interviewer_memories": [],
                "agent_memories": [],
            }
        ),
    )

    result = service.summarize_interview(user_id=7, interview_id=100)

    assert result == {"created_or_updated": 1}
    assert lifecycle.upserts[0]["user_id"] == 7
    assert lifecycle.upserts[0]["source_interview_id"] == 100
    assert lifecycle.upserts[0]["item"].memory_type == "technical_weakness"

    empty_lifecycle = _RecordingLifecycle()
    empty_service = MemorySummaryService(
        interview_repository=_SummaryInterviewRepository(),
        evaluation_repository=_SummaryEvaluationRepository(),
        lifecycle_service=empty_lifecycle,  # type: ignore[arg-type]
        llm_client=_LLM(
            {"candidate_memories": [], "interviewer_memories": [], "agent_memories": []}
        ),
    )
    assert empty_service.summarize_interview(user_id=7, interview_id=100) == {
        "created_or_updated": 0
    }
    assert empty_lifecycle.upserts == []


def test_duplicate_memory_upsert_merges_existing_record_instead_of_inserting() -> None:
    existing = _memory(1, "Needs practice with old lock examples", "technical_weakness")
    repository = _LifecycleRepository(existing)
    service = MemoryLifecycleService(
        repository,  # type: ignore[arg-type]
        _RecordingIndexService(),  # type: ignore[arg-type]
    )

    updated = service.upsert_memory(
        item=MemoryItem(
            collection="candidate_memories",
            memory_type="technical_weakness",
            title="Python concurrency weakness",
            content="Needs practice with locks and queues.",
            confidence=0.9,
            structured_data={"evidence": ["new answer"]},
        ),
        user_id=7,
        source_interview_id=100,
        target_position="backend engineer",
    )

    assert updated.id == 1
    assert repository.inserted == []
    assert repository.updated[0]["record"].id == 1
    assert repository.updated[0]["structured_data"]["occurrences"] == 2
    assert "new answer" in repository.updated[0]["structured_data"]["evidence"]


class _MemoryRepository:
    def __init__(self, memories: list[MemoryRecord]) -> None:
        self.memories = memories
        self.candidate_calls: list[dict[str, Any]] = []
        self.system_calls: list[dict[str, Any]] = []

    def list_candidate_memories(
        self,
        *,
        user_id: int,
        memory_types: list[str] | None = None,
        include_pending_index: bool = False,
    ) -> list[MemoryRecord]:
        self.candidate_calls.append(
            {
                "user_id": user_id,
                "memory_types": memory_types,
                "include_pending_index": include_pending_index,
            }
        )
        allowed = set(memory_types or [])
        return [
            memory
            for memory in self.memories
            if memory.collection == "candidate_memories"
            and memory.user_id == user_id
            and (not allowed or memory.memory_type in allowed)
        ]

    def list_system_memories(
        self,
        *,
        collection: str,
        agent_type: str | None = None,
        memory_types: list[str] | None = None,
    ) -> list[MemoryRecord]:
        self.system_calls.append(
            {"collection": collection, "agent_type": agent_type, "memory_types": memory_types}
        )
        allowed = set(memory_types or [])
        return [
            memory
            for memory in self.memories
            if memory.collection == collection
            and (agent_type is None or memory.agent_type == agent_type)
            and (not allowed or memory.memory_type in allowed)
        ]

    def get(self, collection: str, memory_id: int) -> MemoryRecord | None:
        return next(
            (
                memory
                for memory in self.memories
                if memory.collection == collection and memory.id == memory_id
            ),
            None,
        )


class _RecordingVectorIndex:
    def __init__(self, hits: list[tuple[str, int, float]]) -> None:
        self.hits = hits
        self.calls: list[dict[str, Any]] = []

    def search(self, **kwargs: Any) -> Any:
        from app.services.memory_index import VectorSearchHit, VectorSearchResult

        self.calls.append(kwargs)
        return VectorSearchResult(
            hits=[
                VectorSearchHit(
                    collection=collection,
                    memory_id=memory_id,
                    score=score,
                    metadata={"memory_id": memory_id},
                )
                for collection, memory_id, score in self.hits
            ]
        )


class _KeywordReranker:
    version = "keyword-test"

    def score(self, query: str, content: str, confidence: float = 0.0) -> float:
        query_terms = set(query.lower().split())
        content_terms = set(content.lower().split())
        if not query_terms:
            return 0.0
        return len(query_terms & content_terms) / len(query_terms)


class _FailingReranker:
    version = "failing-test"

    def score(self, query: str, content: str, confidence: float = 0.0) -> float:
        raise RuntimeError("reranker unavailable")


class _RecordingAuditRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _LLM:
    model_name = "mock-llm"

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"system_prompt": system_prompt, "user_payload": user_payload})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _RecordingLifecycle:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []

    def upsert_memory(self, **kwargs: Any) -> MemoryRecord:
        self.upserts.append(kwargs)
        return _memory(99, kwargs["item"].content, kwargs["item"].memory_type)


class _SummaryInterviewRepository:
    def get_interview_for_user(self, interview_id: int, user_id: int) -> Any:
        return _Obj(
            id=interview_id,
            user_id=user_id,
            resume_id=10,
            target_position="backend engineer",
            job_description="build APIs",
            selected_rounds=["resume", "technical", "manager", "hr"],
        )

    def get_resume_for_user(self, resume_id: int, user_id: int) -> Any:
        return _Obj(id=resume_id, user_id=user_id, structured_data={"skills": ["Python"]})

    def list_rounds(self, interview_id: int) -> list[Any]:
        return [_Obj(id=1, round_type="technical", status="completed")]

    def list_qa(self, interview_id: int) -> list[Any]:
        return [
            _Obj(
                id=1,
                question="Explain locks",
                answer="I am not confident with lock ordering",
                round_id=1,
            )
        ]


class _SummaryEvaluationRepository:
    def list_by_interview(self, interview_id: int) -> list[Any]:
        return [_Obj(status="succeeded", result={"issues": ["lock ordering"]})]


class _LifecycleRepository:
    def __init__(self, existing: MemoryRecord) -> None:
        self.existing = existing
        self.inserted: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []

    def find_similar(self, **kwargs: Any) -> MemoryRecord | None:
        return self.existing

    def insert_memory(self, **kwargs: Any) -> MemoryRecord:
        self.inserted.append(kwargs)
        return _memory(2, kwargs["content"], kwargs["memory_type"])

    def update_existing_memory(self, **kwargs: Any) -> MemoryRecord:
        self.updated.append(kwargs)
        return MemoryRecord(
            **{
                **kwargs["record"].__dict__,
                "content": kwargs["content"],
                "structured_data": kwargs["structured_data"],
                "tokens": kwargs["tokens"],
                "confidence": kwargs["confidence"],
                "status": kwargs["status"],
                "index_status": kwargs["index_status"],
                "version": kwargs["record"].version + 1,
            }
        )


class _RecordingIndexService:
    def __init__(self) -> None:
        self.indexed: list[MemoryRecord] = []
        self.deleted: list[tuple[str, int]] = []

    def index_memory(self, memory: MemoryRecord) -> None:
        self.indexed.append(memory)

    def delete_memory_vectors(self, collection: str, memory_id: int) -> None:
        self.deleted.append((collection, memory_id))


class _Obj:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


def _request(
    *,
    usage_scene: str = "new_question",
    intent: str = "find relevant memory",
    agent_type: str | None = "technical",
    top_k: int | None = None,
) -> MemoryRetrievalRequest:
    return MemoryRetrievalRequest(
        user_id=7,
        usage_scene=usage_scene,  # type: ignore[arg-type]
        intent=intent,
        agent_type=agent_type,
        top_k=top_k,
    )


def _memory(
    memory_id: int,
    content: str,
    memory_type: str,
    *,
    collection: str = "candidate_memories",
    user_id: int | None = 7,
    agent_type: str | None = None,
    confidence: float = 0.9,
) -> MemoryRecord:
    return MemoryRecord(
        id=memory_id,
        collection=collection,
        memory_type=memory_type,
        title=f"memory {memory_id}",
        content=content,
        structured_data={"evidence": ["old answer"]},
        tokens=content.lower().split(),
        confidence=confidence,
        status="active",
        index_status="indexed",
        source_interview_id=100,
        source_round_id=10,
        version=1,
        created_at=datetime(2026, 6, 18, 9, 0, 0),
        updated_at=None,
        user_id=user_id,
        agent_type=agent_type,
    )
