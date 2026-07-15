from __future__ import annotations

# ruff: noqa: E402
import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.registry import ROUND_ORDER
from app.db.mysql import mysql_connection
from app.repositories.evaluations import EvaluationRepository
from app.repositories.interviews import InterviewRepository
from app.repositories.memories import MemoryRepository
from app.repositories.memory_tasks import MemoryTaskRepository
from app.repositories.preferences import PreferencesRepository
from app.repositories.rag_audit import RagAuditRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.users import UserRepository
from app.schemas.memory import MemoryRetrievalRequest
from app.services.evaluations import EvaluationSchedulerService
from app.services.interviews import InterviewService
from app.services.llm import get_llm_client
from app.services.memory_index import ChromaMemoryIndex
from app.services.memory_retrieval import MemoryRetrievalService
from app.services.memory_tasks import MemoryTaskRunner, MemoryTaskService

EVAL_MARK = "memory_real_eval_20260618"
REPORT_PATH = Path(r"E:\CodexWorkSpace\MEMORY_REAL_MULTI_ROUND_EVALUATION_REPORT.md")
TARGET_POSITION = f"后端开发工程师-{EVAL_MARK}"
JOB_DESCRIPTION = (
    f"{EVAL_MARK} 真实记忆评测。请围绕 FastAPI、MySQL、Vue、多 Agent 面试系统、"
    "记忆总结、向量索引和跨会话召回进行提问。"
)
ANSWER_TEMPLATE = (
    "{mark} 第 {index} 次回答：我不清楚这个问题的关键原理，也没有可量化的真实案例。"
    "如果需要我会后续复盘，但当前只能给出很笼统的描述。"
)
COLLECTIONS = ("candidate_memories", "interviewer_memories", "agent_memories")


@dataclass
class EvalState:
    run_id: str
    username: str
    user_id: int | None = None
    resume_id: int | None = None
    original_memory_enabled: bool | None = None
    baseline: dict[str, Any] = field(default_factory=dict)
    precleanup: dict[str, Any] = field(default_factory=dict)
    created_interview_ids: list[int] = field(default_factory=list)
    created_round_ids: list[int] = field(default_factory=list)
    created_qa_ids: list[int] = field(default_factory=list)
    final_report: dict[str, Any] | None = None
    memory_task: dict[str, Any] | None = None
    memory_counts: dict[str, Any] = field(default_factory=dict)
    retrieval: dict[str, Any] = field(default_factory=dict)
    cleanup: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    baseline_memory_snapshot: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the real InterviewArena memory evaluation flow."
    )
    parser.add_argument("--username", default="gy", help="Existing account to evaluate.")
    parser.add_argument("--resume-id", type=int, default=None, help="Existing resume id.")
    parser.add_argument("--report-path", default=str(REPORT_PATH), help="Markdown report path.")
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Keep generated rows for manual inspection. The report still lists cleanup targets.",
    )
    parser.add_argument(
        "--max-task-runs",
        type=int,
        default=6,
        help="Maximum MemoryTaskRunner.run_once attempts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state = EvalState(
        run_id=f"{EVAL_MARK}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        username=args.username,
    )
    report_path = Path(args.report_path)

    try:
        run_evaluation(state, args)
    except Exception as exc:
        state.errors.append(_safe_error(exc))
        raise
    finally:
        state.finished_at = datetime.utcnow()
        write_report(report_path, state)
        print(f"report_path={report_path}")


