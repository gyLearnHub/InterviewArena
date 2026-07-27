from datetime import UTC, datetime
from typing import Any, cast

from fastapi.encoders import jsonable_encoder

from app.repositories.history import HistoryRepository
from app.services.memory_index import ChromaMemoryIndex
from app.services.short_term_memory_store import get_short_term_memory_store

_DIRECT_EXPORT_TABLES = (
    "resumes",
    "resume_parse_tasks",
    "job_match_analysis_tasks",
    "interviews",
    "candidate_memories",
    "interviewer_memories",
    "agent_memories",
    "memory_tasks",
    "notifications",
    "user_feedback_submissions",
    "review_bookmarks",
    "weakness_practice_progress",
    "rag_audit_logs",
    "skill_call_traces",
    "harness_traces",
    "harness_checkpoints",
    "harness_rule_evaluations",
    "harness_improvement_candidates",
    "harness_artifact_bundles",
    "harness_evolution_runs",
)
_INTERVIEW_CHILD_EXPORTS = {
    "interview_rounds": (
        "SELECT child.* FROM interview_rounds child "
        "JOIN interviews owner ON owner.id = child.interview_id "
        "WHERE owner.user_id = %s ORDER BY child.id"
    ),
    "interview_qa": (
        "SELECT child.* FROM interview_qa child "
        "JOIN interviews owner ON owner.id = child.interview_id "
        "WHERE owner.user_id = %s ORDER BY child.id"
    ),
    "answer_reanswer_attempts": (
        "SELECT child.* FROM answer_reanswer_attempts child "
        "JOIN interviews owner ON owner.id = child.interview_id "
        "WHERE owner.user_id = %s ORDER BY child.id"
    ),
    "evaluation_records": (
        "SELECT child.* FROM evaluation_records child "
        "JOIN interviews owner ON owner.id = child.interview_id "
        "WHERE owner.user_id = %s ORDER BY child.id"
    ),
    "feedback_reports": (
        "SELECT child.* FROM feedback_reports child "
        "JOIN interviews owner ON owner.id = child.interview_id "
        "WHERE owner.user_id = %s ORDER BY child.id"
    ),
}


def export_account_data(connection: Any, user_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, username, display_name, avatar_url, memory_enabled,
                   memory_updated_at, external_model_consent_at,
                   external_model_consent_version, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        profile = cursor.fetchone() or {}
        data: dict[str, Any] = {}
        for table in _DIRECT_EXPORT_TABLES:
            cursor.execute(f"SELECT * FROM {table} WHERE user_id = %s ORDER BY id", (user_id,))
            data[table] = list(cursor.fetchall())
        for name, query in _INTERVIEW_CHILD_EXPORTS.items():
            cursor.execute(query, (user_id,))
            data[name] = list(cursor.fetchall())
    return cast(
        dict[str, Any],
        jsonable_encoder(
            {
            "export_version": "1",
            "exported_at": datetime.now(UTC),
            "profile": profile,
            "data": data,
            }
        ),
    )


def delete_account_data(connection: Any, user_id: int) -> tuple[list[str], str | None]:
    history = HistoryRepository(connection)
    interview_ids = history.list_interview_ids_by_user(user_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT original_file_path FROM resumes "
            "WHERE user_id = %s AND original_file_path <> ''",
            (user_id,),
        )
        resume_paths = [str(row["original_file_path"]) for row in cursor.fetchall()]
        cursor.execute("SELECT avatar_url FROM users WHERE id = %s", (user_id,))
        user_row = cursor.fetchone() or {}
        avatar_url = str(user_row["avatar_url"]) if user_row.get("avatar_url") else None

    get_short_term_memory_store().delete_many(user_id, interview_ids)
    vector_error = ChromaMemoryIndex().delete_user_memories(user_id)
    if vector_error and vector_error != "chroma_disabled":
        raise RuntimeError(vector_error)

    _delete_user_evolution_data(connection, user_id)
    history.delete_all_by_user(user_id)
    with connection.cursor() as cursor:
        for path in resume_paths:
            cursor.execute(
                """
                INSERT INTO file_cleanup_tasks (original_file_path)
                VALUES (%s)
                ON DUPLICATE KEY UPDATE
                    status = 'pending',
                    next_retry_at = NULL,
                    completed_at = NULL
                """,
                (path,),
            )
        for table in (
            "review_bookmarks",
            "candidate_memories",
            "interviewer_memories",
            "agent_memories",
            "memory_tasks",
            "notifications",
            "user_feedback_submissions",
            "rag_audit_logs",
            "skill_call_traces",
            "harness_improvement_candidates",
            "job_match_analysis_tasks",
            "resume_parse_tasks",
        ):
            cursor.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM resumes WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if int(cursor.rowcount) != 1:
            raise RuntimeError("account deletion did not remove the user")
    return resume_paths, avatar_url


def _delete_user_evolution_data(connection: Any, user_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE event
            FROM harness_evolution_events event
            LEFT JOIN harness_evolution_runs run ON run.id = event.run_id
            LEFT JOIN harness_artifact_bundles bundle ON bundle.id = event.bundle_id
            WHERE run.user_id = %s OR bundle.user_id = %s
            """,
            (user_id, user_id),
        )
        cursor.execute(
            """
            DELETE sample
            FROM harness_evolution_samples sample
            JOIN harness_evolution_runs run ON run.id = sample.run_id
            WHERE run.user_id = %s
            """,
            (user_id,),
        )
        cursor.execute(
            """
            DELETE observation
            FROM harness_evolution_observations observation
            JOIN harness_artifact_bundles bundle ON bundle.id = observation.bundle_id
            WHERE bundle.user_id = %s
            """,
            (user_id,),
        )
        cursor.execute("DELETE FROM harness_evolution_runs WHERE user_id = %s", (user_id,))
        cursor.execute(
            """
            DELETE artifact
            FROM harness_artifacts artifact
            JOIN harness_artifact_bundles bundle ON bundle.id = artifact.bundle_id
            WHERE bundle.user_id = %s
            """,
            (user_id,),
        )
        cursor.execute(
            """
            UPDATE harness_artifact_bundles child
            JOIN harness_artifact_bundles parent ON parent.id = child.parent_bundle_id
            SET child.parent_bundle_id = NULL
            WHERE parent.user_id = %s
            """,
            (user_id,),
        )
        cursor.execute("DELETE FROM harness_artifact_bundles WHERE user_id = %s", (user_id,))
