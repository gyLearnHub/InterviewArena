from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.registry import ROUND_ORDER
from app.core.config import get_settings
from app.db.mysql import mysql_connection, parse_mysql_url
from app.repositories.interviews import InterviewRepository
from app.repositories.resumes import ResumeRepository
from app.repositories.users import UserRepository
from app.services.interviews import InterviewService
from app.services.llm import DeepSeekLLMClient
from scripts.migrate_v1 import migrate

SAFE_DATABASE_MARKERS = ("test", "smoke", "e2e")
SMOKE_MARK = "skill_smoke_e2e"
REQUIRED_SCHEMA_TABLES = (
    "users",
    "resumes",
    "interviews",
    "interview_rounds",
    "interview_qa",
    "skill_call_traces",
)
ROUND_LABELS = {
    "resume": "简历面",
    "technical": "技术面",
    "manager": "主管面",
    "hr": "HR 面",
}
TARGET_POSITION = f"{SMOKE_MARK} Agent 应用开发工程师"
JOB_DESCRIPTION = "".join(
    [
        f"{SMOKE_MARK}：负责 Python/FastAPI、MySQL、Vue、RAG、Agent 工具调用、",
        "多轮面试编排、评估与可观测性建设。",
    ]
)
ANSWER_BY_ROUND = {
    "resume": "我负责多轮面试状态机和 trace 记录，因为要保证恢复时问题、回答和轮次状态一致。",
    "technical": "我负责接口和数据库设计，因为需要权衡事务一致性、索引性能和 Agent 调用耗时。",
    "manager": "我推进过一次跨团队排期，对齐目标后拆分里程碑，最终让核心流程提前两天上线。",
    "hr": "我希望长期做 AI 应用工程化，关注 Agent 可靠性、评估体系和真实业务落地。",
}
RESUME_DATA: dict[str, Any] = {
    "basic_info": {"name": "Skill Smoke Candidate", "email": "skill-smoke@example.com"},
    "education": [
        {"school": "测试大学", "major": "软件工程", "start_date": "2018", "end_date": "2022"}
    ],
    "work_experience": [
        {
            "company": "SkillSmokeLab",
            "title": "后端与 Agent 应用开发工程师",
            "start_date": "2024",
            "end_date": "至今",
            "description": "负责 InterviewArena 多轮面试、技能信号和 Harness Trace。",
        }
    ],
    "project_experience": [
        {
            "name": "InterviewArena skill smoke",
            "role": "后端开发",
            "responsibility": "设计 skill 调用链、trace 记录和 Agent 上下文注入。",
            "result": "让每次提问前的确定性信号可回放、可追踪。",
        }
    ],
    "skills": ["Python", "FastAPI", "MySQL", "Vue", "RAG", "Agent", "pytest"],
    "certificates_awards": [],
}


@dataclass
class SmokeState:
    user_ids: list[int] = field(default_factory=list)
    resume_ids: list[int] = field(default_factory=list)
    interview_ids: list[int] = field(default_factory=list)


