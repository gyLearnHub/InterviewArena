from datetime import datetime
from importlib import import_module
from typing import Any

from pydantic import ValidationError

from app.prompts.loader import load_prompt
from app.repositories.evaluations import EvaluationRepository
from app.repositories.interviews import InterviewRepository
from app.schemas.memory import MemoryItem, MemorySummaryOutput
from app.services.memory_lifecycle import MemoryLifecycleService

PROMPT_VERSION = "memory-summary-v1"
MAX_TEXT_LENGTH = 900
FOCUSED_TEXT_LENGTH = 500


class MemorySummaryService:
    def __init__(
        self,
        *,
        interview_repository: InterviewRepository,
        evaluation_repository: EvaluationRepository,
        lifecycle_service: MemoryLifecycleService,
        llm_client: Any,
    ) -> None:
        self.interviews = interview_repository
        self.evaluations = evaluation_repository
        self.lifecycle = lifecycle_service
        self.llm_client = llm_client

    def summarize_interview(self, *, user_id: int, interview_id: int) -> dict[str, Any]:
        interview = self.interviews.get_interview_for_user(interview_id, user_id)
        if interview is None:
            raise ValueError("interview not found for user")
        resume = self.interviews.get_resume_for_user(interview.resume_id, user_id)
        if resume is None:
            raise ValueError("resume not found for user")
        payload = {
            "interview": {
                "id": interview.id,
                "target_position": interview.target_position,
                "job_description": _clip_text(interview.job_description),
                "selected_rounds": interview.selected_rounds,
            },
            "resume_summary": _compact_resume(resume.structured_data),
            "rounds": [_round_payload(item) for item in self.interviews.list_rounds(interview.id)],
            "qa_history": [_qa_payload(item) for item in self.interviews.list_qa(interview.id)],
            "evaluations": [
                _evaluation_payload(item)
                for item in self.evaluations.list_by_interview(interview.id)
                if item.status == "succeeded"
            ],
        }
        output = self._generate_summary(_json_safe(payload))
        created = 0
        collection_counts: dict[str, int] = {}
        for item in _all_items(output):
            item = _canonicalize_memory_item(item)
            if item.collection == "candidate_memories":
                target_user_id = user_id
            else:
                target_user_id = None
            self.lifecycle.upsert_memory(
                item=item,
                user_id=target_user_id,
                source_interview_id=interview.id,
                target_position=interview.target_position,
            )
            created += 1
            collection_counts[item.collection] = collection_counts.get(item.collection, 0) + 1
        _record_harness_event(
            user_id=user_id,
            interview_id=interview.id,
            event_type="memory_summary_written",
            payload={"created_or_updated": created, "collection_counts": collection_counts},
        )
        return {"created_or_updated": created}

    def _generate_summary(self, payload: dict[str, Any]) -> MemorySummaryOutput:
        try:
            result = self.llm_client.generate_json(load_prompt("memory_summary.md"), payload)
            output = MemorySummaryOutput.model_validate(result)
            if not _all_items(output) and _has_memory_evidence(payload):
                retry_result = self.llm_client.generate_json(
                    _focused_retry_prompt(load_prompt("memory_summary.md")),
                    _focused_payload(payload),
                )
                output = MemorySummaryOutput.model_validate(retry_result)
            if not output.candidate_memories and _has_candidate_evidence(payload):
                candidate_result = self.llm_client.generate_json(
                    _candidate_retry_prompt(load_prompt("memory_summary.md")),
                    _focused_payload(payload),
                )
                output = _merge_summary_outputs(
                    output,
                    MemorySummaryOutput.model_validate(candidate_result),
                )
            return output
        except ValidationError:
            raise
        except Exception:
            raise


def _all_items(output: MemorySummaryOutput) -> list[MemoryItem]:
    return [
        *output.candidate_memories,
        *output.interviewer_memories,
        *output.agent_memories,
    ]


def _canonicalize_memory_item(item: MemoryItem) -> MemoryItem:
    memory_type = _canonical_memory_type(item)
    if memory_type == item.memory_type:
        return item
    return item.model_copy(update={"memory_type": memory_type})


