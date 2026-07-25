import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.schemas.review_bookmark import (
    review_bookmark_evaluation_json,
    review_bookmark_evaluation_to_dict,
)
from pydantic import ValidationError

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class ReviewBookmarkRecord:
    id: int
    user_id: int
    bookmark_key: str
    source_interview_id: int | None
    target_position: str
    round_id: int | None
    round_type: str | None
    question_id: int | None
    title: str
    issue: str
    suggestion: str | None
    question: str | None
    answer: str | None
    evaluation: JSONDict | None
    source_score: int | None
    status: str
    practice_interview_id: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ReviewBookmarkQuestionContext:
    interview_id: int
    target_position: str
    round_id: int | None
    round_type: str | None
    question_id: int
    question: str
    answer: str | None


@dataclass(frozen=True)
class ReviewBookmarkRoundContext:
    interview_id: int
    round_id: int
    round_type: str | None


@dataclass(frozen=True)
class ReviewBookmarkInterviewContext:
    interview_id: int
    target_position: str


class ReviewBookmarkRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def list_by_user(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        round_type: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[ReviewBookmarkRecord]:
        conditions = ["rb.user_id = %s"]
        params: list[Any] = [user_id]
        if round_type is not None:
            conditions.append("rb.round_type = %s")
            params.append(round_type)
        if statuses:
            placeholders = ", ".join(["%s"] * len(statuses))
            conditions.append(f"rb.status IN ({placeholders})")
            params.extend(statuses)
        params.extend([max(1, min(limit, 100)), max(offset, 0)])
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT rb.id, rb.user_id, rb.bookmark_key, rb.source_interview_id,
                       rb.target_position, rb.round_id, rb.round_type, rb.question_id,
                       rb.title, rb.issue, rb.suggestion, rb.question, rb.answer,
                       rb.evaluation, rb.source_score, rb.status,
                       rb.practice_interview_id, rb.created_at, rb.updated_at
                FROM review_bookmarks rb
                WHERE {" AND ".join(conditions)}
                ORDER BY rb.updated_at DESC, rb.id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_record(row) for row in rows]

    def get_for_user(
        self,
        bookmark_id: int,
        user_id: int,
    ) -> ReviewBookmarkRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rb.id, rb.user_id, rb.bookmark_key, rb.source_interview_id,
                       rb.target_position, rb.round_id, rb.round_type, rb.question_id,
                       rb.title, rb.issue, rb.suggestion, rb.question, rb.answer,
                       rb.evaluation, rb.source_score, rb.status,
                       rb.practice_interview_id, rb.created_at, rb.updated_at
                FROM review_bookmarks rb
                WHERE rb.id = %s AND rb.user_id = %s
                """,
                (bookmark_id, user_id),
            )
            row = cursor.fetchone()
        return _to_record(row) if row is not None else None

    def lock_for_practice(
        self,
        bookmark_id: int,
        user_id: int,
    ) -> ReviewBookmarkRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rb.id, rb.user_id, rb.bookmark_key, rb.source_interview_id,
                       rb.target_position, rb.round_id, rb.round_type, rb.question_id,
                       rb.title, rb.issue, rb.suggestion, rb.question, rb.answer,
                       rb.evaluation, rb.source_score, rb.status,
                       rb.practice_interview_id, rb.created_at, rb.updated_at
                FROM review_bookmarks rb
                WHERE rb.id = %s AND rb.user_id = %s
                FOR UPDATE
                """,
                (bookmark_id, user_id),
            )
            row = cursor.fetchone()
        return _to_record(row) if row is not None else None

    def get_by_key(
        self,
        user_id: int,
        bookmark_key: str,
    ) -> ReviewBookmarkRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rb.id, rb.user_id, rb.bookmark_key, rb.source_interview_id,
                       rb.target_position, rb.round_id, rb.round_type, rb.question_id,
                       rb.title, rb.issue, rb.suggestion, rb.question, rb.answer,
                       rb.evaluation, rb.source_score, rb.status,
                       rb.practice_interview_id, rb.created_at, rb.updated_at
                FROM review_bookmarks rb
                WHERE rb.user_id = %s AND rb.bookmark_key = %s
                """,
                (user_id, bookmark_key),
            )
            row = cursor.fetchone()
        return _to_record(row) if row is not None else None

    def upsert_bookmark(
        self,
        *,
        user_id: int,
        bookmark_key: str,
        source_interview_id: int,
        target_position: str,
        round_id: int | None,
        round_type: str | None,
        question_id: int | None,
        title: str,
        issue: str,
        suggestion: str | None,
        question: str | None,
        answer: str | None,
        evaluation: JSONDict | None,
        source_score: int | None,
    ) -> ReviewBookmarkRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO review_bookmarks (
                    user_id, bookmark_key, source_interview_id, target_position,
                    round_id, round_type,
                    question_id, title, issue, suggestion, question, answer,
                    evaluation, source_score, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
                ON DUPLICATE KEY UPDATE
                    target_position = VALUES(target_position),
                    title = VALUES(title),
                    issue = VALUES(issue),
                    suggestion = VALUES(suggestion),
                    question = VALUES(question),
                    answer = VALUES(answer),
                    evaluation = VALUES(evaluation),
                    source_score = VALUES(source_score),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    bookmark_key,
                    source_interview_id,
                    target_position,
                    round_id,
                    round_type,
                    question_id,
                    title,
                    issue,
                    suggestion,
                    question,
                    answer,
                    _json_dumps(evaluation) if evaluation is not None else None,
                    source_score,
                ),
            )
        record = self.get_by_key(user_id, bookmark_key)
        if record is None:
            raise RuntimeError("created review bookmark was not found")
        return record

    def mark_practice_created(
        self,
        *,
        bookmark_id: int,
        user_id: int,
        practice_interview_id: int,
    ) -> ReviewBookmarkRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE review_bookmarks
                SET status = 'practice_created',
                    practice_interview_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s AND practice_interview_id IS NULL
                """,
                (practice_interview_id, bookmark_id, user_id),
            )
        return self.get_for_user(bookmark_id, user_id)

    def update_status(
        self,
        *,
        bookmark_id: int,
        user_id: int,
        status: str,
    ) -> ReviewBookmarkRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE review_bookmarks
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """,
                (status, bookmark_id, user_id),
            )
        return self.get_for_user(bookmark_id, user_id)

    def delete_for_user(self, bookmark_id: int, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM review_bookmarks WHERE id = %s AND user_id = %s",
                (bookmark_id, user_id),
            )
            return int(cursor.rowcount) > 0

    def get_question_context(
        self,
        question_id: int,
        user_id: int,
    ) -> ReviewBookmarkQuestionContext | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT qa.id AS question_id, qa.interview_id, i.target_position,
                       qa.round_id, ir.round_type, qa.question, qa.answer
                FROM interview_qa qa
                JOIN interviews i ON i.id = qa.interview_id
                LEFT JOIN interview_rounds ir ON ir.id = qa.round_id
                WHERE qa.id = %s AND i.user_id = %s
                """,
                (question_id, user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ReviewBookmarkQuestionContext(
            interview_id=int(row["interview_id"]),
            target_position=str(row["target_position"]),
            round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
            round_type=str(row["round_type"]) if row.get("round_type") is not None else None,
            question_id=int(row["question_id"]),
            question=str(row["question"]),
            answer=str(row["answer"]) if row.get("answer") is not None else None,
        )

    def get_interview_context(
        self,
        interview_id: int,
        user_id: int,
    ) -> ReviewBookmarkInterviewContext | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, target_position
                FROM interviews
                WHERE id = %s AND user_id = %s
                """,
                (interview_id, user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ReviewBookmarkInterviewContext(
            interview_id=int(row["id"]),
            target_position=str(row["target_position"]),
        )

    def get_round_context(
        self,
        round_id: int,
        user_id: int,
    ) -> ReviewBookmarkRoundContext | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ir.id AS round_id, ir.interview_id, ir.round_type
                FROM interview_rounds ir
                JOIN interviews i ON i.id = ir.interview_id
                WHERE ir.id = %s AND i.user_id = %s
                """,
                (round_id, user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ReviewBookmarkRoundContext(
            interview_id=int(row["interview_id"]),
            round_id=int(row["round_id"]),
            round_type=str(row["round_type"]) if row.get("round_type") is not None else None,
        )


def _to_record(row: dict[str, Any]) -> ReviewBookmarkRecord:
    return ReviewBookmarkRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        bookmark_key=str(row["bookmark_key"]),
        source_interview_id=(
            int(row["source_interview_id"])
            if row.get("source_interview_id") is not None
            else None
        ),
        target_position=str(row["target_position"]),
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        round_type=str(row["round_type"]) if row.get("round_type") is not None else None,
        question_id=int(row["question_id"]) if row.get("question_id") is not None else None,
        title=str(row["title"]),
        issue=str(row["issue"]),
        suggestion=str(row["suggestion"]) if row.get("suggestion") is not None else None,
        question=str(row["question"]) if row.get("question") is not None else None,
        answer=str(row["answer"]) if row.get("answer") is not None else None,
        evaluation=_json_dict(row.get("evaluation")),
        source_score=int(row["source_score"]) if row.get("source_score") is not None else None,
        status=str(row["status"]),
        practice_interview_id=(
            int(row["practice_interview_id"])
            if row.get("practice_interview_id") is not None
            else None
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _json_dumps(value: JSONDict) -> str:
    try:
        payload = review_bookmark_evaluation_to_dict(value)
        return review_bookmark_evaluation_json(payload)
    except (ValidationError, ValueError) as exc:
        message = (
            "复盘评价内容过大。"
            if "review_bookmark_evaluation_too_large" in str(exc) or "过大" in str(exc)
            else "复盘评价内容格式不正确。"
        )
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT,
            message=message,
        ) from exc


def _json_dict(value: Any) -> JSONDict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return None
