from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db.mysql import mysql_connection
from app.services.memory_index import COLLECTIONS, ChromaMemoryIndex

DEFAULT_BATCH_MARKS = (
    "memory_real_eval_20260618",
    "real4round_",
    "CodexReal4Round",
)
DEFAULT_USERNAME_PATTERNS = (
    "codex_check_%",
    "codex_ui_%",
    "real4round_%",
    "e2e_%",
    "test_%",
)
TABLE_ORDER = (
    "harness_trace_events",
    "harness_rule_evaluations",
    "harness_checkpoints",
    "harness_improvement_candidates",
    "harness_traces",
    "rag_audit_logs",
    "memory_tasks",
    "feedback_reports",
    "evaluation_records",
    "interview_qa",
    "interview_rounds",
    "interviews",
    "resumes",
    "users",
)
SAFE_FILE_TARGETS = (
    "docs_real_four_round_run*.log",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "frontend/test-results",
    "frontend/playwright-report",
)


@dataclass
class CleanupTarget:
    test_user_ids: list[int] = field(default_factory=list)
    test_usernames: dict[int, str] = field(default_factory=dict)
    interview_ids: list[int] = field(default_factory=list)
    round_ids: list[int] = field(default_factory=list)
    qa_ids: list[int] = field(default_factory=list)
    trace_ids: list[int] = field(default_factory=list)
    skill_trace_ids: list[int] = field(default_factory=list)
    checkpoint_ids: list[int] = field(default_factory=list)
    rule_ids: list[int] = field(default_factory=list)
    improvement_ids: list[int] = field(default_factory=list)
    feedback_ids: list[int] = field(default_factory=list)
    evaluation_ids: list[int] = field(default_factory=list)
    memory_task_ids: list[int] = field(default_factory=list)
    rag_audit_ids: list[int] = field(default_factory=list)
    resume_ids: list[int] = field(default_factory=list)
    memory_ids: dict[str, list[int]] = field(
        default_factory=lambda: {collection: [] for collection in COLLECTIONS}
    )
    ambiguous: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely inspect and clean clearly identified InterviewArena test data."
    )
    parser.add_argument(
        "--execute", action="store_true", help="Actually delete selected data."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Only inspect. This is the default."
    )
    parser.add_argument(
        "--username", action="append", default=[], help="Exact test username."
    )
    parser.add_argument(
        "--user-id",
        action="append",
        type=int,
        default=[],
        help="Explicit test user id.",
    )
    parser.add_argument(
        "--username-like",
        action="append",
        default=[],
        help="SQL LIKE pattern for test usernames. Backslash escapes are honored.",
    )
    parser.add_argument(
        "--batch-mark",
        action="append",
        default=[],
        help="Exact batch/test marker to match in whitelisted text fields.",
    )
    parser.add_argument(
        "--interview-id",
        action="append",
        type=int,
        default=[],
        help="Explicit test interview id.",
    )
    parser.add_argument(
        "--keep-test-users",
        action="store_true",
        help="Keep matching test users and their resumes after deleting test interviews.",
    )
    parser.add_argument(
        "--clean-files",
        action="store_true",
        help="Delete whitelisted cache, temporary, and test log files.",
    )
    parser.add_argument("--report-json", default="", help="Optional JSON report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run = not args.execute or args.dry_run
    report = run_cleanup(args, dry_run=dry_run)
    text = json.dumps(_json_safe(report), ensure_ascii=False, indent=2)
    print(text)
    if args.report_json:
        path = Path(args.report_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")


def run_cleanup(args: argparse.Namespace, *, dry_run: bool) -> dict[str, Any]:
    markers = sorted(set(DEFAULT_BATCH_MARKS + tuple(args.batch_mark)))
    username_patterns = sorted(
        set(DEFAULT_USERNAME_PATTERNS + tuple(args.username_like))
    )
    started_at = datetime.utcnow()
    with mysql_connection() as connection:
        target = discover_targets(connection, args, markers, username_patterns)
        before = collect_counts(connection, target)
        foreign_keys = collect_foreign_keys(connection)
        collections = inspect_chroma(target)
        if dry_run:
            connection.rollback()
            deleted: dict[str, Any] = {}
            files = (
                inspect_files(delete=False) if args.clean_files else {"skipped": True}
            )
        else:
            vector_result = delete_chroma_vectors(target)
            if not vector_result["ok"]:
                connection.rollback()
                return {
                    "mode": "execute",
                    "ok": False,
                    "error": "ChromaDB vector deletion failed; MySQL cleanup was rolled back.",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow(),
                    "filters": filters_payload(args, markers, username_patterns),
                    "foreign_keys": foreign_keys,
                    "targets": target_payload(target),
                    "before": before,
                    "chroma": vector_result,
                }
            deleted = delete_mysql_records(
                connection, target, keep_test_users=args.keep_test_users
            )
            files = (
                inspect_files(delete=True) if args.clean_files else {"skipped": True}
            )
        after = collect_counts(connection, target)
        orphan_checks = collect_orphan_checks(connection)
        retained = collect_retained_summary(connection, target)
        return {
            "mode": "dry-run" if dry_run else "execute",
            "ok": True,
            "started_at": started_at,
            "finished_at": datetime.utcnow(),
            "filters": filters_payload(args, markers, username_patterns),
            "foreign_keys": foreign_keys,
            "collections": list(COLLECTIONS),
            "targets": target_payload(target),
            "before": before,
            "deleted": deleted,
            "after": after,
            "chroma": collections if dry_run else inspect_chroma(target),
            "files": files,
            "retained": retained,
            "orphan_checks": orphan_checks,
            "ambiguous": target.ambiguous,
        }


def discover_targets(
    connection: Any,
    args: argparse.Namespace,
    markers: list[str],
    username_patterns: list[str],
) -> CleanupTarget:
    target = CleanupTarget()
    with connection.cursor() as cursor:
        target.test_user_ids, target.test_usernames = find_test_users(
            cursor, args, username_patterns
        )
        target.interview_ids = find_interviews(cursor, target, args, markers)
        target.round_ids = select_ids(
            cursor,
            "SELECT id FROM interview_rounds WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        target.qa_ids = select_ids(
            cursor,
            "SELECT id FROM interview_qa WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        target.trace_ids = select_ids(
            cursor,
            "SELECT id FROM harness_traces WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        if table_exists(cursor, "skill_call_traces"):
            target.skill_trace_ids = select_ids(
                cursor,
                "SELECT id FROM skill_call_traces WHERE interview_id IN ({}) ORDER BY id",
                target.interview_ids,
            )
        target.checkpoint_ids = select_ids(
            cursor,
            "SELECT id FROM harness_checkpoints WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        target.rule_ids = select_ids(
            cursor,
            "SELECT id FROM harness_rule_evaluations WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        target.improvement_ids = find_improvement_ids(cursor, target)
        target.feedback_ids = select_ids(
            cursor,
            "SELECT id FROM feedback_reports WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        target.evaluation_ids = select_ids(
            cursor,
            "SELECT id FROM evaluation_records WHERE interview_id IN ({}) ORDER BY id",
            target.interview_ids,
        )
        target.memory_ids = find_memory_ids(cursor, target, markers)
        target.memory_task_ids = find_memory_task_ids(cursor, target)
        target.rag_audit_ids = find_rag_audit_ids(cursor, target, markers)
        target.resume_ids = find_resume_ids(
            cursor, target, keep_test_users=args.keep_test_users
        )
        target.ambiguous = find_ambiguous(cursor, target, markers)
    return target


def find_test_users(
    cursor: Any,
    args: argparse.Namespace,
    username_patterns: list[str],
) -> tuple[list[int], dict[int, str]]:
    conditions: list[str] = []
    params: list[Any] = []
    if args.user_id:
        conditions.append(f"id IN ({placeholders(args.user_id)})")
        params.extend(args.user_id)
    if args.username:
        conditions.append(f"username IN ({placeholders(args.username)})")
        params.extend(args.username)
    for pattern in username_patterns:
        conditions.append("username LIKE %s")
        params.append(pattern)
    if not conditions:
        return [], {}
    cursor.execute(
        f"SELECT id, username FROM users WHERE {' OR '.join(conditions)} ORDER BY id",
        tuple(params),
    )
    rows = cursor.fetchall()
    ids = [int(row["id"]) for row in rows]
    names = {int(row["id"]): str(row["username"]) for row in rows}
    return ids, names


def find_interviews(
    cursor: Any,
    target: CleanupTarget,
    args: argparse.Namespace,
    markers: list[str],
) -> list[int]:
    ids = set(args.interview_id)
    if target.test_user_ids:
        cursor.execute(
            f"SELECT id FROM interviews WHERE user_id IN ({placeholders(target.test_user_ids)})",
            tuple(target.test_user_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    for marker in markers:
        like = f"%{marker}%"
        cursor.execute(
            """
            SELECT id
            FROM interviews
            WHERE target_position LIKE %s OR job_description LIKE %s
            """,
            (like, like),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    return sorted(ids)


def find_improvement_ids(cursor: Any, target: CleanupTarget) -> list[int]:
    ids: set[int] = set()
    if target.interview_ids:
        cursor.execute(
            f"""
            SELECT id
            FROM harness_improvement_candidates
            WHERE interview_id IN ({placeholders(target.interview_ids)})
            """,
            tuple(target.interview_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    if target.trace_ids:
        cursor.execute(
            f"""
            SELECT id
            FROM harness_improvement_candidates
            WHERE source_trace_id IN ({placeholders(target.trace_ids)})
            """,
            tuple(target.trace_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    return sorted(ids)


def find_memory_ids(
    cursor: Any,
    target: CleanupTarget,
    markers: list[str],
) -> dict[str, list[int]]:
    result: dict[str, set[int]] = {collection: set() for collection in COLLECTIONS}
    for collection in COLLECTIONS:
        if target.interview_ids:
            cursor.execute(
                f"""
                SELECT id
                FROM {collection}
                WHERE source_interview_id IN ({placeholders(target.interview_ids)})
                """,
                tuple(target.interview_ids),
            )
            result[collection].update(int(row["id"]) for row in cursor.fetchall())
        if collection == "candidate_memories" and target.test_user_ids:
            cursor.execute(
                f"""
                SELECT id
                FROM candidate_memories
                WHERE user_id IN ({placeholders(target.test_user_ids)})
                """,
                tuple(target.test_user_ids),
            )
            result[collection].update(int(row["id"]) for row in cursor.fetchall())
        for marker in markers:
            like = f"%{marker}%"
            cursor.execute(
                f"""
                SELECT id
                FROM {collection}
                WHERE title LIKE %s
                   OR content LIKE %s
                   OR CAST(structured_data AS CHAR) LIKE %s
                """,
                (like, like, like),
            )
            result[collection].update(int(row["id"]) for row in cursor.fetchall())
    return {collection: sorted(ids) for collection, ids in result.items()}


def find_memory_task_ids(cursor: Any, target: CleanupTarget) -> list[int]:
    ids: set[int] = set()
    if target.interview_ids:
        interview_placeholders = placeholders(target.interview_ids)
        cursor.execute(
            f"SELECT id FROM memory_tasks WHERE interview_id IN ({interview_placeholders})",
            tuple(target.interview_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    if target.test_user_ids:
        cursor.execute(
            f"SELECT id FROM memory_tasks WHERE user_id IN ({placeholders(target.test_user_ids)})",
            tuple(target.test_user_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    for collection, memory_ids in target.memory_ids.items():
        if not memory_ids:
            continue
        cursor.execute(
            f"""
            SELECT id
            FROM memory_tasks
            WHERE memory_collection = %s AND memory_id IN ({placeholders(memory_ids)})
            """,
            (collection, *memory_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    return sorted(ids)


def find_rag_audit_ids(
    cursor: Any,
    target: CleanupTarget,
    markers: list[str],
) -> list[int]:
    ids: set[int] = set()
    if target.interview_ids:
        interview_placeholders = placeholders(target.interview_ids)
        cursor.execute(
            f"SELECT id FROM rag_audit_logs WHERE interview_id IN ({interview_placeholders})",
            tuple(target.interview_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    if target.test_user_ids:
        user_placeholders = placeholders(target.test_user_ids)
        cursor.execute(
            f"SELECT id FROM rag_audit_logs WHERE user_id IN ({user_placeholders})",
            tuple(target.test_user_ids),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    for marker in markers:
        like = f"%{marker}%"
        cursor.execute(
            """
            SELECT id
            FROM rag_audit_logs
            WHERE request_id LIKE %s
               OR original_intent LIKE %s
               OR rewritten_query LIKE %s
            """,
            (like, like, like),
        )
        ids.update(int(row["id"]) for row in cursor.fetchall())
    return sorted(ids)


def find_resume_ids(
    cursor: Any,
    target: CleanupTarget,
    *,
    keep_test_users: bool,
) -> list[int]:
    if keep_test_users or not target.test_user_ids:
        return []
    user_placeholders = placeholders(target.test_user_ids)
    cursor.execute(
        f"SELECT id FROM resumes WHERE user_id IN ({user_placeholders}) ORDER BY id",
        tuple(target.test_user_ids),
    )
    return [int(row["id"]) for row in cursor.fetchall()]


def find_ambiguous(
    cursor: Any,
    target: CleanupTarget,
    markers: list[str],
) -> dict[str, list[dict[str, Any]]]:
    ambiguous: dict[str, list[dict[str, Any]]] = {}
    for marker in markers:
        like = f"%{marker}%"
        cursor.execute(
            """
            SELECT r.id, r.user_id, u.username, r.original_file_path
            FROM resumes r
            JOIN users u ON u.id = r.user_id
            WHERE (r.original_file_path LIKE %s OR CAST(r.structured_data AS CHAR) LIKE %s)
              AND r.id NOT IN ({})
            ORDER BY r.id
            LIMIT 20
            """.format(
                placeholders(target.resume_ids) if target.resume_ids else "0"
            ),
            (like, like, *target.resume_ids),
        )
        rows = cursor.fetchall()
        if rows:
            ambiguous.setdefault("resumes_with_marker_not_selected", []).extend(rows)
    cursor.execute(
        """
        SELECT id, username
        FROM users
        WHERE username LIKE %s
          AND username NOT LIKE %s
          AND username NOT LIKE %s
          AND username NOT LIKE %s
        ORDER BY id
        LIMIT 50
        """,
        ("%test%", "real4round_%", "e2e_%", "test_%"),
    )
    rows = cursor.fetchall()
    if rows:
        ambiguous["users_containing_test_not_selected"] = rows
    return ambiguous


def collect_counts(connection: Any, target: CleanupTarget) -> dict[str, Any]:
    with connection.cursor() as cursor:
        counts = {
            "users": count_ids(cursor, "users", target.test_user_ids),
            "resumes": count_ids(cursor, "resumes", target.resume_ids),
            "interviews": count_ids(cursor, "interviews", target.interview_ids),
            "interview_rounds": count_ids(cursor, "interview_rounds", target.round_ids),
            "interview_qa": count_ids(cursor, "interview_qa", target.qa_ids),
            "skill_call_traces": count_ids(
                cursor, "skill_call_traces", target.skill_trace_ids
            )
            if table_exists(cursor, "skill_call_traces")
            else 0,
            "feedback_reports": count_ids(
                cursor, "feedback_reports", target.feedback_ids
            ),
            "evaluation_records": count_ids(
                cursor, "evaluation_records", target.evaluation_ids
            ),
            "memory_tasks": count_ids(cursor, "memory_tasks", target.memory_task_ids),
            "rag_audit_logs": count_ids(cursor, "rag_audit_logs", target.rag_audit_ids),
            "harness_traces": count_ids(cursor, "harness_traces", target.trace_ids),
            "harness_trace_events": count_where(
                cursor, "harness_trace_events", "trace_id", target.trace_ids
            ),
            "harness_checkpoints": count_ids(
                cursor, "harness_checkpoints", target.checkpoint_ids
            ),
            "harness_rule_evaluations": count_ids(
                cursor, "harness_rule_evaluations", target.rule_ids
            ),
            "harness_improvement_candidates": count_ids(
                cursor, "harness_improvement_candidates", target.improvement_ids
            ),
            "memories": {},
        }
        for collection, ids in target.memory_ids.items():
            counts["memories"][collection] = count_ids(cursor, collection, ids)
        return counts


def collect_foreign_keys(connection: Any) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE() AS db")
        database = cursor.fetchone()["db"]
        cursor.execute(
            """
            SELECT kcu.TABLE_NAME, kcu.COLUMN_NAME, kcu.REFERENCED_TABLE_NAME,
                   kcu.REFERENCED_COLUMN_NAME, rc.CONSTRAINT_NAME,
                   rc.UPDATE_RULE, rc.DELETE_RULE
            FROM information_schema.REFERENTIAL_CONSTRAINTS rc
            JOIN information_schema.KEY_COLUMN_USAGE kcu
              ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
             AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND rc.TABLE_NAME = kcu.TABLE_NAME
            WHERE rc.CONSTRAINT_SCHEMA = %s
            ORDER BY kcu.TABLE_NAME, rc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
            """,
            (database,),
        )
        return list(cursor.fetchall())


def inspect_chroma(target: CleanupTarget) -> dict[str, Any]:
    index = ChromaMemoryIndex()
    result: dict[str, Any] = {
        "enabled": index.enabled,
        "fallback_reason": index.fallback_reason,
        "persist_dir": get_settings().chroma_persist_dir,
        "collections": {},
    }
    if not index.enabled:
        return result
    for collection, memory_ids in target.memory_ids.items():
        collection_result: dict[str, Any] = {"total": None, "target_ids": {}}
        try:
            chroma_collection = index.collections[collection]
            collection_result["total"] = int(chroma_collection.count())
            for memory_id in memory_ids:
                collection_result["target_ids"][str(memory_id)] = chroma_get_count(
                    chroma_collection, memory_id
                )
        except Exception as exc:
            collection_result["error"] = f"{exc.__class__.__name__}: {exc}"
        result["collections"][collection] = collection_result
    return result


def delete_chroma_vectors(target: CleanupTarget) -> dict[str, Any]:
    index = ChromaMemoryIndex()
    result: dict[str, Any] = {
        "ok": True,
        "enabled": index.enabled,
        "fallback_reason": index.fallback_reason,
        "deleted": {},
    }
    if not index.enabled:
        result["ok"] = index.fallback_reason == "chroma_disabled"
        return result
    for collection, memory_ids in target.memory_ids.items():
        deleted: dict[str, Any] = {}
        for memory_id in memory_ids:
            before = chroma_get_count(index.collections[collection], memory_id)
            reason = index.delete_memory(collection, memory_id)
            after = chroma_get_count(index.collections[collection], memory_id)
            deleted[str(memory_id)] = {
                "before": before,
                "after": after,
                "reason": reason,
            }
            if reason is not None or after != 0:
                result["ok"] = False
        result["deleted"][collection] = deleted
    return result


def chroma_get_count(collection: Any, memory_id: int) -> int:
    result = collection.get(where={"memory_id": int(memory_id)}, include=[])
    return len(result.get("ids") or [])


def delete_mysql_records(
    connection: Any,
    target: CleanupTarget,
    *,
    keep_test_users: bool,
) -> dict[str, int]:
    deleted: dict[str, int] = {}
    with connection.cursor() as cursor:
        if target.trace_ids:
            deleted["harness_trace_events"] = delete_where(
                cursor, "harness_trace_events", "trace_id", target.trace_ids
            )
        deleted["harness_rule_evaluations"] = delete_ids(
            cursor, "harness_rule_evaluations", target.rule_ids
        )
        deleted["harness_checkpoints"] = delete_ids(
            cursor, "harness_checkpoints", target.checkpoint_ids
        )
        deleted["harness_improvement_candidates"] = delete_ids(
            cursor, "harness_improvement_candidates", target.improvement_ids
        )
        if target.interview_ids:
            cursor.execute(
                f"""
                UPDATE interviews
                SET last_checkpoint_id = NULL
                WHERE id IN ({placeholders(target.interview_ids)})
                """,
                tuple(target.interview_ids),
            )
        if target.trace_ids:
            cursor.execute(
                f"""
                UPDATE harness_traces
                SET source_trace_id = NULL
                WHERE source_trace_id IN ({placeholders(target.trace_ids)})
                """,
                tuple(target.trace_ids),
            )
        deleted["harness_traces"] = delete_ids(
            cursor, "harness_traces", target.trace_ids
        )
        deleted["rag_audit_logs"] = delete_ids(
            cursor, "rag_audit_logs", target.rag_audit_ids
        )
        deleted["memory_tasks"] = delete_ids(
            cursor, "memory_tasks", target.memory_task_ids
        )
        for collection, memory_ids in target.memory_ids.items():
            if memory_ids:
                cursor.execute(
                    f"""
                    UPDATE {collection}
                    SET superseded_by_id = NULL
                    WHERE superseded_by_id IN ({placeholders(memory_ids)})
                    """,
                    tuple(memory_ids),
                )
            deleted[collection] = delete_ids(cursor, collection, memory_ids)
        deleted["feedback_reports"] = delete_ids(
            cursor, "feedback_reports", target.feedback_ids
        )
        if table_exists(cursor, "skill_call_traces"):
            deleted["skill_call_traces"] = delete_ids(
                cursor, "skill_call_traces", target.skill_trace_ids
            )
        deleted["evaluation_records"] = delete_ids(
            cursor, "evaluation_records", target.evaluation_ids
        )
        if target.interview_ids:
            cursor.execute(
                f"""
                UPDATE interview_qa
                SET parent_question_id = NULL
                WHERE interview_id IN ({placeholders(target.interview_ids)})
                """,
                tuple(target.interview_ids),
            )
        deleted["interview_qa"] = delete_ids(cursor, "interview_qa", target.qa_ids)
        deleted["interview_rounds"] = delete_ids(
            cursor, "interview_rounds", target.round_ids
        )
        deleted["interviews"] = delete_ids(cursor, "interviews", target.interview_ids)
        if not keep_test_users:
            deleted["resumes"] = delete_ids(cursor, "resumes", target.resume_ids)
            deleted["users"] = delete_ids(cursor, "users", target.test_user_ids)
    return deleted


def inspect_files(*, delete: bool) -> dict[str, Any]:
    results: dict[str, Any] = {"delete": delete, "targets": []}
    for item in SAFE_FILE_TARGETS:
        matches = list(PROJECT_ROOT.glob(item))
        for path in sorted(matches):
            record: dict[str, Any] = {
                "path": str(path),
                "exists_before": path.exists(),
                "deleted": False,
            }
            if delete and path.exists():
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    record["deleted"] = True
                    record["exists_after"] = path.exists()
                except Exception as exc:
                    record["error"] = f"{exc.__class__.__name__}: {exc}"
                    record["exists_after"] = path.exists()
            results["targets"].append(record)
    return results


def collect_retained_summary(connection: Any, target: CleanupTarget) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM users")
        users = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM interviews")
        interviews = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM resumes")
        resumes = int(cursor.fetchone()["n"])
        cursor.execute(
            """
            SELECT id, username
            FROM users
            WHERE id NOT IN ({})
            ORDER BY id
            LIMIT 20
            """.format(
                placeholders(target.test_user_ids) if target.test_user_ids else "0"
            ),
            tuple(target.test_user_ids),
        )
        sample_users = cursor.fetchall()
    return {
        "total_users": users,
        "total_resumes": resumes,
        "total_interviews": interviews,
        "sample_non_target_users": sample_users,
    }


def collect_orphan_checks(connection: Any) -> dict[str, int]:
    checks = {
        "interviews_without_user": """
            SELECT COUNT(*) AS n FROM interviews i
            LEFT JOIN users u ON u.id = i.user_id
            WHERE u.id IS NULL
        """,
        "interviews_without_resume": """
            SELECT COUNT(*) AS n FROM interviews i
            LEFT JOIN resumes r ON r.id = i.resume_id
            WHERE r.id IS NULL
        """,
        "rounds_without_interview": """
            SELECT COUNT(*) AS n FROM interview_rounds r
            LEFT JOIN interviews i ON i.id = r.interview_id
            WHERE i.id IS NULL
        """,
        "qa_without_interview": """
            SELECT COUNT(*) AS n FROM interview_qa qa
            LEFT JOIN interviews i ON i.id = qa.interview_id
            WHERE i.id IS NULL
        """,
        "qa_without_round": """
            SELECT COUNT(*) AS n FROM interview_qa qa
            LEFT JOIN interview_rounds r ON r.id = qa.round_id
            WHERE qa.round_id IS NOT NULL AND r.id IS NULL
        """,
        "feedback_without_interview": """
            SELECT COUNT(*) AS n FROM feedback_reports fr
            LEFT JOIN interviews i ON i.id = fr.interview_id
            WHERE i.id IS NULL
        """,
        "evaluation_without_interview": """
            SELECT COUNT(*) AS n FROM evaluation_records er
            LEFT JOIN interviews i ON i.id = er.interview_id
            WHERE i.id IS NULL
        """,
        "harness_trace_without_interview": """
            SELECT COUNT(*) AS n FROM harness_traces ht
            LEFT JOIN interviews i ON i.id = ht.interview_id
            WHERE i.id IS NULL
        """,
        "harness_event_without_trace": """
            SELECT COUNT(*) AS n FROM harness_trace_events e
            LEFT JOIN harness_traces ht ON ht.id = e.trace_id
            WHERE ht.id IS NULL
        """,
    }
    with connection.cursor() as cursor:
        result = {}
        for name, query in checks.items():
            cursor.execute(query)
            result[name] = int(cursor.fetchone()["n"])
    return result


def filters_payload(
    args: argparse.Namespace,
    markers: list[str],
    username_patterns: list[str],
) -> dict[str, Any]:
    return {
        "execute": args.execute,
        "dry_run": not args.execute or args.dry_run,
        "exact_usernames": args.username,
        "explicit_user_ids": args.user_id,
        "username_like": username_patterns,
        "batch_marks": markers,
        "explicit_interview_ids": args.interview_id,
        "keep_test_users": args.keep_test_users,
        "clean_files": args.clean_files,
    }


def target_payload(target: CleanupTarget) -> dict[str, Any]:
    return {
        "test_user_ids": target.test_user_ids,
        "test_usernames": target.test_usernames,
        "interview_ids": target.interview_ids,
        "round_ids": target.round_ids,
        "qa_ids": target.qa_ids,
        "trace_ids": target.trace_ids,
        "skill_trace_ids": target.skill_trace_ids,
        "checkpoint_ids": target.checkpoint_ids,
        "replay_ids": target.replay_ids,
        "rule_ids": target.rule_ids,
        "improvement_ids": target.improvement_ids,
        "feedback_ids": target.feedback_ids,
        "evaluation_ids": target.evaluation_ids,
        "memory_task_ids": target.memory_task_ids,
        "rag_audit_ids": target.rag_audit_ids,
        "resume_ids": target.resume_ids,
        "memory_ids": target.memory_ids,
    }


def count_ids(cursor: Any, table: str, ids: list[int]) -> int:
    if not ids:
        return 0
    id_placeholders = placeholders(ids)
    cursor.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE id IN ({id_placeholders})",
        tuple(ids),
    )
    return int(cursor.fetchone()["n"])


def count_where(cursor: Any, table: str, column: str, values: list[int]) -> int:
    if not values:
        return 0
    cursor.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE {column} IN ({placeholders(values)})",
        tuple(values),
    )
    return int(cursor.fetchone()["n"])


def select_ids(cursor: Any, query_template: str, ids: list[int]) -> list[int]:
    if not ids:
        return []
    cursor.execute(query_template.format(placeholders(ids)), tuple(ids))
    return [int(row["id"]) for row in cursor.fetchall()]


def table_exists(cursor: Any, table: str) -> bool:
    cursor.execute("SHOW TABLES LIKE %s", (table,))
    return cursor.fetchone() is not None


def delete_ids(cursor: Any, table: str, ids: list[int]) -> int:
    if not ids:
        return 0
    cursor.execute(f"DELETE FROM {table} WHERE id IN ({placeholders(ids)})", tuple(ids))
    return int(cursor.rowcount)


def delete_where(cursor: Any, table: str, column: str, values: list[int]) -> int:
    if not values:
        return 0
    cursor.execute(
        f"DELETE FROM {table} WHERE {column} IN ({placeholders(values)})",
        tuple(values),
    )
    return int(cursor.rowcount)


def placeholders(values: list[Any]) -> str:
    if not values:
        raise ValueError("empty placeholder list")
    return ",".join(["%s"] * len(values))


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    main()