def run_evaluation(state: EvalState, args: argparse.Namespace) -> None:
    with mysql_connection() as connection:
        user = UserRepository(connection).get_by_username(state.username)
        if user is None:
            raise RuntimeError(f"User not found: {state.username}")
        resumes = ResumeRepository(connection).list_by_user(user.id)
        resume = _select_resume(resumes, args.resume_id)
        state.user_id = user.id
        state.resume_id = resume.id
        preferences = PreferencesRepository(connection)
        state.original_memory_enabled = preferences.get_memory_enabled(user.id)
        state.baseline = collect_baseline(connection, user.id)
        state.baseline_memory_snapshot = collect_memory_snapshot(connection, user.id)
        state.baseline["memory_integrity"] = memory_snapshot_summary(
            state.baseline_memory_snapshot
        )
        state.precleanup = cleanup_eval_data(connection, user.id, dry_run=args.skip_cleanup)
        if not preferences.get_memory_enabled(user.id):
            preferences.update_memory_enabled(user.id, True)

    try:
        llm_client = get_llm_client()
        with mysql_connection() as connection:
            service = build_interview_service(connection, llm_client)
            interview = service.create_interview(
                user_id=state.user_id,
                resume_id=state.resume_id,
                target_position=TARGET_POSITION,
                job_description=f"{JOB_DESCRIPTION}\nrun_id={state.run_id}",
                selected_rounds=list(ROUND_ORDER),
            )
            state.created_interview_ids.append(interview.id)
            for round_record in service.list_rounds(interview):
                state.created_round_ids.append(round_record.id)
                _complete_round(service, state.user_id, interview.id, round_record.id)
            report = service.finish_interview(state.user_id, interview.id, finish_type="normal")
            state.final_report = report.model_dump()
            _refresh_created_ids(connection, state)

        state.memory_task = run_memory_task(state.created_interview_ids[0], args.max_task_runs)
        state.memory_counts = collect_eval_memory_counts(state.created_interview_ids)
        changes = collect_preexisting_memory_changes(state)
        state.memory_counts["preexisting_memory_changes"] = changes
        if any(changes.values()):
            state.errors.append("Pre-existing memory rows changed during evaluation.")
        state.retrieval = run_retrieval_probe(state)
    finally:
        try:
            with mysql_connection() as connection:
                preferences = PreferencesRepository(connection)
                if state.original_memory_enabled is not None:
                    preferences.update_memory_enabled(state.user_id, state.original_memory_enabled)
                state.cleanup = cleanup_eval_data(
                    connection,
                    state.user_id,
                    dry_run=args.skip_cleanup,
                )
        except Exception as exc:
            state.errors.append(f"cleanup failed: {_safe_error(exc)}")


def build_interview_service(connection: Any, llm_client: Any) -> InterviewService:
    interview_repository = InterviewRepository(connection)
    return InterviewService(
        interview_repository,
        llm_client,
        EvaluationSchedulerService(EvaluationRepository(connection), llm_client),
        MemoryTaskService(MemoryTaskRepository(connection), PreferencesRepository(connection)),
        MemoryRetrievalService(
            memory_repository=MemoryRepository(connection),
            audit_repository=RagAuditRepository(connection),
        ),
        PreferencesRepository(connection),
    )


def _select_resume(resumes: list[Any], resume_id: int | None) -> Any:
    if resume_id is not None:
        for resume in resumes:
            if resume.id == resume_id:
                return resume
        raise RuntimeError(f"Resume not found for current user: {resume_id}")
    if not resumes:
        raise RuntimeError("No existing resume found for the evaluation user.")
    return resumes[0]


def _complete_round(
    service: InterviewService,
    user_id: int,
    interview_id: int,
    round_id: int,
) -> None:
    question_response = service.start_round(user_id, interview_id, round_id)
    question = question_response
    for index in range(1, 5):
        answer = ANSWER_TEMPLATE.format(mark=EVAL_MARK, index=index)
        response = service.answer_round_question(
            user_id=user_id,
            interview_id=interview_id,
            round_id=round_id,
            question_id=question.id,
            answer=answer,
        )
        if response.action == "finish_round":
            return
        if response.question is None:
            break
        question = response.question
    service.finish_round(user_id, interview_id, round_id, finish_type="normal")


def run_memory_task(interview_id: int, max_runs: int) -> dict[str, Any]:
    task_id = _memory_task_id(interview_id)
    if task_id is None:
        return {"status": "missing", "interview_id": interview_id}
    for _ in range(max(1, max_runs)):
        with mysql_connection() as connection:
            tasks = MemoryTaskRepository(connection)
            task = tasks.get_by_id(task_id)
            if task is None:
                return {"status": "missing", "interview_id": interview_id, "task_id": task_id}
            if task.status in {"completed", "failed"}:
                return _json_safe(task.__dict__)
            _mark_task_processing(connection, task.id)
            task = tasks.get_by_id(task.id)
            if task is None:
                return {"status": "missing", "interview_id": interview_id, "task_id": task_id}
            try:
                result = MemoryTaskRunner()._handle_task(connection, task)
                tasks.mark_completed(task.id, result)
            except Exception as exc:
                tasks.mark_failed_or_retry(task, _safe_error(exc))
        task_snapshot = _memory_task_snapshot(interview_id)
        if task_snapshot and task_snapshot.get("status") in {"completed", "failed"}:
            return task_snapshot
        time.sleep(1)
    return _memory_task_snapshot(interview_id) or {
        "status": "missing",
        "interview_id": interview_id,
    }


def _memory_task_id(interview_id: int) -> int | None:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM memory_tasks
                WHERE task_type = 'memory_summary' AND interview_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (interview_id,),
            )
            row = cursor.fetchone()
    return int(row["id"]) if row else None


def _mark_task_processing(connection: Any, task_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE memory_tasks
            SET status = 'processing', started_at = UTC_TIMESTAMP(), error_message = NULL
            WHERE id = %s
            """,
            (task_id,),
        )


def _memory_task_snapshot(interview_id: int) -> dict[str, Any] | None:
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_type, user_id, interview_id, status, retry_count,
                       max_retries, error_message, result, started_at, completed_at
                FROM memory_tasks
                WHERE task_type = 'memory_summary' AND interview_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (interview_id,),
            )
            row = cursor.fetchone()
    return _json_safe(row) if row else None


def run_retrieval_probe(state: EvalState) -> dict[str, Any]:
    result: dict[str, Any] = {}
    with mysql_connection() as connection:
        retrieval_service = MemoryRetrievalService(
            memory_repository=MemoryRepository(connection),
            audit_repository=RagAuditRepository(connection),
        )
        retrieved = retrieval_service.retrieve(
            MemoryRetrievalRequest(
                user_id=state.user_id,
                memory_enabled=True,
                interview_id=state.created_interview_ids[0],
                round_id=None,
                agent_type="technical",
                usage_scene="new_question",
                intent="验证本次真实评测写入的候选人长期记忆是否可被技术面召回。",
                query_text=f"{EVAL_MARK} 候选人技术薄弱点 不知道 不清楚",
                collections=["candidate_memories"],
                top_k=5,
            )
        )
        result["direct_retrieval"] = {
            "request_id": retrieved.request_id,
            "hit_count": len(retrieved.memories),
            "memory_ids": [item.memory_id for item in retrieved.memories],
            "fallback_reason": retrieved.fallback_reason,
        }

        service = build_interview_service(connection, get_llm_client())
        probe = service.create_interview(
            user_id=state.user_id,
            resume_id=state.resume_id,
            target_position=TARGET_POSITION,
            job_description=f"{JOB_DESCRIPTION}\nprobe_for={state.run_id}",
            selected_rounds=["technical"],
        )
        state.created_interview_ids.append(probe.id)
        technical_round = service.list_rounds(probe)[0]
        state.created_round_ids.append(technical_round.id)
        question = service.start_round(state.user_id, probe.id, technical_round.id)
        state.created_qa_ids.append(question.id)
        result["business_probe"] = latest_audit_snapshot(connection, probe.id)
        result["business_probe"]["interview_id"] = probe.id
        result["business_probe"]["round_id"] = technical_round.id
        result["business_probe"]["question_id"] = question.id
    return result


def collect_baseline(connection: Any, user_id: int) -> dict[str, Any]:
    baseline = {
        "user_id": user_id,
        "memory_enabled": PreferencesRepository(connection).get_memory_enabled(user_id),
        "counts": {},
        "vector_counts": vector_counts(),
        "eval_residue": eval_residue_counts(connection, user_id),
    }
    with connection.cursor() as cursor:
        for name, query, params in [
            ("interviews", "SELECT COUNT(*) AS n FROM interviews WHERE user_id = %s", (user_id,)),
            (
                "candidate_memories",
                "SELECT COUNT(*) AS n FROM candidate_memories WHERE user_id = %s",
                (user_id,),
            ),
            (
                "memory_tasks",
                "SELECT COUNT(*) AS n FROM memory_tasks WHERE user_id = %s",
                (user_id,),
            ),
            (
                "rag_audit_logs",
                "SELECT COUNT(*) AS n FROM rag_audit_logs WHERE user_id = %s",
                (user_id,),
            ),
        ]:
            cursor.execute(query, params)
            baseline["counts"][name] = int(cursor.fetchone()["n"])
    return baseline


def collect_memory_snapshot(connection: Any, user_id: int) -> dict[str, dict[int, dict[str, Any]]]:
    snapshot: dict[str, dict[int, dict[str, Any]]] = {}
    with connection.cursor() as cursor:
        for collection in COLLECTIONS:
            if collection == "candidate_memories":
                cursor.execute(
                    """
                    SELECT id, version, updated_at, source_interview_id, title, content
                    FROM candidate_memories
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT id, version, updated_at, source_interview_id, title, content
                    FROM {collection}
                    """
                )
            rows = cursor.fetchall()
            snapshot[collection] = {
                int(row["id"]): {
                    "version": int(row.get("version") or 0),
                    "updated_at": _format_dt(row.get("updated_at")),
                    "source_interview_id": row.get("source_interview_id"),
                    "content_hash": _content_hash(row.get("title"), row.get("content")),
                }
                for row in rows
            }
    return snapshot


def memory_snapshot_summary(snapshot: dict[str, dict[int, dict[str, Any]]]) -> dict[str, Any]:
    return {
        collection: {
            "count": len(rows),
            "fingerprint": _content_hash(
                collection,
                json.dumps(rows, ensure_ascii=False, sort_keys=True),
            ),
        }
        for collection, rows in snapshot.items()
    }


def collect_preexisting_memory_changes(state: EvalState) -> dict[str, list[int]]:
    if state.user_id is None:
        return {}
    with mysql_connection() as connection:
        current = collect_memory_snapshot(connection, state.user_id)
    changes: dict[str, list[int]] = {}
    for collection, before_rows in state.baseline_memory_snapshot.items():
        current_rows = current.get(collection, {})
        changed_ids = [
            memory_id
            for memory_id, before in before_rows.items()
            if memory_id in current_rows and current_rows[memory_id] != before
        ]
        changes[collection] = changed_ids
    return changes


def eval_residue_counts(connection: Any, user_id: int) -> dict[str, int]:
    interview_ids = find_eval_interview_ids(connection, user_id)
    memory_ids = find_eval_memory_ids(connection, interview_ids)
    counts = {"interviews": len(interview_ids)}
    counts.update({f"{collection}_by_source": len(ids) for collection, ids in memory_ids.items()})
    with connection.cursor() as cursor:
        if interview_ids:
            params = tuple(interview_ids)
            placeholder = _placeholders(interview_ids)
            for table in [
                "interview_rounds",
                "interview_qa",
                "feedback_reports",
                "evaluation_records",
                "memory_tasks",
                "rag_audit_logs",
                "harness_traces",
                "harness_checkpoints",
                "harness_rule_evaluations",
            ]:
                cursor.execute(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE interview_id IN ({placeholder})",
                    params,
                )
                counts[table] = int(cursor.fetchone()["n"])
    return counts


def collect_eval_memory_counts(interview_ids: list[int]) -> dict[str, Any]:
    with mysql_connection() as connection:
        memory_ids = find_eval_memory_ids(connection, interview_ids)
        rows: dict[str, list[dict[str, Any]]] = {}
        with connection.cursor() as cursor:
            for collection, ids in memory_ids.items():
                if not ids:
                    rows[collection] = []
                    continue
                cursor.execute(
                    f"""
                    SELECT id, memory_type, title, confidence, status, index_status,
                           source_interview_id
                    FROM {collection}
                    WHERE id IN ({_placeholders(ids)})
                    ORDER BY id
                    """,
                    tuple(ids),
                )
                rows[collection] = [_json_safe(row) for row in cursor.fetchall()]
    return {
        "mysql": rows,
        "vector_counts": vector_counts(),
        "eval_memory_ids": memory_ids,
    }


def latest_audit_snapshot(connection: Any, interview_id: int) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT request_id, candidate_memory_ids, injected_memory_ids, hit_count,
                   fallback_reason, embedding_version, reranker_version, prompt_version
            FROM rag_audit_logs
            WHERE interview_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (interview_id,),
        )
        row = cursor.fetchone()
    if not row:
        return {"hit_count": 0, "candidate_memory_ids": [], "injected_memory_ids": []}
    return _json_safe(row)


def cleanup_eval_data(connection: Any, user_id: int, *, dry_run: bool) -> dict[str, Any]:
    interview_ids = find_eval_interview_ids(connection, user_id)
    memory_ids = find_eval_memory_ids(connection, interview_ids)
    cleanup: dict[str, Any] = {
        "dry_run": dry_run,
        "interview_ids": interview_ids,
        "memory_ids": memory_ids,
        "deleted": {},
        "manual_cleanup": manual_cleanup_candidates(connection, user_id),
    }
    if dry_run or not interview_ids:
        return cleanup

    for collection, ids in memory_ids.items():
        delete_vectors(collection, ids)

    with connection.cursor() as cursor:
        for collection, ids in memory_ids.items():
            cleanup["deleted"][collection] = _delete_by_ids(cursor, collection, ids)
        trace_ids = _ids_by_interviews(cursor, "harness_traces", interview_ids)
        cleanup["deleted"]["harness_trace_events"] = _delete_trace_events(cursor, trace_ids)
        cleanup["deleted"]["harness_rule_evaluations"] = _delete_by_interviews(
            cursor, "harness_rule_evaluations", interview_ids
        )
        cleanup["deleted"]["harness_checkpoints"] = _delete_by_interviews(
            cursor, "harness_checkpoints", interview_ids
        )
        _null_trace_sources(cursor, trace_ids)
        cleanup["deleted"]["harness_traces"] = _delete_by_interviews(
            cursor, "harness_traces", interview_ids
        )
        for table in [
            "rag_audit_logs",
            "memory_tasks",
            "feedback_reports",
            "evaluation_records",
        ]:
            cleanup["deleted"][table] = _delete_by_interviews(cursor, table, interview_ids)
        _clear_qa_parent_links(cursor, interview_ids)
        cleanup["deleted"]["interview_qa"] = _delete_by_interviews(
            cursor, "interview_qa", interview_ids
        )
        cleanup["deleted"]["interview_rounds"] = _delete_by_interviews(
            cursor, "interview_rounds", interview_ids
        )
        cleanup["deleted"]["interviews"] = _delete_by_ids(cursor, "interviews", interview_ids)
    cleanup["postcheck"] = eval_residue_counts(connection, user_id)
    return cleanup


def find_eval_interview_ids(connection: Any, user_id: int) -> list[int]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM interviews
            WHERE user_id = %s
              AND (target_position LIKE %s OR job_description LIKE %s)
            ORDER BY id
            """,
            (user_id, f"%{EVAL_MARK}%", f"%{EVAL_MARK}%"),
        )
        return [int(row["id"]) for row in cursor.fetchall()]


def find_eval_memory_ids(connection: Any, interview_ids: list[int]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {collection: [] for collection in COLLECTIONS}
    if not interview_ids:
        return result
    with connection.cursor() as cursor:
        for collection in COLLECTIONS:
            cursor.execute(
                f"""
                SELECT id
                FROM {collection}
                WHERE source_interview_id IN ({_placeholders(interview_ids)})
                ORDER BY id
                """,
                tuple(interview_ids),
            )
            result[collection] = [int(row["id"]) for row in cursor.fetchall()]
    return result


def manual_cleanup_candidates(connection: Any, user_id: int) -> dict[str, list[int]]:
    candidates: dict[str, list[int]] = {}
    with connection.cursor() as cursor:
        for collection in COLLECTIONS:
            where_user = "user_id = %s AND" if collection == "candidate_memories" else ""
            params: list[Any] = [user_id] if collection == "candidate_memories" else []
            params.extend([f"%{EVAL_MARK}%", f"%{EVAL_MARK}%", f"%{EVAL_MARK}%"])
            cursor.execute(
                f"""
                SELECT id
                FROM {collection}
                WHERE {where_user}
                      source_interview_id IS NULL
                  AND (
                      title LIKE %s
                      OR content LIKE %s
                      OR CAST(structured_data AS CHAR) LIKE %s
                  )
                ORDER BY id
                """,
                tuple(params),
            )
            candidates[collection] = [int(row["id"]) for row in cursor.fetchall()]
    return candidates


def vector_counts() -> dict[str, Any]:
    index = ChromaMemoryIndex()
    if not index.enabled:
        return {"enabled": False, "fallback_reason": index.fallback_reason}
    counts: dict[str, Any] = {"enabled": True}
    for collection in COLLECTIONS:
        try:
            counts[collection] = int(index.collections[collection].count())
        except Exception as exc:
            counts[collection] = f"error:{exc.__class__.__name__}"
    return counts


def delete_vectors(collection: str, ids: list[int]) -> None:
    if not ids:
        return
    index = ChromaMemoryIndex()
    if not index.enabled:
        return
    for memory_id in ids:
        index.delete_memory(collection, memory_id)


def _refresh_created_ids(connection: Any, state: EvalState) -> None:
    if not state.created_interview_ids:
        return
    with connection.cursor() as cursor:
        placeholder = _placeholders(state.created_interview_ids)
        params = tuple(state.created_interview_ids)
        cursor.execute(
            f"SELECT id FROM interview_rounds WHERE interview_id IN ({placeholder}) ORDER BY id",
            params,
        )
        state.created_round_ids = [int(row["id"]) for row in cursor.fetchall()]
        cursor.execute(
            f"SELECT id FROM interview_qa WHERE interview_id IN ({placeholder}) ORDER BY id",
            params,
        )
        state.created_qa_ids = [int(row["id"]) for row in cursor.fetchall()]


def _ids_by_interviews(cursor: Any, table: str, interview_ids: list[int]) -> list[int]:
    if not interview_ids:
        return []
    cursor.execute(
        f"SELECT id FROM {table} WHERE interview_id IN ({_placeholders(interview_ids)})",
        tuple(interview_ids),
    )
    return [int(row["id"]) for row in cursor.fetchall()]


def _delete_by_interviews(cursor: Any, table: str, interview_ids: list[int]) -> int:
    if not interview_ids:
        return 0
    cursor.execute(
        f"DELETE FROM {table} WHERE interview_id IN ({_placeholders(interview_ids)})",
        tuple(interview_ids),
    )
    return int(cursor.rowcount)


def _delete_by_ids(cursor: Any, table: str, ids: list[int]) -> int:
    if not ids:
        return 0
    cursor.execute(f"DELETE FROM {table} WHERE id IN ({_placeholders(ids)})", tuple(ids))
    return int(cursor.rowcount)


def _delete_trace_events(cursor: Any, trace_ids: list[int]) -> int:
    if not trace_ids:
        return 0
    cursor.execute(
        f"DELETE FROM harness_trace_events WHERE trace_id IN ({_placeholders(trace_ids)})",
        tuple(trace_ids),
    )
    return int(cursor.rowcount)


def _null_trace_sources(cursor: Any, trace_ids: list[int]) -> None:
    if not trace_ids:
        return
    cursor.execute(
        f"""
        UPDATE harness_traces
        SET source_trace_id = NULL
        WHERE source_trace_id IN ({_placeholders(trace_ids)})
        """,
        tuple(trace_ids),
    )


def _clear_qa_parent_links(cursor: Any, interview_ids: list[int]) -> None:
    if not interview_ids:
        return
    cursor.execute(
        f"""
        UPDATE interview_qa
        SET parent_question_id = NULL
        WHERE interview_id IN ({_placeholders(interview_ids)})
        """,
        tuple(interview_ids),
    )


def _placeholders(values: list[int]) -> str:
    return ",".join(["%s"] * len(values))


def write_report(path: Path, state: EvalState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(state), encoding="utf-8")


def render_report(state: EvalState) -> str:
    conclusion = "通过" if not state.errors and _cleanup_ok(state.cleanup) else "未通过"
    lines = [
        "# InterviewArena 真实多轮记忆评测报告",
        "",
        f"评测标识：`{EVAL_MARK}`",
        f"运行标识：`{state.run_id}`",
        f"报告时间：{_format_dt(state.finished_at)}",
        "",
        f"结论：{conclusion}",
        "",
        "## 基线采集",
        "",
        _json_block(state.baseline),
        "",
        "## 真实链路执行",
        "",
        f"- 用户 ID：`{state.user_id}`",
        f"- 简历 ID：`{state.resume_id}`",
        f"- 面试 ID：`{state.created_interview_ids}`",
        f"- 轮次 ID：`{state.created_round_ids}`",
        f"- 问答 ID：`{state.created_qa_ids}`",
        "",
        "## 最终报告结果",
        "",
        _json_block(state.final_report or {}),
        "",
        "## Memory Task",
        "",
        _json_block(state.memory_task or {}),
        "",
        "## 长期记忆与向量索引",
        "",
        _json_block(state.memory_counts),
        "",
        "## 跨会话召回与业务注入探测",
        "",
        _json_block(state.retrieval),
        "",
        "## 清理结果",
        "",
        _json_block(state.cleanup),
        "",
        "## 错误",
        "",
        _json_block(state.errors),
        "",
        "## 验收判断",
        "",
        "- 使用真实 MySQL、真实 LLM、真实 memory task、真实 Chroma/embedding 配置路径。",
        "- 评测数据通过 target_position/job_description 中的独立标识定位。",
        "- 自动清理只处理可由本次评测标识定位的 interview 及其依赖数据。",
        "- 不记录密码、Token、Cookie、API key 或数据库密码。",
    ]
    return "\n".join(lines) + "\n"


def _cleanup_ok(cleanup: dict[str, Any]) -> bool:
    postcheck = cleanup.get("postcheck")
    if not isinstance(postcheck, dict):
        return bool(cleanup.get("dry_run"))
    return all(int(value) == 0 for value in postcheck.values() if isinstance(value, int))


def _json_block(value: Any) -> str:
    return "```json\n" + json.dumps(_json_safe(value), ensure_ascii=False, indent=2) + "\n```"


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _format_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else ""


def _content_hash(*values: Any) -> str:
    text = "\n".join("" if value is None else str(value) for value in values)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _safe_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    redacted_words = ["authorization", "api_key", "token", "cookie", "password"]
    lowered = text.lower()
    if any(word in lowered for word in redacted_words):
        return f"{exc.__class__.__name__}: <redacted>"
    return f"{exc.__class__.__name__}: {text[:1000]}"


if __name__ == "__main__":
    main()
