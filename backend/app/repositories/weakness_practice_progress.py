from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WeaknessPracticeProgressRecord:
    id: int
    user_id: int
    source_interview_id: int
    practice_interview_id: int
    weakness_title: str
    weakness_key: str
    suggestion: str | None
    round_type: str | None
    status: str
    source_score: int | None = None
    practice_score: int | None = None
    last_practiced_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def to_weakness_practice_progress(
    row: dict[str, Any] | None,
) -> WeaknessPracticeProgressRecord | None:
    if row is None:
        return None
    return WeaknessPracticeProgressRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        source_interview_id=int(row["source_interview_id"]),
        practice_interview_id=int(row["practice_interview_id"]),
        weakness_title=str(row["weakness_title"]),
        weakness_key=str(row["weakness_key"]),
        suggestion=row.get("suggestion"),
        round_type=row.get("round_type"),
        status=str(row.get("status") or "pending"),
        source_score=int(row["source_score"])
        if row.get("source_score") is not None
        else None,
        practice_score=int(row["practice_score"])
        if row.get("practice_score") is not None
        else None,
        last_practiced_at=row.get("last_practiced_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )
