import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

VALID_COLLECTIONS = {"candidate_memories", "interviewer_memories", "agent_memories"}
ACTIVE_RECALL_STATUSES = {"active"}
RECALL_INDEX_STATUSES = {"indexed", "pending_index"}


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    collection: str
    memory_type: str
    title: str
    content: str
    structured_data: dict[str, Any]
    tokens: list[str]
    confidence: float
    status: str
    index_status: str
    source_interview_id: int | None
    source_round_id: int | None
    version: int
    created_at: datetime | None
    updated_at: datetime | None
    user_id: int | None = None
    agent_type: str | None = None
    position_key: str | None = None
    scenario: str | None = None


class MemoryRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def commit(self) -> None:
        self.connection.commit()

    def list_candidate_memories(
        self,
        *,
        user_id: int,
        memory_types: list[str] | None = None,
        include_pending_index: bool = False,
    ) -> list[MemoryRecord]:
        index_statuses = RECALL_INDEX_STATUSES if include_pending_index else {"indexed"}
        conditions = [
            "user_id = %s",
            "status = 'active'",
            f"index_status IN ({','.join(['%s'] * len(index_statuses))})",
        ]
        params: list[Any] = [user_id, *sorted(index_statuses)]
        if memory_types:
            conditions.append(f"memory_type IN ({','.join(['%s'] * len(memory_types))})")
            params.extend(memory_types)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM candidate_memories
                WHERE {" AND ".join(conditions)}
                ORDER BY confidence DESC, updated_at DESC
                LIMIT 100
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_memory(row, "candidate_memories") for row in rows]

    def count_active_candidate_memories(self, user_id: int) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM candidate_memories
                WHERE user_id = %s
                  AND status = 'active'
                """,
                (user_id,),
            )
            row = cursor.fetchone() or {}
        return int(row.get("count") or 0)

    def list_user_candidate_memories(
        self,
        *,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM candidate_memories
                WHERE user_id = %s
                  AND status <> 'deleted'
                ORDER BY updated_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cursor.fetchall()
        return [_to_memory(row, "candidate_memories") for row in rows]

    def count_user_candidate_memories_by_status(self, *, user_id: int) -> dict[str, int]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM candidate_memories
                WHERE user_id = %s
                  AND status <> 'deleted'
                GROUP BY status
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return {str(row["status"]): int(row.get("count") or 0) for row in rows}

    def list_system_memories(
        self,
        *,
        collection: str,
        agent_type: str | None = None,
        memory_types: list[str] | None = None,
    ) -> list[MemoryRecord]:
        _ensure_collection(collection)
        if collection == "candidate_memories":
            raise ValueError("candidate memories require user filtering")
        conditions = ["status = 'active'", "index_status IN ('indexed', 'pending_index')"]
        params: list[Any] = []
        if agent_type:
            conditions.append("agent_type = %s")
            params.append(agent_type)
        if memory_types:
            conditions.append(f"memory_type IN ({','.join(['%s'] * len(memory_types))})")
            params.extend(memory_types)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM {collection}
                WHERE {" AND ".join(conditions)}
                ORDER BY confidence DESC, updated_at DESC
                LIMIT 100
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_memory(row, collection) for row in rows]

    def find_similar(
        self,
        *,
        item: dict[str, Any],
        user_id: int | None,
        agent_type: str | None,
    ) -> MemoryRecord | None:
        collection = str(item["collection"])
        _ensure_collection(collection)
        title = str(item["title"]).strip()
        memory_type = str(item["memory_type"]).strip()
        if collection == "candidate_memories":
            if user_id is None:
                return None
            query = """
                SELECT *
                FROM candidate_memories
                WHERE user_id = %s
                  AND memory_type = %s
                  AND title = %s
                  AND status IN ('active', 'pending_review')
                ORDER BY version DESC
                LIMIT 1
            """
            params: tuple[Any, ...] = (user_id, memory_type, title)
        else:
            query = f"""
                SELECT *
                FROM {collection}
                WHERE agent_type = %s
                  AND memory_type = %s
                  AND title = %s
                  AND status IN ('active', 'pending_review')
                ORDER BY version DESC
                LIMIT 1
            """
            params = (agent_type or "", memory_type, title)
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return _to_memory(row, collection) if row is not None else None

    def insert_memory(
        self,
        *,
        collection: str,
        user_id: int | None,
        agent_type: str | None,
        position_key: str | None,
        scenario: str | None,
        memory_type: str,
        title: str,
        content: str,
        structured_data: dict[str, Any],
        tokens: list[str],
        confidence: float,
        confidence_detail: dict[str, Any],
        status: str,
        index_status: str,
        source_interview_id: int | None,
        source_round_id: int | None,
        version: int = 1,
    ) -> MemoryRecord:
        _ensure_collection(collection)
        if collection == "candidate_memories":
            columns = """
                user_id, memory_type, title, content, structured_data, tokens, confidence,
                confidence_detail, status, index_status, source_interview_id, source_round_id,
                version, last_evidence_at
            """
            values = """
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            """
            params: tuple[Any, ...] = (
                user_id,
                memory_type,
                title,
                content,
                json.dumps(structured_data, ensure_ascii=False),
                json.dumps(tokens, ensure_ascii=False),
                confidence,
                json.dumps(confidence_detail, ensure_ascii=False),
                status,
                index_status,
                source_interview_id,
                source_round_id,
                version,
            )
        else:
            identity_column = "position_key" if collection == "interviewer_memories" else "scenario"
            identity_value = position_key if collection == "interviewer_memories" else scenario
            columns = f"""
                agent_type, {identity_column}, memory_type, title, content, structured_data,
                tokens, confidence, confidence_detail, status, index_status,
                source_interview_id, source_round_id, version, last_evidence_at
            """
            values = """
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            """
            params = (
                agent_type or "",
                identity_value or "",
                memory_type,
                title,
                content,
                json.dumps(structured_data, ensure_ascii=False),
                json.dumps(tokens, ensure_ascii=False),
                confidence,
                json.dumps(confidence_detail, ensure_ascii=False),
                status,
                index_status,
                source_interview_id,
                source_round_id,
                version,
            )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {collection} ({columns}) VALUES ({values})",
                params,
            )
            memory_id = int(cursor.lastrowid)
        record = self.get(collection, memory_id)
        if record is None:
            raise RuntimeError("memory was not saved")
        return record

    def update_existing_memory(
        self,
        *,
        record: MemoryRecord,
        content: str,
        structured_data: dict[str, Any],
        tokens: list[str],
        confidence: float,
        confidence_detail: dict[str, Any],
        status: str,
        index_status: str,
    ) -> MemoryRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {record.collection}
                SET content = %s,
                    structured_data = %s,
                    tokens = %s,
                    confidence = %s,
                    confidence_detail = %s,
                    status = %s,
                    index_status = %s,
                    version = version + 1,
                    last_evidence_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    content,
                    json.dumps(structured_data, ensure_ascii=False),
                    json.dumps(tokens, ensure_ascii=False),
                    confidence,
                    json.dumps(confidence_detail, ensure_ascii=False),
                    status,
                    index_status,
                    record.id,
                ),
            )
        updated = self.get(record.collection, record.id)
        if updated is None:
            raise RuntimeError("memory update failed")
        return updated

    def get(self, collection: str, memory_id: int) -> MemoryRecord | None:
        _ensure_collection(collection)
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {collection} WHERE id = %s", (memory_id,))
            row = cursor.fetchone()
        return _to_memory(row, collection) if row is not None else None

    def mark_user_candidate_pending_delete(self, user_id: int) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE candidate_memories
                SET status = 'deleted', index_status = 'pending_delete'
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return int(cursor.rowcount)

    def mark_candidate_memory_deleted(self, *, memory_id: int, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE candidate_memories
                SET status = 'deleted',
                    index_status = 'pending_delete'
                WHERE id = %s
                  AND user_id = %s
                  AND status <> 'deleted'
                """,
                (memory_id, user_id),
            )
            return int(cursor.rowcount) > 0

    def delete_user_candidate_memories(self, user_id: int) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM candidate_memories
                WHERE user_id = %s
                  AND status = 'deleted'
                  AND index_status = 'pending_delete'
                """,
                (user_id,),
            )
            return int(cursor.rowcount)

    def mark_indexed(self, collection: str, memory_id: int) -> None:
        _ensure_collection(collection)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {collection} SET index_status = 'indexed' WHERE id = %s",
                (memory_id,),
            )

    def mark_index_failed(self, collection: str, memory_id: int) -> None:
        _ensure_collection(collection)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {collection} SET index_status = 'index_failed' WHERE id = %s",
                (memory_id,),
            )


def _ensure_collection(collection: str) -> None:
    if collection not in VALID_COLLECTIONS:
        raise ValueError(f"Unsupported memory collection: {collection}")


def _to_memory(row: dict[str, Any], collection: str) -> MemoryRecord:
    return MemoryRecord(
        id=int(row["id"]),
        collection=collection,
        memory_type=str(row["memory_type"]),
        title=str(row["title"]),
        content=str(row["content"]),
        structured_data=_json_dict(row.get("structured_data")),
        tokens=_json_string_list(row.get("tokens")),
        confidence=float(row.get("confidence") or 0),
        status=str(row["status"]),
        index_status=str(row["index_status"]),
        source_interview_id=(
            int(row["source_interview_id"]) if row.get("source_interview_id") is not None else None
        ),
        source_round_id=(
            int(row["source_round_id"]) if row.get("source_round_id") is not None else None
        ),
        version=int(row.get("version") or 1),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        user_id=int(row["user_id"]) if row.get("user_id") is not None else None,
        agent_type=row.get("agent_type"),
        position_key=row.get("position_key"),
        scenario=row.get("scenario"),
    )


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []
