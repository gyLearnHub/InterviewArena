from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Literal

from app.core.config import Settings, get_settings
from app.harness.events import record_harness_event
from app.repositories.interviews import (
    InterviewRecord,
    InterviewRepository,
    InterviewRoundRecord,
    QARecord,
)
from app.schemas.short_term_memory import (
    CompletedRoundMemory,
    RollingShortTermSummary,
    ShortTermMemorySnapshot,
    ShortTermMemoryStatus,
    ShortTermQA,
)
from app.services.evaluations import EvaluationSchedulerService
from app.services.short_term_memory_store import (
    RedisShortTermMemoryStore,
    ShortTermMemoryStoreError,
    ShortTermMemoryVersionConflict,
)

LOGGER = logging.getLogger(__name__)
FINISHED_ROUND_STATUSES = {"completed", "finished_early"}


class ShortTermMemoryService:
    def __init__(
        self,
        repository: InterviewRepository,
        store: RedisShortTermMemoryStore,
        evaluation_service: EvaluationSchedulerService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.store = store
        self.evaluation_service = evaluation_service
        self.settings = settings or get_settings()

    def sync(self, user_id: int, interview_id: int) -> ShortTermMemoryStatus:
        interview = self.repository.get_interview_for_user(interview_id, user_id)
        if interview is None:
            return self._status("degraded", "mysql", fallback_used=True)
        _, status = self._sync_snapshot(user_id, interview)
        return status

    def sync_from_records(
        self,
        user_id: int,
        interview: InterviewRecord,
        *,
        rounds: list[InterviewRoundRecord],
        qa_records: list[QARecord],
        score_by_id: dict[int, dict[str, Any]],
    ) -> ShortTermMemoryStatus:
        _, status = self._sync_snapshot(
            user_id,
            interview,
            rounds=rounds,
            qa_records=qa_records,
            score_by_id=score_by_id,
        )
        return status

    def _sync_snapshot(
        self,
        user_id: int,
        interview: InterviewRecord,
        *,
        rounds: list[InterviewRoundRecord] | None = None,
        qa_records: list[QARecord] | None = None,
        score_by_id: dict[int, dict[str, Any]] | None = None,
    ) -> tuple[ShortTermMemorySnapshot, ShortTermMemoryStatus]:
        loaded_rounds = rounds if rounds is not None else self.repository.list_rounds(interview.id)
        loaded_qa = qa_records if qa_records is not None else self.repository.list_qa(interview.id)
        source_revision = self._source_revision(interview, loaded_qa, loaded_rounds)
        expected_version: int | None = None
        try:
            existing = self.store.load(user_id, interview.id)
            if existing is not None:
                expected_version = existing.version
                if existing.source_revision == source_revision:
                    self._event(user_id, interview, None, "short_memory_cache_hit")
                    return existing, self._snapshot_status(existing, "redis")
            else:
                self._event(user_id, interview, None, "short_memory_cache_miss")
            snapshot = self._build_snapshot(
                user_id,
                interview,
                rounds=loaded_rounds,
                qa_records=loaded_qa,
                score_by_id=score_by_id,
                source_revision=source_revision,
            )
            stored = self.store.compare_and_set(
                snapshot,
                expected_version=expected_version,
            )
            event = (
                "short_memory_compressed"
                if stored.compression_count > 0
                else "short_memory_rebuilt"
            )
            self._event(user_id, interview, None, event)
            status = self._snapshot_status(
                stored,
                "mysql" if existing is None else "redis",
                recovered=existing is None,
            )
            return stored, status
        except ShortTermMemoryVersionConflict:
            self._event(user_id, interview, None, "short_memory_version_conflict")
            try:
                latest = self.store.load(user_id, interview.id)
                if latest is not None and latest.source_revision == source_revision:
                    return latest, self._snapshot_status(latest, "redis")
                snapshot = self._build_snapshot(
                    user_id,
                    interview,
                    rounds=loaded_rounds,
                    qa_records=loaded_qa,
                    score_by_id=score_by_id,
                    source_revision=source_revision,
                )
                stored = self.store.compare_and_set(
                    snapshot,
                    expected_version=latest.version if latest is not None else None,
                )
                return stored, self._snapshot_status(stored, "redis")
            except (ShortTermMemoryStoreError, ShortTermMemoryVersionConflict):
                snapshot = self._build_snapshot(
                    user_id,
                    interview,
                    rounds=loaded_rounds,
                    qa_records=loaded_qa,
                    score_by_id=score_by_id,
                    source_revision=source_revision,
                )
                return snapshot, self._degraded_status(user_id, interview)
        except ShortTermMemoryStoreError:
            snapshot = self._build_snapshot(
                user_id,
                interview,
                rounds=loaded_rounds,
                qa_records=loaded_qa,
                score_by_id=score_by_id,
                source_revision=source_revision,
            )
            return snapshot, self._degraded_status(user_id, interview)

    def prompt_context(
        self,
        *,
        user_id: int,
        interview: InterviewRecord,
        round_record: InterviewRoundRecord,
        qa_history: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], ShortTermMemoryStatus]:
        snapshot, status = self._sync_snapshot(user_id, interview)

        merged_recent = self._merge_recent(snapshot, round_record, qa_history)
        recent_ids = {item["id"] for item in merged_recent if isinstance(item.get("id"), int)}
        generation_history: list[dict[str, Any]] = []
        for item in qa_history:
            copied = dict(item)
            if copied.get("id") not in recent_ids:
                copied.pop("answer", None)
                copied.pop("evaluation_follow_up", None)
            generation_history.append(copied)

        context = {
            "schema_version": snapshot.schema_version,
            "current_round": round_record.round_type,
            "recent_qa": merged_recent,
            "rolling_summary": self._role_view(
                snapshot.rolling_summary.model_dump(),
                round_record.round_type,
            ),
            "completed_rounds": [
                item.model_dump()
                for item in snapshot.completed_rounds
                if item.round_type != round_record.round_type
            ],
            "estimated_tokens": snapshot.estimated_tokens,
            "compressed": status.compressed,
        }
        return context, generation_history, status

    def delete(self, user_id: int, interview_id: int) -> ShortTermMemoryStatus:
        interview = self.repository.get_interview_for_user(interview_id, user_id)
        try:
            self.store.delete(user_id, interview_id)
            if interview is not None:
                self._event(user_id, interview, None, "short_memory_deleted")
            return self._status("healthy", "redis")
        except ShortTermMemoryStoreError:
            if interview is not None:
                return self._degraded_status(user_id, interview)
            return self._status("degraded", "mysql", fallback_used=True)

    def _build_snapshot(
        self,
        user_id: int,
        interview: InterviewRecord,
        *,
        rounds: list[InterviewRoundRecord],
        qa_records: list[QARecord],
        score_by_id: dict[int, dict[str, Any]] | None = None,
        source_revision: str | None = None,
    ) -> ShortTermMemorySnapshot:
        loaded_scores = (
            score_by_id if score_by_id is not None else self._question_scores(interview.id)
        )
        round_by_id = {item.id: item for item in rounds}
        answered = [item for item in qa_records if (item.answer or "").strip()]
        recent_limit = self.settings.short_memory_recent_qa_limit
        older = answered[:-recent_limit]
        recent = answered[-recent_limit:]
        rolling = self._rolling_summary(older, loaded_scores)
        recent_payload = [
            self._qa_memory(
                item,
                round_by_id.get(item.round_id) if item.round_id is not None else None,
                loaded_scores.get(item.id),
            )
            for item in recent
        ]
        completed = [
            CompletedRoundMemory(
                round_id=item.id,
                round_type=item.round_type,
                status=item.status,
                summary=self._public_round_summary(item.summary or {}),
            )
            for item in rounds
            if item.status in FINISHED_ROUND_STATUSES and item.summary
        ]
        current_round = next(
            (item.round_type for item in rounds if item.status == "in_progress"),
            interview.current_round,
        )
        snapshot = ShortTermMemorySnapshot(
            user_id=user_id,
            interview_id=interview.id,
            current_round=current_round,
            source_revision=source_revision or self._source_revision(interview, qa_records, rounds),
            recent_qa=recent_payload,
            rolling_summary=rolling,
            completed_rounds=completed,
            compression_count=1 if older else 0,
            updated_at=datetime.utcnow(),
        )
        return self._fit_budget(snapshot)

    def _fit_budget(self, snapshot: ShortTermMemorySnapshot) -> ShortTermMemorySnapshot:
        budget = self.settings.short_memory_token_budget
        estimated = _estimate_tokens(snapshot.model_dump(mode="json"))
        truncated = False
        while estimated >= int(budget * 0.9):
            candidate = next(
                (item for item in snapshot.recent_qa if len(item.answer) > 600),
                None,
            )
            if candidate is None:
                break
            next_length = max(599, len(candidate.answer) // 2)
            if next_length >= len(candidate.answer):
                next_length = 599
            candidate.answer = f"{candidate.answer[:next_length]}…"
            candidate.answer_truncated = True
            truncated = True
            estimated = _estimate_tokens(snapshot.model_dump(mode="json"))
        snapshot.estimated_tokens = estimated
        if truncated and snapshot.compression_count == 0:
            snapshot.compression_count = 1
        return snapshot

    def _rolling_summary(
        self,
        qa_records: list[QARecord],
        score_by_id: dict[int, dict[str, Any]],
    ) -> RollingShortTermSummary:
        facts: list[str] = []
        strengths: list[str] = []
        weaknesses: list[str] = []
        topics: list[str] = []
        follow_ups: list[str] = []
        flags: list[str] = []
        evidence_ids: list[int] = []
        for qa in qa_records:
            answer = (qa.answer or "").strip()
            if answer:
                facts.append(f"Q{qa.id} {qa.question[:80]}：{answer[:180]}")
                evidence_ids.append(qa.id)
            if qa.question_type and qa.question_type not in topics:
                topics.append(qa.question_type)
            score = score_by_id.get(qa.id) or {}
            strengths.extend(_string_list(score.get("strengths")))
            issues = _string_list(score.get("issues"))
            weaknesses.extend(issues)
            direction = str(score.get("follow_up_direction") or "").strip()
            if score.get("should_follow_up") and direction:
                follow_ups.append(direction)
            flags.extend(
                item
                for item in issues
                if any(marker in item for marker in ("不一致", "矛盾", "冲突", "存疑"))
            )
        return RollingShortTermSummary(
            key_facts=_unique(facts, 12),
            strengths=_unique(strengths, 12),
            weaknesses=_unique(weaknesses, 12),
            covered_topics=_unique(topics, 20),
            pending_follow_ups=_unique(follow_ups, 10),
            consistency_flags=_unique(flags, 8),
            evidence_question_ids=evidence_ids[-20:],
        )

    def _qa_memory(
        self,
        qa: QARecord,
        round_record: InterviewRoundRecord | None,
        evaluation: dict[str, Any] | None,
    ) -> ShortTermQA:
        return ShortTermQA(
            question_id=qa.id,
            round_id=qa.round_id,
            round_type=round_record.round_type if round_record is not None else None,
            sequence=qa.sequence,
            question_type=qa.question_type,
            question_kind=qa.question_kind,
            question=qa.question,
            answer=(qa.answer or "").strip(),
            evaluation=self._public_evaluation(evaluation),
        )

    def _merge_recent(
        self,
        snapshot: ShortTermMemorySnapshot,
        round_record: InterviewRoundRecord,
        qa_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[int, dict[str, Any]] = {
            item.question_id: {
                "id": item.question_id,
                "round_id": item.round_id,
                "round_type": item.round_type,
                "sequence": item.sequence,
                "question_type": item.question_type,
                "question_kind": item.question_kind,
                "question": item.question,
                "answer": item.answer,
                "evaluation": item.evaluation,
            }
            for item in snapshot.recent_qa
        }
        for item in qa_history:
            question_id = item.get("id")
            answer = item.get("answer")
            if (
                not isinstance(question_id, int)
                or not isinstance(answer, str)
                or not answer.strip()
            ):
                continue
            merged[question_id] = {
                **item,
                "round_id": round_record.id,
                "round_type": round_record.round_type,
            }
        return sorted(merged.values(), key=lambda item: int(item.get("id") or 0))[
            -self.settings.short_memory_recent_qa_limit :
        ]

    def _question_scores(self, interview_id: int) -> dict[int, dict[str, Any]]:
        if self.evaluation_service is None:
            return {}
        try:
            return self.evaluation_service.question_scores_by_id(interview_id)
        except Exception:
            LOGGER.exception("failed to load question scores for short-term memory")
            return {}

    def _snapshot_status(
        self,
        snapshot: ShortTermMemorySnapshot,
        source: Literal["redis", "mysql"],
        *,
        recovered: bool = False,
    ) -> ShortTermMemoryStatus:
        compressed = snapshot.compression_count > 0
        state: Literal["healthy", "compressed", "recovered"] = (
            "recovered" if recovered else ("compressed" if compressed else "healthy")
        )
        return self._status(
            state,
            source,
            compressed=compressed,
            fallback_used=recovered,
            updated_at=snapshot.updated_at,
        )

    def _degraded_status(
        self,
        user_id: int,
        interview: InterviewRecord,
        round_id: int | None = None,
    ) -> ShortTermMemoryStatus:
        self._event(
            user_id,
            interview,
            round_id,
            "short_memory_redis_degraded",
        )
        return self._status("degraded", "mysql", fallback_used=True)

    @staticmethod
    def _status(
        state: Literal["healthy", "compressed", "recovered", "degraded"],
        source: Literal["redis", "mysql"],
        *,
        compressed: bool = False,
        fallback_used: bool = False,
        updated_at: datetime | None = None,
    ) -> ShortTermMemoryStatus:
        return ShortTermMemoryStatus(
            status=state,
            source=source,
            compressed=compressed,
            fallback_used=fallback_used,
            updated_at=updated_at or datetime.utcnow(),
        )

    def _event(
        self,
        user_id: int,
        interview: InterviewRecord,
        round_id: int | None,
        event_type: str,
    ) -> None:
        record_harness_event(
            connection=getattr(self.repository, "connection", None),
            user_id=user_id,
            interview_id=interview.id,
            round_id=round_id,
            node_type="short_term_memory",
            event_type=event_type,
            payload={"source": "redis" if "degraded" not in event_type else "mysql"},
        )

    @staticmethod
    def _source_revision(
        interview: InterviewRecord,
        qa_records: list[QARecord],
        rounds: list[InterviewRoundRecord],
    ) -> str:
        payload = {
            "interview": [
                interview.overall_status,
                interview.current_round,
                interview.question_count,
            ],
            "qa": [
                [
                    item.id,
                    item.round_id,
                    item.sequence,
                    item.question_type,
                    item.question_kind,
                    item.question_status,
                    item.question,
                    item.answer,
                ]
                for item in qa_records
            ],
            "rounds": [
                [
                    item.id,
                    item.status,
                    item.score,
                    item.result,
                    item.summary,
                    item.ended_at,
                ]
                for item in rounds
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_evaluation(value: dict[str, Any] | None) -> dict[str, Any] | None:
        if not value:
            return None
        keys = (
            "total_score",
            "strengths",
            "issues",
            "evidence",
            "should_follow_up",
            "follow_up_direction",
        )
        return {key: value.get(key) for key in keys if key in value}

    @staticmethod
    def _public_round_summary(value: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "score",
            "result",
            "dimension_reviews",
            "strengths",
            "main_issues",
            "suggestions",
            "evidence",
            "is_reference_only",
            "reference_note",
        )
        return {key: value.get(key) for key in keys if key in value}

    @staticmethod
    def _role_view(summary: dict[str, Any], round_type: str) -> dict[str, Any]:
        shared = {
            key: summary.get(key, [])
            for key in ("key_facts", "pending_follow_ups", "consistency_flags")
        }
        role_keys = {
            "resume": ("covered_topics", "weaknesses"),
            "technical": ("covered_topics", "strengths", "weaknesses"),
            "manager": ("strengths", "weaknesses"),
            "hr": ("strengths", "weaknesses"),
        }.get(round_type, ("covered_topics", "strengths", "weaknesses"))
        return {**shared, **{key: summary.get(key, []) for key in role_keys}}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _estimate_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    non_cjk = len(text) - cjk
    return max(1, cjk + (non_cjk + 3) // 4)
