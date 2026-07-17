import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.repositories.weakness_practice_progress import (
    WeaknessPracticeProgressRecord as WeaknessPracticeProgressRecord,
)
from app.repositories.weakness_practice_progress import (
    to_weakness_practice_progress as _to_weakness_practice_progress,
)

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class FeedbackReportRecord:
    score: int
    weaknesses: list[str]
    suggestions: list[str]
    recommendation: str | None = None
    round_scores: list[JSONDict] | None = None
    strengths: list[str] | None = None
    ability_analysis: list[str] | None = None
    job_match: str | None = None
    final_conclusion: str | None = None
    confidence: str | None = None
    reference_note: str | None = None
    used_candidate_memory: bool = False
    report_reliability_status: str = "normal"
    created_at: datetime | None = None


@dataclass(frozen=True)
class ResumeSummaryRecord:
    id: int
    structured_data: JSONDict
    created_at: datetime


@dataclass(frozen=True)
class HistoryRoundRecord:
    id: int
    round_type: str
    status: str
    score: int | None
    result: str | None
    summary: JSONDict | None
    is_reference_only: bool
    started_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True)
class HistoryQARecord:
    id: int
    round_id: int | None
    round_type: str | None
    sequence: int
    question_type: str
    question: str
    answer: str | None
    question_kind: str
    parent_question_id: int | None
    created_at: datetime | None
    question_evaluation: JSONDict | None = None


@dataclass(frozen=True)
class HistoryInterviewRecord:
    id: int
    user_id: int
    resume_id: int
    target_position: str
    status: str
    mode: str
    job_description: str | None
    overall_status: str
    elapsed_seconds: int
    started_at: datetime | None
    ended_at: datetime | None
    last_active_at: datetime | None
    created_at: datetime
    resume: ResumeSummaryRecord
    feedback_report: FeedbackReportRecord | None = None
    rounds: list[HistoryRoundRecord] | None = None
    qa_history: list[HistoryQARecord] | None = None
    harness_status: str | None = None
    recovery_count: int = 0
    had_degradation: bool = False
    last_harness_error: str | None = None


@dataclass(frozen=True)
class ReportListRecord:
    interview_id: int
    user_id: int
    target_position: str
    score: int
    report_reliability_status: str
    used_candidate_memory: bool
    created_at: datetime | None


@dataclass(frozen=True)
class DashboardAggregateRecord:
    interview_count: int
    report_count: int
    personalized_feedback_used: bool


class HistoryRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self._column_cache: dict[str, set[str]] = {}

    def list_by_user(self, user_id: int) -> list[HistoryInterviewRecord]:
        with self.connection.cursor() as cursor:
            feedback_reliability_select = self._feedback_reliability_select()
            feedback_memory_select = self._feedback_memory_select()
            interview_selects = self._interview_optional_selects()
            history_order = self._history_order_expression()
            cursor.execute(
                """
                SELECT
                    i.id,
                    i.user_id,
                    i.resume_id,
                    i.target_position,
                    i.status,
                    {mode_select}
                    {job_description_select}
                    {overall_status_select}
                    {elapsed_seconds_select}
                    i.started_at,
                    i.ended_at,
                    {last_active_at_select}
                    {harness_status_select}
                    {recovery_count_select}
                    {had_degradation_select}
                    {last_harness_error_select}
                    i.created_at,
                    r.structured_data AS resume_structured_data,
                    r.created_at AS resume_created_at,
                    fr.score AS feedback_score,
                    fr.weaknesses AS feedback_weaknesses,
                    fr.suggestions AS feedback_suggestions,
                    fr.recommendation AS feedback_recommendation,
                    fr.round_scores AS feedback_round_scores,
                    fr.strengths AS feedback_strengths,
                    fr.ability_analysis AS feedback_ability_analysis,
                    fr.job_match AS feedback_job_match,
                    fr.final_conclusion AS feedback_final_conclusion,
                    fr.confidence AS feedback_confidence,
                    fr.reference_note AS feedback_reference_note,
                    {feedback_memory_select}
                    {feedback_reliability_select}
                    fr.created_at AS feedback_created_at
                FROM interviews i
                JOIN resumes r ON r.id = i.resume_id
                LEFT JOIN feedback_reports fr ON fr.interview_id = i.id
                WHERE i.user_id = %s
                ORDER BY {history_order} DESC, i.id DESC
                """.format(
                    feedback_reliability_select=feedback_reliability_select,
                    feedback_memory_select=feedback_memory_select,
                    history_order=history_order,
                    **interview_selects,
                ),
                (user_id,),
            )
            rows = cursor.fetchall()
        return [_to_history_record(row) for row in rows]

    def get_dashboard_aggregate(self, user_id: int) -> DashboardAggregateRecord:
        used_memory_expression = (
            "COALESCE(MAX(fr.used_candidate_memory), 0)"
            if self._has_column("feedback_reports", "used_candidate_memory")
            else "0"
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    COUNT(i.id) AS interview_count,
                    COUNT(fr.interview_id) AS report_count,
                    {used_memory_expression} AS personalized_feedback_used
                FROM interviews i
                LEFT JOIN feedback_reports fr ON fr.interview_id = i.id
                WHERE i.user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone() or {}
        return DashboardAggregateRecord(
            interview_count=int(row.get("interview_count") or 0),
            report_count=int(row.get("report_count") or 0),
            personalized_feedback_used=bool(row.get("personalized_feedback_used")),
        )

    def list_dashboard_recent_by_user(
        self,
        user_id: int,
        *,
        limit: int = 5,
    ) -> list[HistoryInterviewRecord]:
        return self._list_dashboard_records(user_id, limit=limit, reports_only=False)

    def list_dashboard_reports_by_user(
        self,
        user_id: int,
        *,
        limit: int = 8,
    ) -> list[HistoryInterviewRecord]:
        return self._list_dashboard_records(user_id, limit=limit, reports_only=True)

    def _list_dashboard_records(
        self,
        user_id: int,
        *,
        limit: int,
        reports_only: bool,
    ) -> list[HistoryInterviewRecord]:
        feedback_reliability_select = self._feedback_reliability_select()
        feedback_memory_select = self._feedback_memory_select()
        interview_selects = self._interview_optional_selects()
        history_order = self._history_order_expression()
        report_filter = "AND fr.interview_id IS NOT NULL" if reports_only else ""
        order_expression = (
            "COALESCE(fr.created_at, i.ended_at, i.started_at, i.created_at)"
            if reports_only
            else history_order
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    i.id,
                    i.user_id,
                    i.resume_id,
                    i.target_position,
                    i.status,
                    {mode_select}
                    {job_description_select}
                    {overall_status_select}
                    {elapsed_seconds_select}
                    i.started_at,
                    i.ended_at,
                    {last_active_at_select}
                    {harness_status_select}
                    {recovery_count_select}
                    {had_degradation_select}
                    {last_harness_error_select}
                    i.created_at,
                    JSON_OBJECT() AS resume_structured_data,
                    i.created_at AS resume_created_at,
                    fr.score AS feedback_score,
                    fr.weaknesses AS feedback_weaknesses,
                    fr.suggestions AS feedback_suggestions,
                    fr.recommendation AS feedback_recommendation,
                    fr.round_scores AS feedback_round_scores,
                    fr.strengths AS feedback_strengths,
                    fr.ability_analysis AS feedback_ability_analysis,
                    fr.job_match AS feedback_job_match,
                    fr.final_conclusion AS feedback_final_conclusion,
                    fr.confidence AS feedback_confidence,
                    fr.reference_note AS feedback_reference_note,
                    {feedback_memory_select}
                    {feedback_reliability_select}
                    fr.created_at AS feedback_created_at
                FROM interviews i
                LEFT JOIN feedback_reports fr ON fr.interview_id = i.id
                WHERE i.user_id = %s
                  {report_filter}
                ORDER BY {order_expression} DESC, i.id DESC
                LIMIT %s
                """.format(
                    feedback_reliability_select=feedback_reliability_select,
                    feedback_memory_select=feedback_memory_select,
                    report_filter=report_filter,
                    order_expression=order_expression,
                    **interview_selects,
                ),
                (user_id, max(1, min(limit, 100))),
            )
            rows = cursor.fetchall()
        return [_to_history_record(row) for row in rows]

    def list_interviews_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        status_filter: str | None = None,
    ) -> list[HistoryInterviewRecord]:
        with self.connection.cursor() as cursor:
            interview_selects = self._interview_optional_selects()
            history_order = self._history_order_expression()
            pagination_clause = ""
            params: list[Any] = [user_id]
            filters: list[str] = []
            keyword = query.strip()
            if keyword:
                if keyword.isdigit():
                    filters.append("(i.target_position LIKE %s OR i.id = %s)")
                    params.extend([f"%{keyword}%", int(keyword)])
                else:
                    filters.append("i.target_position LIKE %s")
                    params.append(f"%{keyword}%")
            if status_filter:
                status_expression = (
                    "COALESCE(i.overall_status, i.status)"
                    if self._has_column("interviews", "overall_status")
                    else "i.status"
                )
                filters.append(f"{status_expression} = %s")
                params.append(status_filter)
            filter_clause = "" if not filters else "AND " + " AND ".join(filters)
            if limit is not None:
                pagination_clause = "LIMIT %s OFFSET %s"
                params.extend([limit, max(offset, 0)])
            cursor.execute(
                """
                SELECT
                    i.id,
                    i.user_id,
                    i.resume_id,
                    i.target_position,
                    i.status,
                    {mode_select}
                    {job_description_select}
                    {overall_status_select}
                    {elapsed_seconds_select}
                    i.started_at,
                    i.ended_at,
                    {last_active_at_select}
                    {harness_status_select}
                    {recovery_count_select}
                    {had_degradation_select}
                    {last_harness_error_select}
                    i.created_at,
                    JSON_OBJECT() AS resume_structured_data,
                    i.created_at AS resume_created_at
                FROM interviews i
                JOIN resumes r ON r.id = i.resume_id
                WHERE i.user_id = %s
                  {filter_clause}
                ORDER BY {history_order} DESC, i.id DESC
                {pagination_clause}
                """.format(
                    filter_clause=filter_clause,
                    history_order=history_order,
                    pagination_clause=pagination_clause,
                    **interview_selects,
                ),
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_history_record(row) for row in rows]

    def list_reports_by_user(
        self,
        user_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        score_filter: str | None = None,
        sort: str = "recent",
    ) -> list[ReportListRecord]:
        with self.connection.cursor() as cursor:
            feedback_reliability_select = self._feedback_reliability_select()
            feedback_memory_select = self._feedback_memory_select("used_candidate_memory")
            pagination_clause = ""
            params: list[Any] = [user_id]
            filters: list[str] = []
            keyword = query.strip()
            if keyword:
                if keyword.isdigit():
                    filters.append("(i.target_position LIKE %s OR i.id = %s)")
                    params.extend([f"%{keyword}%", int(keyword)])
                else:
                    filters.append("i.target_position LIKE %s")
                    params.append(f"%{keyword}%")
            if score_filter == "high":
                filters.append("fr.score >= %s")
                params.append(80)
            elif score_filter == "middle":
                filters.append("fr.score >= %s AND fr.score < %s")
                params.extend([60, 80])
            filter_clause = "" if not filters else "AND " + " AND ".join(filters)
            order_clause = {
                "score-desc": "fr.score DESC, fr.created_at DESC, fr.interview_id DESC",
                "score-asc": "fr.score ASC, fr.created_at DESC, fr.interview_id DESC",
            }.get(sort, "fr.created_at DESC, fr.interview_id DESC")
            if limit is not None:
                pagination_clause = "LIMIT %s OFFSET %s"
                params.extend([limit, max(offset, 0)])
            cursor.execute(
                f"""
                SELECT
                    i.id AS interview_id,
                    i.user_id,
                    i.target_position,
                    fr.score,
                    {feedback_memory_select}
                    {feedback_reliability_select}
                    fr.created_at
                FROM feedback_reports fr
                JOIN interviews i ON i.id = fr.interview_id
                WHERE i.user_id = %s
                  {filter_clause}
                ORDER BY {order_clause}
                {pagination_clause}
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        return [_to_report_list_record(row) for row in rows]

    def list_weakness_practice_progress_by_user(
        self,
        user_id: int,
    ) -> list[WeaknessPracticeProgressRecord]:
        if not self._table_exists("weakness_practice_progress"):
            return []
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    source_interview_id,
                    practice_interview_id,
                    weakness_title,
                    weakness_key,
                    suggestion,
                    round_type,
                    status,
                    source_score,
                    practice_score,
                    last_practiced_at,
                    created_at,
                    updated_at
                FROM weakness_practice_progress
                WHERE user_id = %s
                ORDER BY COALESCE(last_practiced_at, updated_at, created_at) DESC, id DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        return [
            progress
            for row in rows
            if (progress := _to_weakness_practice_progress(row)) is not None
        ]

    def get_by_id(self, interview_id: int) -> HistoryInterviewRecord | None:
        return self._get_by_id(interview_id)

    def get_by_id_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> HistoryInterviewRecord | None:
        return self._get_by_id(interview_id, user_id=user_id)

    def _get_by_id(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
    ) -> HistoryInterviewRecord | None:
        user_filter = "AND i.user_id = %s" if user_id is not None else ""
        params: tuple[Any, ...] = (
            (interview_id, user_id) if user_id is not None else (interview_id,)
        )
        with self.connection.cursor() as cursor:
            feedback_reliability_select = self._feedback_reliability_select()
            feedback_memory_select = self._feedback_memory_select()
            interview_selects = self._interview_optional_selects()
            cursor.execute(
                """
                SELECT
                    i.id,
                    i.user_id,
                    i.resume_id,
                    i.target_position,
                    i.status,
                    {mode_select}
                    {job_description_select}
                    {overall_status_select}
                    {elapsed_seconds_select}
                    i.started_at,
                    i.ended_at,
                    {last_active_at_select}
                    {harness_status_select}
                    {recovery_count_select}
                    {had_degradation_select}
                    {last_harness_error_select}
                    i.created_at,
                    r.structured_data AS resume_structured_data,
                    r.created_at AS resume_created_at,
                    fr.score AS feedback_score,
                    fr.weaknesses AS feedback_weaknesses,
                    fr.suggestions AS feedback_suggestions,
                    fr.recommendation AS feedback_recommendation,
                    fr.round_scores AS feedback_round_scores,
                    fr.strengths AS feedback_strengths,
                    fr.ability_analysis AS feedback_ability_analysis,
                    fr.job_match AS feedback_job_match,
                    fr.final_conclusion AS feedback_final_conclusion,
                    fr.confidence AS feedback_confidence,
                    fr.reference_note AS feedback_reference_note,
                    {feedback_memory_select}
                    {feedback_reliability_select}
                    fr.created_at AS feedback_created_at
                FROM interviews i
                JOIN resumes r ON r.id = i.resume_id
                LEFT JOIN feedback_reports fr ON fr.interview_id = i.id
                WHERE i.id = %s
                  {user_filter}
                """.format(
                    feedback_reliability_select=feedback_reliability_select,
                    feedback_memory_select=feedback_memory_select,
                    user_filter=user_filter,
                    **interview_selects,
                ),
                params,
            )
            row = cursor.fetchone()
        if row is None:
            return None
        record = _to_history_record(row)
        return HistoryInterviewRecord(
            **{
                **record.__dict__,
                "rounds": self._list_rounds(record.id),
                "qa_history": self._list_qa(record.id),
            }
        )

    def list_interview_ids_by_user(self, user_id: int) -> list[int]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM interviews WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            return [int(row["id"]) for row in cursor.fetchall()]

    def delete_by_id_for_user(self, interview_id: int, user_id: int) -> bool:
        with self.connection.cursor() as cursor:
            self._scrub_evolution_records_for_interview(cursor, interview_id, user_id)
            self._delete_memory_tasks_for_interview(cursor, interview_id, user_id)
            self._delete_rag_audit_logs_for_interview(cursor, interview_id, user_id)
            self._delete_notifications_for_interview(cursor, interview_id, user_id)
            self._delete_harness_records_for_interview(cursor, interview_id, user_id)
            self._delete_skill_call_traces_for_interview(cursor, interview_id, user_id)
            cursor.execute(
                "UPDATE user_feedback_submissions SET interview_id = NULL, round_id = NULL, "
                "question_id = NULL WHERE user_id = %s AND interview_id = %s",
                (user_id, interview_id),
            )
            cursor.execute(
                "DELETE er FROM evaluation_records er JOIN interviews i ON i.id = er.interview_id "
                "WHERE i.id = %s AND i.user_id = %s",
                (interview_id, user_id),
            )
            cursor.execute(
                "DELETE fr FROM feedback_reports fr JOIN interviews i ON i.id = fr.interview_id "
                "WHERE i.id = %s AND i.user_id = %s",
                (interview_id, user_id),
            )
            cursor.execute(
                "UPDATE interview_qa qa JOIN interviews i ON i.id = qa.interview_id "
                "SET qa.parent_question_id = NULL, qa.regenerated_from_question_id = NULL "
                "WHERE i.id = %s AND i.user_id = %s",
                (interview_id, user_id),
            )
            cursor.execute(
                "DELETE qa FROM interview_qa qa JOIN interviews i ON i.id = qa.interview_id "
                "WHERE i.id = %s AND i.user_id = %s",
                (interview_id, user_id),
            )
            cursor.execute(
                "DELETE ir FROM interview_rounds ir JOIN interviews i ON i.id = ir.interview_id "
                "WHERE i.id = %s AND i.user_id = %s",
                (interview_id, user_id),
            )
            cursor.execute(
                "DELETE FROM interviews WHERE id = %s AND user_id = %s",
                (interview_id, user_id),
            )
            return int(cursor.rowcount) > 0

    def delete_all_by_user(self, user_id: int) -> int:
        with self.connection.cursor() as cursor:
            self._scrub_evolution_records_for_user(cursor, user_id)
            self._delete_memory_tasks_for_user(cursor, user_id)
            self._delete_rag_audit_logs_for_user(cursor, user_id)
            self._delete_notifications_for_user(cursor, user_id)
            self._delete_harness_records_for_user(cursor, user_id)
            self._delete_skill_call_traces_for_user(cursor, user_id)
            cursor.execute(
                "UPDATE user_feedback_submissions SET interview_id = NULL, round_id = NULL, "
                "question_id = NULL WHERE user_id = %s AND interview_id IS NOT NULL",
                (user_id,),
            )
            cursor.execute(
                "DELETE er FROM evaluation_records er JOIN interviews i ON i.id = er.interview_id "
                "WHERE i.user_id = %s",
                (user_id,),
            )
            cursor.execute(
                "DELETE fr FROM feedback_reports fr JOIN interviews i ON i.id = fr.interview_id "
                "WHERE i.user_id = %s",
                (user_id,),
            )
            cursor.execute(
                "UPDATE interview_qa qa JOIN interviews i ON i.id = qa.interview_id "
                "SET qa.parent_question_id = NULL, qa.regenerated_from_question_id = NULL "
                "WHERE i.user_id = %s",
                (user_id,),
            )
            cursor.execute(
                "DELETE qa FROM interview_qa qa JOIN interviews i ON i.id = qa.interview_id "
                "WHERE i.user_id = %s",
                (user_id,),
            )
            cursor.execute(
                "DELETE ir FROM interview_rounds ir JOIN interviews i ON i.id = ir.interview_id "
                "WHERE i.user_id = %s",
                (user_id,),
            )
            cursor.execute("DELETE FROM interviews WHERE user_id = %s", (user_id,))
            return int(cursor.rowcount)

    def _delete_memory_tasks_for_interview(
        self,
        cursor: Any,
        interview_id: int,
        user_id: int,
    ) -> None:
        cursor.execute(
            "DELETE mt FROM memory_tasks mt JOIN interviews i ON i.id = mt.interview_id "
            "WHERE i.id = %s AND i.user_id = %s",
            (interview_id, user_id),
        )

    def _scrub_evolution_records_for_interview(
        self,
        cursor: Any,
        interview_id: int,
        user_id: int,
    ) -> None:
        if not self._table_exists("harness_evolution_runs"):
            return
        cursor.execute(
            """
            SELECT her.id, her.source_interview_ids
            FROM harness_evolution_runs her
            JOIN interviews i ON i.id = %s AND i.user_id = %s
            WHERE JSON_CONTAINS(her.source_interview_ids, JSON_ARRAY(i.id))
            """,
            (interview_id, user_id),
        )
        run_rows = list(cursor.fetchall())
        if self._table_exists("harness_evolution_samples"):
            cursor.execute(
                """
                DELETE hes FROM harness_evolution_samples hes
                JOIN interviews i ON i.id = hes.source_interview_id
                WHERE i.id = %s AND i.user_id = %s
                """,
                (interview_id, user_id),
            )
        if self._table_exists("harness_evolution_events"):
            cursor.execute(
                """
                DELETE hee FROM harness_evolution_events hee
                JOIN interviews i
                  ON i.id = CAST(
                      JSON_UNQUOTE(JSON_EXTRACT(hee.payload, '$.interview_id'))
                      AS UNSIGNED
                  )
                WHERE i.id = %s AND i.user_id = %s
                """,
                (interview_id, user_id),
            )
        self._remove_interview_ids_from_evolution_runs(
            cursor,
            run_rows,
            {interview_id},
        )

    def _scrub_evolution_records_for_user(self, cursor: Any, user_id: int) -> None:
        if not self._table_exists("harness_evolution_runs"):
            return
        cursor.execute("SELECT id FROM interviews WHERE user_id = %s", (user_id,))
        interview_ids = {int(row["id"]) for row in cursor.fetchall()}
        if not interview_ids:
            return
        cursor.execute("SELECT id, source_interview_ids FROM harness_evolution_runs")
        run_rows = list(cursor.fetchall())
        if self._table_exists("harness_evolution_samples"):
            cursor.execute(
                """
                DELETE hes FROM harness_evolution_samples hes
                JOIN interviews i ON i.id = hes.source_interview_id
                WHERE i.user_id = %s
                """,
                (user_id,),
            )
        if self._table_exists("harness_evolution_events"):
            cursor.execute(
                """
                DELETE hee FROM harness_evolution_events hee
                JOIN interviews i
                  ON i.id = CAST(
                      JSON_UNQUOTE(JSON_EXTRACT(hee.payload, '$.interview_id'))
                      AS UNSIGNED
                  )
                WHERE i.user_id = %s
                """,
                (user_id,),
            )
        self._remove_interview_ids_from_evolution_runs(
            cursor,
            run_rows,
            interview_ids,
        )

    @staticmethod
    def _remove_interview_ids_from_evolution_runs(
        cursor: Any,
        run_rows: list[dict[str, Any]],
        interview_ids: set[int],
    ) -> None:
        for row in run_rows:
            raw_ids = row.get("source_interview_ids")
            if isinstance(raw_ids, str):
                try:
                    raw_ids = json.loads(raw_ids)
                except json.JSONDecodeError:
                    raw_ids = []
            kept_ids = [
                int(value)
                for value in list(raw_ids or [])
                if int(value) not in interview_ids
            ]
            if len(kept_ids) == len(list(raw_ids or [])):
                continue
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET source_interview_ids = %s,
                    diagnosis = NULL,
                    proposal = JSON_OBJECT('scrubbed_after_source_deletion', true)
                WHERE id = %s
                """,
                (json.dumps(kept_ids), int(row["id"])),
            )

    def _delete_memory_tasks_for_user(self, cursor: Any, user_id: int) -> None:
        cursor.execute(
            "DELETE mt FROM memory_tasks mt JOIN interviews i ON i.id = mt.interview_id "
            "WHERE i.user_id = %s",
            (user_id,),
        )

    def _delete_rag_audit_logs_for_interview(
        self,
        cursor: Any,
        interview_id: int,
        user_id: int,
    ) -> None:
        cursor.execute(
            """
            DELETE ral FROM rag_audit_logs ral
            LEFT JOIN interviews direct_i ON direct_i.id = ral.interview_id
            LEFT JOIN interview_rounds ir ON ir.id = ral.round_id
            LEFT JOIN interviews round_i ON round_i.id = ir.interview_id
            WHERE (direct_i.id = %s AND direct_i.user_id = %s)
               OR (round_i.id = %s AND round_i.user_id = %s)
            """,
            (interview_id, user_id, interview_id, user_id),
        )

    def _delete_rag_audit_logs_for_user(self, cursor: Any, user_id: int) -> None:
        cursor.execute(
            """
            DELETE ral FROM rag_audit_logs ral
            LEFT JOIN interviews direct_i ON direct_i.id = ral.interview_id
            LEFT JOIN interview_rounds ir ON ir.id = ral.round_id
            LEFT JOIN interviews round_i ON round_i.id = ir.interview_id
            WHERE direct_i.user_id = %s OR round_i.user_id = %s
            """,
            (user_id, user_id),
        )

    def _delete_notifications_for_interview(
        self,
        cursor: Any,
        interview_id: int,
        user_id: int,
    ) -> None:
        cursor.execute(
            """
            DELETE n FROM notifications n
            LEFT JOIN interview_rounds ir ON ir.id = n.round_id
            LEFT JOIN interview_qa qa ON qa.id = n.question_id
            WHERE n.user_id = %s
              AND (
                  n.interview_id = %s
                  OR (n.related_type IN ('interview', 'history', 'feedback_report')
                      AND n.related_id = %s)
                  OR ir.interview_id = %s
                  OR qa.interview_id = %s
              )
            """,
            (user_id, interview_id, interview_id, interview_id, interview_id),
        )

    def _delete_notifications_for_user(self, cursor: Any, user_id: int) -> None:
        cursor.execute(
            """
            DELETE n FROM notifications n
            LEFT JOIN interview_rounds ir ON ir.id = n.round_id
            LEFT JOIN interview_qa qa ON qa.id = n.question_id
            WHERE n.user_id = %s
              AND (
                  n.interview_id IN (SELECT id FROM interviews WHERE user_id = %s)
                  OR (n.related_type IN ('interview', 'history', 'feedback_report')
                      AND n.related_id IN (SELECT id FROM interviews WHERE user_id = %s))
                  OR ir.interview_id IN (SELECT id FROM interviews WHERE user_id = %s)
                  OR qa.interview_id IN (SELECT id FROM interviews WHERE user_id = %s)
              )
            """,
            (user_id, user_id, user_id, user_id, user_id),
        )

    def _delete_harness_records_for_interview(
        self,
        cursor: Any,
        interview_id: int,
        user_id: int,
    ) -> None:
        cursor.execute(
            "UPDATE interviews SET last_checkpoint_id = NULL WHERE id = %s AND user_id = %s",
            (interview_id, user_id),
        )
        cursor.execute(
            "DELETE hte FROM harness_trace_events hte "
            "JOIN harness_traces ht ON ht.id = hte.trace_id "
            "JOIN interviews i ON i.id = ht.interview_id "
            "WHERE i.id = %s AND i.user_id = %s",
            (interview_id, user_id),
        )
        cursor.execute(
            "DELETE hre FROM harness_rule_evaluations hre "
            "JOIN interviews i ON i.id = hre.interview_id "
            "WHERE i.id = %s AND i.user_id = %s",
            (interview_id, user_id),
        )
        cursor.execute(
            "DELETE hc FROM harness_checkpoints hc "
            "JOIN interviews i ON i.id = hc.interview_id "
            "WHERE i.id = %s AND i.user_id = %s",
            (interview_id, user_id),
        )
        cursor.execute(
            "DELETE ht FROM harness_traces ht "
            "JOIN interviews i ON i.id = ht.interview_id "
            "WHERE i.id = %s AND i.user_id = %s",
            (interview_id, user_id),
        )

    def _delete_harness_records_for_user(self, cursor: Any, user_id: int) -> None:
        cursor.execute(
            "UPDATE interviews SET last_checkpoint_id = NULL WHERE user_id = %s",
            (user_id,),
        )
        cursor.execute(
            "DELETE hte FROM harness_trace_events hte "
            "JOIN harness_traces ht ON ht.id = hte.trace_id "
            "JOIN interviews i ON i.id = ht.interview_id "
            "WHERE i.user_id = %s",
            (user_id,),
        )
        cursor.execute(
            "DELETE hre FROM harness_rule_evaluations hre "
            "JOIN interviews i ON i.id = hre.interview_id "
            "WHERE i.user_id = %s",
            (user_id,),
        )
        cursor.execute(
            "DELETE hc FROM harness_checkpoints hc "
            "JOIN interviews i ON i.id = hc.interview_id "
            "WHERE i.user_id = %s",
            (user_id,),
        )
        cursor.execute(
            "DELETE ht FROM harness_traces ht "
            "JOIN interviews i ON i.id = ht.interview_id "
            "WHERE i.user_id = %s",
            (user_id,),
        )

    def _delete_skill_call_traces_for_interview(
        self,
        cursor: Any,
        interview_id: int,
        user_id: int,
    ) -> None:
        if not self._table_exists("skill_call_traces"):
            return
        cursor.execute(
            "DELETE sct FROM skill_call_traces sct "
            "JOIN interviews i ON i.id = sct.interview_id "
            "WHERE i.id = %s AND i.user_id = %s",
            (interview_id, user_id),
        )

    def _delete_skill_call_traces_for_user(self, cursor: Any, user_id: int) -> None:
        if not self._table_exists("skill_call_traces"):
            return
        cursor.execute(
            "DELETE sct FROM skill_call_traces sct "
            "JOIN interviews i ON i.id = sct.interview_id "
            "WHERE i.user_id = %s",
            (user_id,),
        )

    def _list_rounds(self, interview_id: int) -> list[HistoryRoundRecord]:
        if not self._table_exists("interview_rounds"):
            return []
        is_reference_only_select = self._column_select(
            "interview_rounds",
            "is_reference_only",
            "is_reference_only",
            "0",
            qualifier="interview_rounds",
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, round_type, status, score, result, summary,
                       {is_reference_only_select}
                       started_at, ended_at
                FROM interview_rounds
                WHERE interview_id = %s
                ORDER BY FIELD(round_type, 'resume', 'technical', 'manager', 'hr')
                """,
                (interview_id,),
            )
            rows = cursor.fetchall()
        return [_to_round_record(row) for row in rows]

    def _list_qa(self, interview_id: int) -> list[HistoryQARecord]:
        has_rounds = self._table_exists("interview_rounds")
        has_round_id = self._has_column("interview_qa", "round_id")
        round_id_select = "qa.round_id," if has_round_id else "NULL AS round_id,"
        round_type_select = (
            "ir.round_type," if has_rounds and has_round_id else "NULL AS round_type,"
        )
        question_kind_select = self._column_select(
            "interview_qa",
            "question_kind",
            "question_kind",
            "'main'",
            qualifier="qa",
        )
        question_status_filter = (
            "AND qa.question_status = 'active'"
            if self._has_column("interview_qa", "question_status")
            else ""
        )
        parent_question_id_select = self._column_select(
            "interview_qa",
            "parent_question_id",
            "parent_question_id",
            "NULL",
            qualifier="qa",
        )
        round_join = (
            "LEFT JOIN interview_rounds ir ON ir.id = qa.round_id"
            if has_rounds and has_round_id
            else ""
        )
        round_order = (
            "FIELD(ir.round_type, 'resume', 'technical', 'manager', 'hr'),"
            if has_rounds and has_round_id
            else ""
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    qa.id,
                    {round_id_select}
                    {round_type_select}
                    qa.sequence,
                    qa.question_type,
                    qa.question,
                    qa.answer,
                    {question_kind_select}
                    {parent_question_id_select}
                    qa.created_at,
                    er.result AS question_evaluation
                FROM interview_qa qa
                {round_join}
                LEFT JOIN evaluation_records er
                    ON er.question_id = qa.id
                    AND er.evaluation_type = 'question'
                    AND er.status = 'succeeded'
                WHERE qa.interview_id = %s
                  {question_status_filter}
                ORDER BY {round_order}
                         qa.sequence ASC,
                         qa.id ASC
                """,
                (interview_id,),
            )
            rows = cursor.fetchall()
        return [_to_qa_record(row) for row in rows]

    def _feedback_reliability_select(self) -> str:
        return self._column_select(
            "feedback_reports",
            "report_reliability_status",
            "feedback_report_reliability_status",
            "'normal'",
            qualifier="fr",
        )

    def _feedback_memory_select(self, alias: str = "feedback_used_candidate_memory") -> str:
        return self._column_select(
            "feedback_reports",
            "used_candidate_memory",
            alias,
            "0",
            qualifier="fr",
        )

    def _interview_optional_selects(self) -> dict[str, str]:
        return {
            "mode_select": self._column_select("interviews", "mode", "mode", "'multi_round'"),
            "job_description_select": self._column_select(
                "interviews",
                "job_description",
                "job_description",
                "NULL",
            ),
            "overall_status_select": self._column_select(
                "interviews",
                "overall_status",
                "overall_status",
                "i.status",
            ),
            "elapsed_seconds_select": self._column_select(
                "interviews",
                "elapsed_seconds",
                "elapsed_seconds",
                "0",
            ),
            "last_active_at_select": self._column_select(
                "interviews",
                "last_active_at",
                "last_active_at",
                "NULL",
            ),
            "harness_status_select": self._column_select(
                "interviews",
                "harness_status",
                "harness_status",
                "NULL",
            ),
            "recovery_count_select": self._column_select(
                "interviews",
                "recovery_count",
                "recovery_count",
                "0",
            ),
            "had_degradation_select": self._column_select(
                "interviews",
                "had_degradation",
                "had_degradation",
                "0",
            ),
            "last_harness_error_select": self._column_select(
                "interviews",
                "last_harness_error",
                "last_harness_error",
                "NULL",
            ),
        }

    def _history_order_expression(self) -> str:
        if self._has_column("interviews", "last_active_at"):
            return "COALESCE(i.last_active_at, i.started_at, i.created_at)"
        return "COALESCE(i.started_at, i.created_at)"

    def _column_select(
        self,
        table: str,
        column: str,
        alias: str,
        fallback_sql: str,
        qualifier: str = "i",
    ) -> str:
        if self._has_column(table, column):
            return f"{qualifier}.{column} AS {alias},"
        return f"{fallback_sql} AS {alias},"

    def _has_column(self, table: str, column: str) -> bool:
        return column in self._existing_columns(table)

    def _table_exists(self, table: str) -> bool:
        return bool(self._existing_columns(table))

    def _existing_columns(self, table: str) -> set[str]:
        if table not in self._column_cache:
            try:
                with self.connection.cursor() as cursor:
                    cursor.execute(f"SHOW COLUMNS FROM {table}")
                    rows = cursor.fetchall()
                self._column_cache[table] = {
                    str(row.get("Field") if isinstance(row, dict) else row[0]) for row in rows
                }
            except Exception:
                self._column_cache[table] = set()
        return self._column_cache[table]


def _to_history_record(row: dict[str, Any]) -> HistoryInterviewRecord:
    resume = ResumeSummaryRecord(
        id=int(row["resume_id"]),
        structured_data=_json_dict(row["resume_structured_data"]),
        created_at=row["resume_created_at"],
    )
    feedback_report = _to_feedback_report(row)
    return HistoryInterviewRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        resume_id=int(row["resume_id"]),
        target_position=str(row["target_position"]),
        status=str(row["status"]),
        mode=str(row.get("mode") or "multi_round"),
        job_description=row.get("job_description"),
        overall_status=str(row.get("overall_status") or row["status"]),
        elapsed_seconds=int(row.get("elapsed_seconds") or 0),
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        last_active_at=row.get("last_active_at"),
        created_at=row["created_at"],
        resume=resume,
        feedback_report=feedback_report,
        harness_status=row.get("harness_status"),
        recovery_count=int(row.get("recovery_count") or 0),
        had_degradation=bool(row.get("had_degradation")),
        last_harness_error=row.get("last_harness_error"),
    )


def _to_report_list_record(row: dict[str, Any]) -> ReportListRecord:
    return ReportListRecord(
        interview_id=int(row["interview_id"]),
        user_id=int(row["user_id"]),
        target_position=str(row["target_position"]),
        score=int(row["score"]),
        report_reliability_status=str(row.get("feedback_report_reliability_status") or "normal"),
        used_candidate_memory=bool(row.get("used_candidate_memory", False)),
        created_at=row.get("created_at"),
    )


def _to_feedback_report(row: dict[str, Any]) -> FeedbackReportRecord | None:
    if row.get("feedback_score") is None:
        return None
    return FeedbackReportRecord(
        score=int(row["feedback_score"]),
        weaknesses=_json_list(row["feedback_weaknesses"]),
        suggestions=_json_list(row["feedback_suggestions"]),
        recommendation=row.get("feedback_recommendation"),
        round_scores=_json_dict_list(row.get("feedback_round_scores")),
        strengths=_json_list(row.get("feedback_strengths")),
        ability_analysis=_json_list(row.get("feedback_ability_analysis")),
        job_match=row.get("feedback_job_match"),
        final_conclusion=row.get("feedback_final_conclusion"),
        confidence=row.get("feedback_confidence"),
        reference_note=row.get("feedback_reference_note"),
        used_candidate_memory=bool(row.get("feedback_used_candidate_memory", False)),
        report_reliability_status=str(row.get("feedback_report_reliability_status") or "normal"),
        created_at=row.get("feedback_created_at"),
    )


def _to_round_record(row: dict[str, Any]) -> HistoryRoundRecord:
    summary = row.get("summary")
    return HistoryRoundRecord(
        id=int(row["id"]),
        round_type=str(row["round_type"]),
        status=str(row["status"]),
        score=int(row["score"]) if row.get("score") is not None else None,
        result=str(row["result"]) if row.get("result") is not None else None,
        summary=_json_dict(summary) if summary is not None else None,
        is_reference_only=bool(row.get("is_reference_only")),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
    )


def _to_qa_record(row: dict[str, Any]) -> HistoryQARecord:
    return HistoryQARecord(
        id=int(row["id"]),
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        round_type=str(row["round_type"]) if row.get("round_type") is not None else None,
        sequence=int(row["sequence"]),
        question_type=str(row["question_type"]),
        question=str(row["question"]),
        answer=str(row["answer"]) if row.get("answer") is not None else None,
        question_kind=str(row.get("question_kind") or "main"),
        parent_question_id=(
            int(row["parent_question_id"]) if row.get("parent_question_id") is not None else None
        ),
        created_at=row.get("created_at"),
        question_evaluation=(
            _json_dict(row.get("question_evaluation"))
            if row.get("question_evaluation") is not None
            else None
        ),
    )


def _json_dict(value: Any) -> JSONDict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _json_dict_list(value: Any) -> list[JSONDict] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return None
