from typing import Any

from app.repositories.history import HistoryRepository

DEFAULT_RECORDING_TABLES: set[str] = set()


class RecordingCursor:
    def __init__(
        self,
        existing_tables: set[str] | None = None,
    ) -> None:
        self.statements: list[str] = []
        self.existing_tables = (
            set(DEFAULT_RECORDING_TABLES) if existing_tables is None else existing_tables
        )
        self.last_statement = ""
        self.rowcount = 0

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: Any = None) -> None:
        normalized = " ".join(sql.split())
        self.last_statement = normalized
        self.statements.append(normalized)
        self.rowcount = 1 if normalized.startswith("DELETE FROM interviews") else 0

    def fetchall(self) -> list[dict[str, Any]]:
        table_prefix = "SHOW COLUMNS FROM "
        if self.last_statement.startswith(table_prefix):
            table = self.last_statement[len(table_prefix) :]
            if table in self.existing_tables:
                return [{"Field": "id"}]
        return []


class RecordingConnection:
    def __init__(
        self,
        existing_tables: set[str] | None = None,
    ) -> None:
        self.cursor_instance = RecordingCursor(existing_tables)

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance


class ScriptedCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.last_statement = ""

    def __enter__(self) -> "ScriptedCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: Any = None) -> None:
        self.last_statement = " ".join(sql.split())
        self.statements.append(self.last_statement)

    def fetchone(self) -> dict[str, Any] | None:
        return {
            "id": 10,
            "user_id": 1,
            "resume_id": 101,
            "target_position": "后端开发",
            "status": "finished",
            "mode": "multi_round",
            "job_description": "负责后端平台建设",
            "overall_status": "finished",
            "elapsed_seconds": 480,
            "started_at": None,
            "ended_at": None,
            "created_at": None,
            "resume_structured_data": '{"skills":["Python"]}',
            "resume_created_at": None,
            "feedback_score": 82,
            "feedback_weaknesses": '["项目深度还可以更具体"]',
            "feedback_suggestions": '["补充技术取舍"]',
            "feedback_recommendation": "建议录用",
            "feedback_round_scores": '[{"round_type":"resume","score":82,"result":"passed"}]',
            "feedback_strengths": '["表达清晰"]',
            "feedback_reference_note": None,
            "feedback_created_at": None,
        }

    def fetchall(self) -> list[dict[str, Any]]:
        if "FROM feedback_reports fr" in self.last_statement:
            return [
                {
                    "interview_id": 10,
                    "user_id": 1,
                    "target_position": "后端开发",
                    "score": 82,
                    "used_candidate_memory": 1,
                    "feedback_report_reliability_status": "reference_only",
                    "created_at": None,
                }
            ]
        if (
            "FROM interviews i" in self.last_statement
            and "LEFT JOIN feedback_reports" not in self.last_statement
        ):
            return [
                {
                    "id": 10,
                    "user_id": 1,
                    "resume_id": 101,
                    "target_position": "后端开发",
                    "status": "in_progress",
                    "mode": "multi_round",
                    "job_description": "负责后端平台建设",
                    "overall_status": "in_progress",
                    "elapsed_seconds": 120,
                    "started_at": None,
                    "ended_at": None,
                    "last_active_at": None,
                    "created_at": None,
                    "resume_structured_data": '{"skills":["Python"]}',
                    "resume_created_at": None,
                }
            ]
        if "FROM interview_rounds" in self.last_statement:
            return [
                {
                    "id": 201,
                    "round_type": "resume",
                    "status": "completed",
                    "score": 82,
                    "result": "passed",
                    "summary": '{"score":82,"result":"passed"}',
                    "is_reference_only": 0,
                    "started_at": None,
                    "ended_at": None,
                }
            ]
        if "FROM interview_qa" in self.last_statement:
            return [
                {
                    "id": 301,
                    "round_id": 201,
                    "round_type": "resume",
                    "sequence": 1,
                    "question_type": "resume_question",
                    "question": "介绍一个项目",
                    "answer": "我做过订单系统",
                    "question_kind": "main",
                    "parent_question_id": None,
                    "created_at": None,
                }
            ]
        return []


class ScriptedConnection:
    def __init__(self) -> None:
        self.cursor_instance = ScriptedCursor()

    def cursor(self) -> ScriptedCursor:
        return self.cursor_instance


def test_delete_history_item_breaks_qa_parent_links_before_deleting_qa() -> None:
    connection = RecordingConnection()
    repository = HistoryRepository(connection)

    repository.delete_by_id_for_user(10, 1)

    statements = connection.cursor_instance.statements
    self_reference_update_index = _index_of(
        statements,
        "SET qa.parent_question_id = NULL, qa.regenerated_from_question_id = NULL",
    )
    assert self_reference_update_index < _index_of(
        statements,
        "DELETE qa FROM interview_qa",
    )


def test_delete_history_item_detaches_user_feedback_before_interview_data() -> None:
    connection = RecordingConnection()
    HistoryRepository(connection).delete_by_id_for_user(10, 1)

    statements = connection.cursor_instance.statements
    detach_index = _index_of(statements, "UPDATE user_feedback_submissions SET interview_id = NULL")
    assert detach_index < _index_of(statements, "DELETE qa FROM interview_qa")
    assert detach_index < _index_of(statements, "DELETE FROM interviews")


def test_delete_history_item_removes_harness_records_before_interview() -> None:
    connection = RecordingConnection()
    repository = HistoryRepository(connection)

    repository.delete_by_id_for_user(10, 1)

    statements = connection.cursor_instance.statements
    interview_delete_index = _index_of(statements, "DELETE FROM interviews")
    for text in [
        "DELETE mt FROM memory_tasks",
        "DELETE ral FROM rag_audit_logs",
        "DELETE n FROM notifications",
        "UPDATE interviews SET last_checkpoint_id = NULL",
        "DELETE hte FROM harness_trace_events",
        "DELETE hre FROM harness_rule_evaluations",
        "DELETE hc FROM harness_checkpoints",
        "DELETE ht FROM harness_traces",
    ]:
        assert _index_of(statements, text) < interview_delete_index


def test_clear_history_breaks_qa_parent_links_before_deleting_qa() -> None:
    connection = RecordingConnection()
    repository = HistoryRepository(connection)

    repository.delete_all_by_user(1)

    statements = connection.cursor_instance.statements
    self_reference_update_index = _index_of(
        statements,
        "SET qa.parent_question_id = NULL, qa.regenerated_from_question_id = NULL",
    )
    assert self_reference_update_index < _index_of(
        statements,
        "DELETE qa FROM interview_qa",
    )


def test_clear_history_detaches_user_feedback_before_interview_data() -> None:
    connection = RecordingConnection()
    HistoryRepository(connection).delete_all_by_user(1)

    statements = connection.cursor_instance.statements
    detach_index = _index_of(statements, "UPDATE user_feedback_submissions SET interview_id = NULL")
    assert detach_index < _index_of(statements, "DELETE qa FROM interview_qa")
    assert detach_index < _index_of(statements, "DELETE FROM interviews")


def test_clear_history_removes_harness_records_before_interviews() -> None:
    connection = RecordingConnection()
    repository = HistoryRepository(connection)

    repository.delete_all_by_user(1)

    statements = connection.cursor_instance.statements
    interview_delete_index = _index_of(statements, "DELETE FROM interviews")
    for text in [
        "DELETE mt FROM memory_tasks",
        "DELETE ral FROM rag_audit_logs",
        "DELETE n FROM notifications",
        "UPDATE interviews SET last_checkpoint_id = NULL",
        "DELETE hte FROM harness_trace_events",
        "DELETE hre FROM harness_rule_evaluations",
        "DELETE hc FROM harness_checkpoints",
        "DELETE ht FROM harness_traces",
    ]:
        assert _index_of(statements, text) < interview_delete_index
    assert _index_of(statements, "DELETE hte FROM harness_trace_events") < _index_of(
        statements,
        "DELETE ht FROM harness_traces",
    )


def test_delete_history_item_removes_context_records_before_rounds_and_qa() -> None:
    connection = RecordingConnection()
    repository = HistoryRepository(connection)

    repository.delete_by_id_for_user(10, 1)

    statements = connection.cursor_instance.statements
    qa_delete_index = _index_of(statements, "DELETE qa FROM interview_qa")
    round_delete_index = _index_of(statements, "DELETE ir FROM interview_rounds")
    assert _index_of(statements, "DELETE mt FROM memory_tasks") < round_delete_index
    assert _index_of(statements, "DELETE ral FROM rag_audit_logs") < round_delete_index
    assert _index_of(statements, "DELETE n FROM notifications") < qa_delete_index