def _canonical_memory_type(item: MemoryItem) -> str:
    normalized = item.memory_type.strip().lower()
    if item.collection == "candidate_memories":
        mapping = {
            "weakness": "technical_weakness",
            "interview_weakness": "technical_weakness",
            "technical_issue": "technical_weakness",
            "answer_issue": "past_wrong_answer",
            "invalid_answer": "past_wrong_answer",
            "garbled_answer": "past_wrong_answer",
            "answer_quality": "past_wrong_answer",
            "profile": "resume_key_fact",
            "candidate_profile": "resume_key_fact",
        }
        return mapping.get(normalized, normalized)
    if item.collection == "agent_memories":
        mapping = {
            "behavior": "agent_behavior",
            "anomaly": "agent_anomaly",
            "issue": "agent_anomaly",
        }
        return mapping.get(normalized, normalized)
    return normalized


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _compact_resume(value: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "basic_info",
        "education",
        "work_experience",
        "project_experience",
        "skills",
        "certificates_awards",
    ]
    return {key: _compact_value(value.get(key)) for key in keys if key in value}


def _round_payload(round_record: Any) -> dict[str, Any]:
    return {
        "id": getattr(round_record, "id", None),
        "round_type": getattr(round_record, "round_type", None),
        "agent_type": getattr(round_record, "agent_type", None),
        "status": getattr(round_record, "status", None),
        "score": getattr(round_record, "score", None),
        "result": getattr(round_record, "result", None),
        "summary": _compact_value(getattr(round_record, "summary", None)),
    }


def _qa_payload(qa: Any) -> dict[str, Any]:
    return {
        "id": getattr(qa, "id", None),
        "round_id": getattr(qa, "round_id", None),
        "sequence": getattr(qa, "sequence", None),
        "question_type": getattr(qa, "question_type", None),
        "question_kind": getattr(qa, "question_kind", None),
        "parent_question_id": getattr(qa, "parent_question_id", None),
        "question": _clip_text(getattr(qa, "question", None)),
        "answer": _clip_text(getattr(qa, "answer", None)),
    }


def _evaluation_payload(record: Any) -> dict[str, Any]:
    return {
        "id": getattr(record, "id", None),
        "evaluation_type": getattr(record, "evaluation_type", None),
        "evaluation_key": getattr(record, "evaluation_key", None),
        "round_id": getattr(record, "round_id", None),
        "question_id": getattr(record, "question_id", None),
        "total_score": getattr(record, "total_score", None),
        "evidence": [_clip_text(item) for item in getattr(record, "evidence", [])[:8]],
        "dimension_scores": _compact_value(getattr(record, "dimension_scores", None)),
        "result": _compact_value(getattr(record, "result", None)),
    }


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _clip_text(str(value))
    if isinstance(value, str):
        return _clip_text(value)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if item is None:
                continue
            compact[str(key)] = _compact_value(item, depth=depth + 1)
        return compact
    if isinstance(value, list):
        return [_compact_value(item, depth=depth + 1) for item in value[:12]]
    return value


def _clip_text(value: Any, limit: int = MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _has_memory_evidence(payload: dict[str, Any]) -> bool:
    for item in payload.get("evaluations", []):
        if not isinstance(item, dict):
            continue
        if item.get("evidence") or item.get("result"):
            return True
        score = item.get("total_score")
        if isinstance(score, (int, float)) and score < 60:
            return True
    for item in payload.get("rounds", []):
        if not isinstance(item, dict):
            continue
        if item.get("result") == "failed":
            return True
        score = item.get("score")
        if isinstance(score, (int, float)) and score < 60:
            return True
    for item in payload.get("qa_history", []):
        if isinstance(item, dict) and item.get("question") and item.get("answer"):
            return True
    return False


def _has_candidate_evidence(payload: dict[str, Any]) -> bool:
    for item in payload.get("evaluations", []):
        if not isinstance(item, dict):
            continue
        if item.get("evaluation_type") != "question":
            continue
        score = item.get("total_score")
        evidence = " ".join(str(value) for value in item.get("evidence", []))
        if isinstance(score, (int, float)) and score < 60:
            return True
        if any(keyword in evidence for keyword in ["回答", "无关", "不可解析", "缺少", "不足"]):
            return True
    for item in payload.get("qa_history", []):
        if isinstance(item, dict) and item.get("question") and item.get("answer"):
            return True
    return False


def _focused_payload(payload: dict[str, Any]) -> dict[str, Any]:
    evaluations = [
        _focused_evaluation(item)
        for item in payload.get("evaluations", [])
        if isinstance(item, dict) and _is_informative_evaluation(item)
    ]
    rounds = [
        _focused_round(item)
        for item in payload.get("rounds", [])
        if isinstance(item, dict) and _is_informative_round(item)
    ]
    qa_by_id = {
        item.get("id"): _focused_qa(item)
        for item in payload.get("qa_history", [])
        if isinstance(item, dict) and item.get("id") is not None
    }
    linked_question_ids = {
        item.get("question_id")
        for item in evaluations
        if item.get("question_id") is not None
    }
    qa = [qa_by_id[item] for item in linked_question_ids if item in qa_by_id]
    if not qa:
        qa = [
            _focused_qa(item)
            for item in payload.get("qa_history", [])[:8]
            if isinstance(item, dict)
        ]
    return {
        "generation_goal": (
            "从失败轮次、问题评估证据和问答中提取可跨会话复用的长期记忆。"
            "如果问题级证据显示回答无关、不可解析或缺少技术细节，应形成候选人薄弱点记忆。"
        ),
        "interview": payload.get("interview", {}),
        "rounds": rounds[:8],
        "question_evaluations": evaluations[:16],
        "qa_evidence": qa[:12],
    }


def _focused_evaluation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluation_type": item.get("evaluation_type"),
        "round_id": item.get("round_id"),
        "question_id": item.get("question_id"),
        "total_score": item.get("total_score"),
        "evidence": [
            _clip_text(value, FOCUSED_TEXT_LENGTH)
            for value in item.get("evidence", [])[:5]
        ],
        "result": _compact_value(item.get("result")),
    }


