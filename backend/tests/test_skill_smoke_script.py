from __future__ import annotations

import pytest
from scripts.smoke_skill_e2e import (
    assert_safe_database_url,
    build_setup_sql,
    env_file_value,
    normalize_rounds,
    resolve_database_url,
    should_execute_schema_statement,
    validate_skill_traces,
)


def test_skill_smoke_rejects_non_test_database_by_default() -> None:
    with pytest.raises(RuntimeError):
        assert_safe_database_url(
            "mysql+pymysql://user:pass@127.0.0.1:3306/interview_arena?charset=utf8mb4"
        )


def test_skill_smoke_allows_named_test_database() -> None:
    database = assert_safe_database_url(
        "mysql+pymysql://user:pass@127.0.0.1:3306/interview_arena_smoke"
    )

    assert database == "interview_arena_smoke"


def test_skill_smoke_normalizes_rounds() -> None:
    assert normalize_rounds([]) == ["resume", "technical", "manager", "hr"]
    assert normalize_rounds(["technical", "technical", "hr"]) == ["technical", "hr"]


def test_skill_smoke_reads_database_url_from_env_file(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DATABASE_URL=mysql+pymysql://main:pass@127.0.0.1:3306/interview_arena\n"
        "SKILL_SMOKE_DATABASE_URL='mysql+pymysql://smoke:pass@127.0.0.1:3306/interview_arena_smoke'\n",
        encoding="utf-8",
    )

    assert (
        env_file_value("SKILL_SMOKE_DATABASE_URL", env_path=env_path)
        == "mysql+pymysql://smoke:pass@127.0.0.1:3306/interview_arena_smoke"
    )
    assert resolve_database_url(
        "",
        fallback_url="mysql+pymysql://main:pass@127.0.0.1:3306/interview_arena",
        env_path=env_path,
    ).endswith("/interview_arena_smoke")


def test_skill_smoke_setup_sql_uses_default_smoke_database() -> None:
    sql = build_setup_sql(
        "mysql+pymysql://interview_arena:change_me@127.0.0.1:3306/interview_arena"
    )

    assert "CREATE DATABASE IF NOT EXISTS `interview_arena_smoke`" in sql
    assert "GRANT ALL PRIVILEGES ON `interview_arena_smoke`.*" in sql
    assert "'interview_arena'@'127.0.0.1'" in sql


def test_skill_smoke_schema_init_skips_mysql_incompatible_add_column_if_not_exists() -> (
    None
):
    assert should_execute_schema_statement("CREATE TABLE IF NOT EXISTS users (id int)")
    assert not should_execute_schema_statement(
        """
        ALTER TABLE interviews
            ADD COLUMN IF NOT EXISTS harness_status VARCHAR(32) NULL
        """
    )


def test_skill_smoke_validates_trace_shape_and_limits() -> None:
    rows = [
        _trace("trace-pre", "pre_question", "context_summary"),
        _trace("trace-pre", "pre_question", "technical_gap_mapper"),
        _trace("trace-post", "post_answer", "answer_quality_probe"),
        _trace("trace-post", "post_answer", "technical_depth_probe"),
    ]

    summary = validate_skill_traces(
        rows,
        expected_round_type="technical",
        submitted_answer="我负责接口和数据库设计，因为需要权衡事务一致性。",
    )

    assert summary["stage_counts"] == {"pre_question": 2, "post_answer": 2}
    assert summary["skill_names"] == [
        "context_summary",
        "technical_gap_mapper",
        "answer_quality_probe",
        "technical_depth_probe",
    ]


def test_skill_smoke_rejects_full_answer_in_input_summary() -> None:
    answer = "我负责接口和数据库设计，因为需要权衡事务一致性。"
    row = _trace("trace-post", "post_answer", "answer_quality_probe")
    row["input_summary"] = {"answer": answer}

    with pytest.raises(AssertionError):
        validate_skill_traces(
            [*_pre_rows(), row],
            expected_round_type="technical",
            submitted_answer=answer,
        )


def _pre_rows() -> list[dict[str, object]]:
    return [
        _trace("trace-pre", "pre_question", "context_summary"),
        _trace("trace-pre", "pre_question", "technical_gap_mapper"),
    ]


def _trace(trace_id: str, stage: str, skill_name: str) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "round_type": "technical",
        "stage": stage,
        "skill_name": skill_name,
        "selection_source": "rule",
        "selection_reason": "test",
        "input_summary": {
            "round_type": "technical",
            "stage": stage,
            "question_kind": "main",
            "answer_length": 20,
        },
        "output_summary": {"signal_count": 1},
        "structured_signals": [{"code": "test", "severity": "info", "evidence": {}}],
        "confidence": 0.7,
        "llm_enhanced": 0,
        "elapsed_ms": 1,
        "error_message": None,
    }