def test_clear_history_removes_context_records_before_rounds_and_qa() -> None:
    connection = RecordingConnection()
    repository = HistoryRepository(connection)

    repository.delete_all_by_user(1)

    statements = connection.cursor_instance.statements
    qa_delete_index = _index_of(statements, "DELETE qa FROM interview_qa")
    round_delete_index = _index_of(statements, "DELETE ir FROM interview_rounds")
    assert _index_of(statements, "DELETE mt FROM memory_tasks") < round_delete_index
    assert _index_of(statements, "DELETE ral FROM rag_audit_logs") < round_delete_index
    assert _index_of(statements, "DELETE n FROM notifications") < qa_delete_index


def test_delete_history_item_removes_skill_call_traces_before_interview_records() -> None:
    connection = RecordingConnection(existing_tables={"skill_call_traces"})
    repository = HistoryRepository(connection)

    repository.delete_by_id_for_user(10, 1)

    statements = connection.cursor_instance.statements
    trace_delete_index = _index_of(statements, "DELETE sct FROM skill_call_traces")
    assert trace_delete_index < _index_of(statements, "DELETE qa FROM interview_qa")
    assert trace_delete_index < _index_of(statements, "DELETE ir FROM interview_rounds")
    assert trace_delete_index < _index_of(statements, "DELETE FROM interviews")


def test_clear_history_removes_skill_call_traces_before_interview_records() -> None:
    connection = RecordingConnection(existing_tables={"skill_call_traces"})
    repository = HistoryRepository(connection)

    repository.delete_all_by_user(1)

    statements = connection.cursor_instance.statements
    trace_delete_index = _index_of(statements, "DELETE sct FROM skill_call_traces")
    assert trace_delete_index < _index_of(statements, "DELETE qa FROM interview_qa")
    assert trace_delete_index < _index_of(statements, "DELETE ir FROM interview_rounds")
    assert trace_delete_index < _index_of(statements, "DELETE FROM interviews")


def test_delete_history_scrubs_autonomous_evolution_samples_and_events() -> None:
    evolution_tables = {
        "harness_evolution_runs",
        "harness_evolution_samples",
        "harness_evolution_events",
    }
    connection = RecordingConnection(existing_tables=evolution_tables)

    HistoryRepository(connection).delete_by_id_for_user(10, 1)

    statements = connection.cursor_instance.statements
    interview_delete_index = _index_of(statements, "DELETE FROM interviews")
    assert (
        _index_of(statements, "DELETE hes FROM harness_evolution_samples")
        < interview_delete_index
    )
    assert (
        _index_of(statements, "DELETE hee FROM harness_evolution_events")
        < interview_delete_index
    )


def test_evolution_run_source_ids_are_scrubbed_without_changing_trigger_cursor() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.updates: list[tuple[str, Any]] = []

        def execute(self, sql: str, params: Any = None) -> None:
            self.updates.append((" ".join(sql.split()), params))

    cursor = Cursor()

    HistoryRepository._remove_interview_ids_from_evolution_runs(
        cursor,
        [{"id": 7, "source_interview_ids": "[9, 10, 11]"}],
        {10},
    )

    assert cursor.updates == [
        (
            (
                "UPDATE harness_evolution_runs SET source_interview_ids = %s, "
                "diagnosis = NULL, "
                "proposal = JSON_OBJECT('scrubbed_after_source_deletion', true) "
                "WHERE id = %s"
            ),
            ("[9, 11]", 7),
        )
    ]


def test_get_history_detail_loads_multi_round_children() -> None:
    connection = ScriptedConnection()
    repository = HistoryRepository(connection)

    record = repository.get_by_id(10)

    assert record is not None
    assert record.mode == "multi_round"
    assert record.feedback_report is not None
    assert record.feedback_report.round_scores == [
        {"round_type": "resume", "score": 82, "result": "passed"}
    ]
    assert record.rounds is not None
    assert record.rounds[0].summary == {"score": 82, "result": "passed"}
    assert record.qa_history is not None
    assert record.qa_history[0].round_type == "resume"
    statements = connection.cursor_instance.statements
    assert any("FROM interview_rounds" in statement for statement in statements)
    assert any("FROM interview_qa" in statement for statement in statements)
    round_statement = next(
        statement for statement in statements if "FROM interview_rounds" in statement
    )
    assert "i.is_reference_only" not in round_statement


def test_get_history_detail_for_user_filters_before_loading_children() -> None:
    connection = ScriptedConnection()
    repository = HistoryRepository(connection)

    record = repository.get_by_id_for_user(10, 1)

    assert record is not None
    statements = connection.cursor_instance.statements
    detail_statement = next(
        statement
        for statement in statements
        if "FROM interviews i" in statement and "LEFT JOIN feedback_reports" in statement
    )
    assert "WHERE i.id = %s AND i.user_id = %s" in detail_statement
    assert any("FROM interview_rounds" in statement for statement in statements)


def test_list_reports_reads_from_feedback_reports() -> None:
    connection = ScriptedConnection()
    repository = HistoryRepository(connection)

    records = repository.list_reports_by_user(1)

    assert len(records) == 1
    assert records[0].interview_id == 10
    assert records[0].score == 82
    assert records[0].report_reliability_status == "reference_only"
    assert any(
        "FROM feedback_reports fr" in statement
        for statement in connection.cursor_instance.statements
    )


def test_list_reports_falls_back_when_optional_report_columns_are_missing() -> None:
    connection = LegacyReportConnection()
    repository = HistoryRepository(connection)

    records = repository.list_reports_by_user(1)

    assert len(records) == 1
    assert records[0].used_candidate_memory is False
    assert records[0].report_reliability_status == "normal"
    statement = next(
        item
        for item in connection.cursor_instance.statements
        if "FROM feedback_reports fr" in item
    )
    assert "0 AS used_candidate_memory" in statement
    assert "'normal' AS feedback_report_reliability_status" in statement


def test_list_interviews_does_not_join_feedback_reports() -> None:
    connection = ScriptedConnection()
    repository = HistoryRepository(connection)

    records = repository.list_interviews_by_user(1)

    assert len(records) == 1
    assert records[0].feedback_report is None
    statement = next(
        item
        for item in connection.cursor_instance.statements
        if "FROM interviews i" in item and "WHERE i.user_id" in item
    )
    assert "feedback_reports" not in statement


def test_list_interviews_falls_back_when_optional_interview_columns_are_missing() -> None:
    connection = LegacyInterviewConnection()
    repository = HistoryRepository(connection)

    records = repository.list_interviews_by_user(1)

    assert len(records) == 1
    assert records[0].mode == "multi_round"
    assert records[0].job_description is None
    assert records[0].overall_status == records[0].status
    assert records[0].elapsed_seconds == 0
    assert records[0].last_active_at is None
    statement = next(
        item
        for item in connection.cursor_instance.statements
        if "FROM interviews i" in item and "WHERE i.user_id" in item
    )
    assert "'multi_round' AS mode" in statement
    assert "NULL AS last_active_at" in statement
    assert "i.last_active_at" not in statement


def _index_of(statements: list[str], text: str) -> int:
    return next(index for index, statement in enumerate(statements) if text in statement)


class LegacyReportCursor(ScriptedCursor):
    def fetchall(self) -> list[dict[str, Any]]:
        if "FROM feedback_reports fr" in self.last_statement:
            return [
                {
                    "interview_id": 10,
                    "user_id": 1,
                    "target_position": "后端开发",
                    "score": 82,
                    "created_at": None,
                }
            ]
        return super().fetchall()


class LegacyReportConnection:
    def __init__(self) -> None:
        self.cursor_instance = LegacyReportCursor()

    def cursor(self) -> LegacyReportCursor:
        return self.cursor_instance


class LegacyInterviewCursor(ScriptedCursor):
    def fetchall(self) -> list[dict[str, Any]]:
        if (
            "FROM interviews i" in self.last_statement
            and "LEFT JOIN feedback_reports" not in self.last_statement
        ):
            return [
                {
                    "id": 10,
                    "user_id": 1,
                    "resume_id": 101,
                    "target_position": "后端开发",
                    "status": "in_progress",
                    "started_at": None,
                    "ended_at": None,
                    "created_at": None,
                    "resume_structured_data": '{"skills":["Python"]}',
                    "resume_created_at": None,
                }
            ]
        return super().fetchall()


class LegacyInterviewConnection:
    def __init__(self) -> None:
        self.cursor_instance = LegacyInterviewCursor()

    def cursor(self) -> LegacyInterviewCursor:
        return self.cursor_instance