class DeterministicSmokeLLMClient:
    model_name = "skill-smoke-deterministic"

    def __init__(self) -> None:
        self.question_count = 0

    def parse_resume(self, resume_text: str) -> dict[str, Any]:
        raise AssertionError("smoke_skill_e2e uses a prebuilt structured resume.")

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        self.question_count += 1
        round_type = str(resume.get("_interview_round") or "unknown")
        stage = "追问" if previous_answer else "开场"
        skill_count = len(resume.get("_skill_context", {}).get("results", []))
        return {
            "question_type": f"{round_type}_skill_smoke",
            "question": (
                f"{ROUND_LABELS.get(round_type, round_type)}{stage} smoke {self.question_count}: "
                f"请结合 {target_position} 补充一个具体证据。skill_signals={skill_count}"
            ),
        }

    def generate_feedback(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {"score": 80, "weaknesses": [], "suggestions": []}

    def generate_json(
        self, system_prompt: str, user_payload: dict[str, Any]
    ) -> dict[str, Any]:
        if "candidate_skills" not in user_payload:
            return {}
        selected = []
        for candidate in user_payload["candidate_skills"]:
            selected.append(
                {
                    "name": candidate["name"],
                    "reason": "skill_smoke_deterministic_selection",
                }
            )
            if len(selected) >= int(user_payload.get("max_skills") or 2):
                break
        return {"selected_skills": selected}


class DeterministicSelectorLLMClient:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    @property
    def model_name(self) -> str:
        return (
            f"{getattr(self.delegate, 'model_name', 'unknown')}+deterministic-selector"
        )

    def parse_resume(self, resume_text: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.delegate.parse_resume(resume_text))

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.delegate.generate_question(
                resume=resume,
                target_position=target_position,
                qa_history=qa_history,
                previous_answer=previous_answer,
                system_prompt=system_prompt,
            ),
        )

    def generate_feedback(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.delegate.generate_feedback(resume, target_position, qa_history),
        )

    def generate_json(
        self, system_prompt: str, user_payload: dict[str, Any]
    ) -> dict[str, Any]:
        if "candidate_skills" not in user_payload:
            return cast(
                dict[str, Any], self.delegate.generate_json(system_prompt, user_payload)
            )
        selected = [
            {"name": item["name"], "reason": "skill_smoke_deterministic_selector"}
            for item in user_payload["candidate_skills"][
                : int(user_payload.get("max_skills") or 2)
            ]
        ]
        return {"selected_skills": selected}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a backend smoke E2E check for skill selection, execution, and traces."
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Test DB URL. Defaults to SKILL_SMOKE_DATABASE_URL, then DATABASE_URL/.env.",
    )
    parser.add_argument(
        "--print-setup-sql",
        action="store_true",
        help="Print SQL for creating/granting a default smoke database, then exit.",
    )
    parser.add_argument(
        "--allow-non-test-db",
        action="store_true",
        help="Allow DB names without test/smoke/e2e. Use only with an isolated database.",
    )
    parser.add_argument(
        "--round",
        action="append",
        choices=[*ROUND_ORDER, "all"],
        default=[],
        help="Round to smoke. Can be repeated. Default: all.",
    )
    parser.add_argument(
        "--fake-llm",
        action="store_true",
        help="Use a deterministic local LLM stub. This checks DB/service wiring only.",
    )
    parser.add_argument(
        "--deterministic-selector",
        action="store_true",
        help="Use real question generation but deterministic skill selection.",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Keep created smoke rows for manual inspection.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.print_setup_sql:
        print(build_setup_sql(args.database_url))
        return
    try:
        report = run_smoke(args)
    except Exception as exc:
        report = {
            "ok": False,
            "started_at": datetime.utcnow(),
            "finished_at": datetime.utcnow(),
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    print(json.dumps(json_safe(report), ensure_ascii=False, indent=2))
    if not report.get("ok"):
        raise SystemExit(1)


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    database_url = resolve_database_url(
        args.database_url, fallback_url=settings.database_url
    )
    database_name = assert_safe_database_url(
        database_url,
        allow_non_test_db=bool(args.allow_non_test_db),
    )
    rounds = normalize_rounds(args.round)
    state = SmokeState()
    report: dict[str, Any] = {
        "ok": False,
        "started_at": datetime.utcnow(),
        "database": database_name,
        "rounds": rounds,
        "llm_mode": llm_mode(args),
        "results": [],
        "cleanup": {},
    }
    with mysql_connection(database_url) as connection:
        try:
            ensure_smoke_schema(connection)
            migrate(connection)
            llm_client = build_llm_client(args)
            user = UserRepository(connection).create(
                username=f"{SMOKE_MARK}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
                password_hash="skill-smoke-not-a-real-password",
            )
            state.user_ids.append(user.id)
            resume = ResumeRepository(connection).create(
                user_id=user.id,
                original_file_path=f"{SMOKE_MARK}.json",
                structured_data=RESUME_DATA,
                content_hash=None,
            )
            state.resume_ids.append(resume.id)
            connection.commit()

            for round_type in rounds:
                result = run_round_smoke(
                    connection=connection,
                    llm_client=llm_client,
                    user_id=user.id,
                    resume_id=resume.id,
                    round_type=round_type,
                    state=state,
                )
                report["results"].append(result)
            report["ok"] = True
        except Exception as exc:
            report["error"] = f"{exc.__class__.__name__}: {exc}"
        finally:
            if args.keep_data:
                report["cleanup"] = {"skipped": True, "state": state.__dict__}
            else:
                try:
                    report["cleanup"] = cleanup_created_records(connection, state)
                except Exception as cleanup_exc:
                    report["ok"] = False
                    report["cleanup"] = {
                        "ok": False,
                        "error": f"{cleanup_exc.__class__.__name__}: {cleanup_exc}",
                        "state": state.__dict__,
                    }
        report["finished_at"] = datetime.utcnow()
    return report


def ensure_smoke_schema(connection: Any) -> None:
    missing = missing_tables(connection, REQUIRED_SCHEMA_TABLES)
    if not missing:
        return
    sql_path = BACKEND_ROOT.parent / "database" / "init_mysql.sql"
    statements = [
        statement.strip()
        for statement in sql_path.read_text(encoding="utf-8").split(";")
        if should_execute_schema_statement(statement)
    ]
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def should_execute_schema_statement(statement: str) -> bool:
    normalized = " ".join(statement.casefold().split())
    if not normalized:
        return False
    return "add column if not exists" not in normalized


def missing_tables(connection: Any, table_names: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    with connection.cursor() as cursor:
        for table_name in table_names:
            cursor.execute("SHOW TABLES LIKE %s", (table_name,))
            if cursor.fetchone() is None:
                missing.append(table_name)
    return missing


def run_round_smoke(
    *,
    connection: Any,
    llm_client: Any,
    user_id: int,
    resume_id: int,
    round_type: str,
    state: SmokeState,
) -> dict[str, Any]:
    repository = InterviewRepository(connection)
    service = InterviewService(repository=repository, llm_client=llm_client)
    interview = service.create_interview(
        user_id=user_id,
        resume_id=resume_id,
        target_position=TARGET_POSITION,
        job_description=JOB_DESCRIPTION,
        selected_rounds=[round_type],
    )
    state.interview_ids.append(interview.id)
    round_record = next(
        item for item in service.list_rounds(interview) if item.round_type == round_type
    )
    first_question = service.start_round(user_id, interview.id, round_record.id)
    answer = ANSWER_BY_ROUND[round_type]
    answer_result = service.answer_round_question(
        user_id=user_id,
        interview_id=interview.id,
        round_id=round_record.id,
        question_id=first_question.id,
        answer=answer,
    )
    if answer_result.question is None:
        raise AssertionError(f"{round_type} did not produce a next question.")
    refreshed_interview = repository.get_interview_for_user(interview.id, user_id)
    if refreshed_interview is not None and refreshed_interview.had_degradation:
        raise AssertionError(
            f"{round_type} smoke degraded: {refreshed_interview.last_harness_error}"
        )
    rows = fetch_skill_traces(connection, interview.id)
    trace_summary = validate_skill_traces(
        rows,
        expected_round_type=round_type,
        submitted_answer=answer,
    )
    return {
        "round_type": round_type,
        "interview_id": interview.id,
        "round_id": round_record.id,
        "first_question_id": first_question.id,
        "next_question_id": answer_result.question.id,
        "first_question_excerpt": first_question.question[:160],
        "next_question_excerpt": answer_result.question.question[:160],
        "harness_status": refreshed_interview.harness_status
        if refreshed_interview is not None
        else None,
        "trace_summary": trace_summary,
    }


def assert_safe_database_url(
    database_url: str, *, allow_non_test_db: bool = False
) -> str:
    config = parse_mysql_url(database_url)
    database = config.database
    if allow_non_test_db:
        return database
    normalized = database.casefold()
    if not any(marker in normalized for marker in SAFE_DATABASE_MARKERS):
        raise RuntimeError(
            "Refusing to run skill smoke against a non-test database. "
            "Use SKILL_SMOKE_DATABASE_URL with a database name containing "
            "test/smoke/e2e, or pass --allow-non-test-db only for an isolated DB."
        )
    return database


def resolve_database_url(
    cli_url: str,
    *,
    fallback_url: str,
    env_path: Path = BACKEND_ROOT / ".env",
) -> str:
    return (
        cli_url.strip()
        or os.getenv("SKILL_SMOKE_DATABASE_URL", "").strip()
        or env_file_value("SKILL_SMOKE_DATABASE_URL", env_path=env_path)
        or fallback_url
    )


def env_file_value(name: str, *, env_path: Path) -> str:
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("'\"")
    return ""


def build_setup_sql(
    database_url: str = "", *, database_name: str = "interview_arena_smoke"
) -> str:
    settings = get_settings()
    source_url = database_url.strip() or settings.database_url
    config = parse_mysql_url(source_url)
    return "\n".join(
        [
            (
                f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database_name)} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            ),
            (
                f"GRANT ALL PRIVILEGES ON {quote_identifier(database_name)}.* "
                f"TO {quote_literal(config.user)}@{quote_literal(config.host)};"
            ),
            "FLUSH PRIVILEGES;",
        ]
    )


def quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def quote_literal(value: str) -> str:
    return f"'{value.replace(chr(92), chr(92) + chr(92)).replace(chr(39), chr(92) + chr(39))}'"


def normalize_rounds(values: list[str]) -> list[str]:
    if not values or "all" in values:
        return list(ROUND_ORDER)
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def build_llm_client(args: argparse.Namespace) -> Any:
    if args.fake_llm:
        return DeterministicSmokeLLMClient()
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is required for real smoke E2E. "
            "Use --fake-llm only for local wiring rehearsal."
        )
    client: Any = DeepSeekLLMClient(settings=settings)
    if args.deterministic_selector:
        client = DeterministicSelectorLLMClient(client)
    return client


def llm_mode(args: argparse.Namespace) -> str:
    if args.fake_llm:
        return "fake_llm"
    if args.deterministic_selector:
        return "real_question_generation_deterministic_selector"
    return "real_llm"


def fetch_skill_traces(connection: Any, interview_id: int) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT trace_id, round_type, stage, skill_name, selection_source,
                   selection_reason, input_summary, output_summary, structured_signals,
                   confidence, llm_enhanced, elapsed_ms, error_message
            FROM skill_call_traces
            WHERE interview_id = %s
            ORDER BY id
            """,
            (interview_id,),
        )
        return [normalize_trace_row(row) for row in cursor.fetchall()]


def normalize_trace_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "input_summary": parse_json_field(row.get("input_summary")),
        "output_summary": parse_json_field(row.get("output_summary")),
        "structured_signals": parse_json_field(row.get("structured_signals")),
    }


def parse_json_field(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def validate_skill_traces(
    rows: list[dict[str, Any]],
    *,
    expected_round_type: str,
    submitted_answer: str,
) -> dict[str, Any]:
    if not rows:
        raise AssertionError("No skill_call_traces rows were written.")
    stage_counts = Counter(str(row.get("stage")) for row in rows)
    for stage in ("pre_question", "post_answer"):
        count = stage_counts.get(stage, 0)
        if count < 1:
            raise AssertionError(f"Missing {stage} skill trace.")
        if count > 2:
            raise AssertionError(f"{stage} skill trace count exceeds max 2: {count}.")
    grouped_by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("round_type") != expected_round_type:
            raise AssertionError(
                f"Unexpected trace round_type: {row.get('round_type')} != {expected_round_type}."
            )
        if row.get("error_message"):
            raise AssertionError(
                f"Skill {row.get('skill_name')} failed: {row.get('error_message')}"
            )
        if row.get("confidence") is None:
            raise AssertionError(f"Skill {row.get('skill_name')} has no confidence.")
        if int(row.get("elapsed_ms") or 0) < 0:
            raise AssertionError(
                f"Skill {row.get('skill_name')} has invalid elapsed_ms."
            )
        assert_no_full_context_leak(row, submitted_answer=submitted_answer)
        grouped_by_trace[str(row.get("trace_id"))].append(row)
    for trace_id, trace_rows in grouped_by_trace.items():
        if len(trace_rows) > 2:
            raise AssertionError(f"Trace {trace_id} selected more than 2 skills.")
    return {
        "row_count": len(rows),
        "stage_counts": dict(stage_counts),
        "skill_names": [str(row.get("skill_name")) for row in rows],
        "selection_sources": sorted({str(row.get("selection_source")) for row in rows}),
        "trace_ids": sorted(grouped_by_trace),
    }


def assert_no_full_context_leak(row: dict[str, Any], *, submitted_answer: str) -> None:
    input_summary = row.get("input_summary")
    input_text = json.dumps(input_summary, ensure_ascii=False, default=str)
    if len(input_text) > 1200:
        raise AssertionError(f"input_summary is too large for {row.get('skill_name')}.")
    if submitted_answer and submitted_answer in input_text:
        raise AssertionError(
            f"input_summary leaked full submitted answer for {row.get('skill_name')}."
        )
    if isinstance(input_summary, dict) and "answer" in input_summary:
        raise AssertionError(
            f"input_summary contains raw answer key for {row.get('skill_name')}."
        )


def cleanup_created_records(connection: Any, state: SmokeState) -> dict[str, Any]:
    if not state.user_ids and not state.interview_ids and not state.resume_ids:
        return {"ok": True, "deleted": {}}
    deleted: dict[str, int] = {}
    with connection.cursor() as cursor:
        trace_ids = select_ids_by_column(
            cursor, "harness_traces", "interview_id", state.interview_ids
        )
        deleted["skill_call_traces"] = delete_where(
            cursor, "skill_call_traces", "interview_id", state.interview_ids
        )
        deleted["harness_trace_events"] = delete_where(
            cursor, "harness_trace_events", "trace_id", trace_ids
        )
        deleted["harness_rule_evaluations"] = delete_where(
            cursor, "harness_rule_evaluations", "interview_id", state.interview_ids
        )
        deleted["harness_checkpoints"] = delete_where(
            cursor, "harness_checkpoints", "interview_id", state.interview_ids
        )
        deleted["harness_improvement_candidates"] = delete_where(
            cursor,
            "harness_improvement_candidates",
            "interview_id",
            state.interview_ids,
        )
        if state.interview_ids:
            cursor.execute(
                f"""
                UPDATE interviews
                SET last_checkpoint_id = NULL
                WHERE id IN ({placeholders(state.interview_ids)})
                """,
                tuple(state.interview_ids),
            )
        deleted["harness_traces"] = delete_ids(cursor, "harness_traces", trace_ids)
        deleted["rag_audit_logs"] = delete_where(
            cursor, "rag_audit_logs", "interview_id", state.interview_ids
        )
        deleted["memory_tasks"] = delete_where(
            cursor, "memory_tasks", "interview_id", state.interview_ids
        )
        deleted["feedback_reports"] = delete_where(
            cursor, "feedback_reports", "interview_id", state.interview_ids
        )
        deleted["evaluation_records"] = delete_where(
            cursor, "evaluation_records", "interview_id", state.interview_ids
        )
        if state.interview_ids:
            cursor.execute(
                f"""
                UPDATE interview_qa
                SET parent_question_id = NULL
                WHERE interview_id IN ({placeholders(state.interview_ids)})
                """,
                tuple(state.interview_ids),
            )
        deleted["interview_qa"] = delete_where(
            cursor, "interview_qa", "interview_id", state.interview_ids
        )
        deleted["interview_rounds"] = delete_where(
            cursor, "interview_rounds", "interview_id", state.interview_ids
        )
        deleted["interviews"] = delete_ids(cursor, "interviews", state.interview_ids)
        deleted["resumes"] = delete_ids(cursor, "resumes", state.resume_ids)
        deleted["users"] = delete_ids(cursor, "users", state.user_ids)
    return {"ok": True, "deleted": deleted}


def select_ids_by_column(
    cursor: Any, table: str, column: str, values: list[int]
) -> list[int]:
    if not values:
        return []
    cursor.execute(
        f"SELECT id FROM {table} WHERE {column} IN ({placeholders(values)}) ORDER BY id",
        tuple(values),
    )
    return [int(row["id"]) for row in cursor.fetchall()]


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


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    main()
