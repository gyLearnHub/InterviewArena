from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class QuestionFeedbackContext:
    interview_id: int
    round_id: int | None


@dataclass(frozen=True)
class UserFeedbackSubmissionRecord:
    id: int
    user_id: int
    feedback_type: str
    content: str
    rating: int | None
    interview_id: int | None
    round_id: int | None
    question_id: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class UserFeedbackRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_submission(
        self,
        *,
        user_id: int,
        feedback_type: str,
        content: str,
        rating: int | None,
        interview_id: int | None,
        round_id: int | None,
        question_id: int | None,
    ) -> UserFeedbackSubmissionRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_feedback_submissions (
                    user_id, feedback_type, content, rating,
                    interview_id, round_id, question_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    feedback_type,
                    content,
                    rating,
                    interview_id,
                    round_id,
                    question_id,
                ),
            )
            submission_id = int(cursor.lastrowid)

        record = self.get_by_id(submission_id)
        if record is None:
            raise RuntimeError("created feedback submission was not found")
        return record

    def get_by_id(self, submission_id: int) -> UserFeedbackSubmissionRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, feedback_type, content, rating,
                       interview_id, round_id, question_id, status,
                       created_at, updated_at
                FROM user_feedback_submissions
                WHERE id = %s
                """,
                (submission_id,),
            )
            row = cursor.fetchone()
        return _to_record(row) if row is not None else None

    def get_interview_owner_id(self, interview_id: int) -> int | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM interviews WHERE id = %s", (interview_id,))
            row = cursor.fetchone()
        return int(row["user_id"]) if row is not None else None

    def get_interview_id_by_round(self, round_id: int, user_id: int) -> int | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ir.interview_id
                FROM interview_rounds ir
                JOIN interviews i ON i.id = ir.interview_id
                WHERE ir.id = %s AND i.user_id = %s
                """,
                (round_id, user_id),
            )
            row = cursor.fetchone()
        return int(row["interview_id"]) if row is not None else None

    def get_question_context(
        self,
        question_id: int,
        user_id: int,
    ) -> QuestionFeedbackContext | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT qa.interview_id, qa.round_id
                FROM interview_qa qa
                JOIN interviews i ON i.id = qa.interview_id
                WHERE qa.id = %s AND i.user_id = %s
                """,
                (question_id, user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return QuestionFeedbackContext(
            interview_id=int(row["interview_id"]),
            round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        )


def _to_record(row: dict[str, Any]) -> UserFeedbackSubmissionRecord:
    return UserFeedbackSubmissionRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        feedback_type=str(row["feedback_type"]),
        content=str(row["content"]),
        rating=int(row["rating"]) if row.get("rating") is not None else None,
        interview_id=int(row["interview_id"]) if row.get("interview_id") is not None else None,
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        question_id=int(row["question_id"]) if row.get("question_id") is not None else None,
        status=str(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