def _focused_round(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "round_type": item.get("round_type"),
        "agent_type": item.get("agent_type"),
        "score": item.get("score"),
        "result": item.get("result"),
        "main_issues": _compact_value((item.get("summary") or {}).get("main_issues")),
        "evidence": _compact_value((item.get("summary") or {}).get("evidence")),
    }


def _focused_qa(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "round_id": item.get("round_id"),
        "sequence": item.get("sequence"),
        "question": _clip_text(item.get("question"), FOCUSED_TEXT_LENGTH),
        "answer": _clip_text(item.get("answer"), FOCUSED_TEXT_LENGTH),
    }


def _is_informative_evaluation(item: dict[str, Any]) -> bool:
    score = item.get("total_score")
    if isinstance(score, (int, float)) and score < 60:
        return True
    return bool(item.get("evidence") or item.get("result"))


def _is_informative_round(item: dict[str, Any]) -> bool:
    score = item.get("score")
    if isinstance(score, (int, float)) and score < 60:
        return True
    return item.get("result") == "failed"


def _focused_retry_prompt(base_prompt: str) -> str:
    return (
        f"{base_prompt}\n\n"
        "二次检查要求：上一轮摘要返回了空数组，但输入中存在失败轮次、问题评估或问答证据。"
        "请基于这些证据重新提取长期记忆。"
        "只要证据显示候选人回答与问题无关、不可解析、缺少关键技术细节或持续低分，"
        "candidate_memories 至少返回 1 条薄弱点或改进趋势记忆。"
        "不要编造未出现的项目事实；content 必须引用概括后的证据，不要复制完整原始回答。"
    )


def _candidate_retry_prompt(base_prompt: str) -> str:
    return (
        f"{base_prompt}\n\n"
        "候选人记忆补充要求：上一轮没有返回 candidate_memories，"
        "但输入中存在问题级低分、回答与问题无关、不可解析或缺少有效技术信息的证据。"
        "这些属于候选人在本次面试中的表现证据，应归入 candidate_memories，"
        "不要只归入 agent_memories。"
        "请至少返回 1 条 candidate_memories，除非你能从证据中确认所有问题级评估都与候选人表现无关。"
        "interviewer_memories 和 agent_memories 可以为空数组。"
    )


def _merge_summary_outputs(
    primary: MemorySummaryOutput,
    supplement: MemorySummaryOutput,
) -> MemorySummaryOutput:
    return MemorySummaryOutput(
        candidate_memories=[*primary.candidate_memories, *supplement.candidate_memories],
        interviewer_memories=[*primary.interviewer_memories, *supplement.interviewer_memories],
        agent_memories=[*primary.agent_memories, *supplement.agent_memories],
    )


def _record_harness_event(
    *,
    user_id: int,
    interview_id: int,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    try:
        module = import_module("app.harness.execution")
    except Exception:
        return
    service = None
    for factory_name in ("get_harness_execution_service", "get_execution_service"):
        factory = getattr(module, factory_name, None)
        if callable(factory):
            service = factory()
            break
    if service is None:
        service = getattr(module, "harness_execution_service", None)
    if service is None:
        return
    event_payload = {
        "user_id": user_id,
        "interview_id": interview_id,
        "round_id": None,
        "node_type": "memory_write_tracker",
        "event_type": event_type,
        "payload": payload,
    }
    for method_name in ("record_event", "create_event", "trace_event"):
        method = getattr(service, method_name, None)
        if callable(method):
            method(**event_payload)
            return
