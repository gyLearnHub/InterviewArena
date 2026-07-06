import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ResumeRecord:
    id: int
    user_id: int
    structured_data: dict[str, Any]


@dataclass(frozen=True)
class InterviewRecord:
    id: int
    user_id: int
    resume_id: int
    target_position: str
    status: str
    question_count: int
    started_at: datetime | None
    ended_at: datetime | None
    mode: str = "multi_round"
    job_description: str | None = None
    selected_rounds: list[str] | None = None
    current_round: str | None = None
    overall_status: str = "created"
    last_active_at: datetime | None = None
    elapsed_seconds: int = 0
    harness_status: str | None = None
    last_checkpoint_id: int | None = None
    recovery_count: int = 0
    last_recovered_at: datetime | None = None
    last_harness_error: str | None = None
    had_degradation: bool = False
    version_bundle_id: int | None = None


@dataclass(frozen=True)
class QARecord:
    id: int
    interview_id: int
    sequence: int
    question_type: str
    question: str
    answer: str | None
    created_at: datetime
    round_id: int | None = None
    question_kind: str = "main"
    question_status: str = "active"
    parent_question_id: int | None = None
    regenerated_from_question_id: int | None = None


@dataclass(frozen=True)
class InterviewRoundRecord:
    id: int
    interview_id: int
    agent_type: str
    round_type: str
    status: str
    min_main_questions: int
    max_main_questions: int
    min_total_questions: int
    max_total_questions: int
    score: int | None
    result: str | None
    summary: dict[str, Any] | None
    is_reference_only: bool
    started_at: datetime | None
    ended_at: datetime | None
    execution_status: str | None = None
    retry_count: int = 0


@dataclass(frozen=True)
class FeedbackReportRecord:
    interview_id: int
    score: int
    weaknesses: list[str]
    suggestions: list[str]
    recommendation: str | None = None
    round_scores: list[dict[str, Any]] | None = None
    strengths: list[str] | None = None
    ability_analysis: list[str] | None = None
    job_match: str | None = None
    final_conclusion: str | None = None
    confidence: str | None = None
    reference_note: str | None = None
    used_candidate_memory: bool = False
    report_reliability_status: str = "normal"


class InterviewRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self._column_cache: dict[str, set[str]] = {}

    def commit(self) -> None:
        self.connection.commit()

    def get_resume_for_user(self, resume_id: int, user_id: int) -> ResumeRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, structured_data
                FROM resumes
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (resume_id, user_id),
            )
            row = cursor.fetchone()
        return _to_resume(row)

    def create_interview(
        self,
        user_id: int,
        resume_id: int,
        target_position: str,
        mode: str = "multi_round",
        job_description: str | None = None,
        selected_rounds: list[str] | None = None,
        version_bundle_id: int | None = None,
    ) -> InterviewRecord:
        selected_rounds_json = (
            json.dumps(selected_rounds, ensure_ascii=False) if selected_rounds is not None else None
        )
        optional_columns = self._existing_columns("interviews", ["version_bundle_id"])
        has_version_bundle = (
            version_bundle_id is not None and "version_bundle_id" in optional_columns
        )
        version_column = ", version_bundle_id" if has_version_bundle else ""
        version_value = ", %s" if has_version_bundle else ""
        params: list[Any] = [
            user_id,
            resume_id,
            target_position,
            "created",
            0,
            mode,
            job_description,
            selected_rounds_json,
            "created",
            0,
        ]
        if has_version_bundle:
            params.append(version_bundle_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO interviews (
                    user_id, resume_id, target_position, status, question_count, mode,
                    job_description, selected_rounds, overall_status,
                    elapsed_seconds{version_column}
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s{version_value})
                """,
                tuple(params),
            )
            interview_id = int(cursor.lastrowid)
        return InterviewRecord(
            id=interview_id,
            user_id=user_id,
            resume_id=resume_id,
            target_position=target_position,
            status="created",
            question_count=0,
            started_at=None,
            ended_at=None,
            mode=mode,
            job_description=job_description,
            selected_rounds=selected_rounds,
            overall_status="created",
            version_bundle_id=version_bundle_id,
        )

    def get_interview_for_user(
        self,
        interview_id: int,
        user_id: int,
    ) -> InterviewRecord | None:
        with self.connection.cursor() as cursor:
            optional_columns = self._existing_columns(
                "interviews",
                [
                    "harness_status",
                    "last_checkpoint_id",
                    "recovery_count",
                    "last_recovered_at",
                    "last_harness_error",
                    "had_degradation",
                    "version_bundle_id",
                ],
            )
            optional_select = "".join(f", {column}" for column in optional_columns)
            cursor.execute(
                f"""
                SELECT id, user_id, resume_id, target_position, status, question_count,
                       started_at, ended_at, mode, job_description, selected_rounds,
                       current_round, overall_status, last_active_at, elapsed_seconds
                       {optional_select}
                FROM interviews
                WHERE id = %s AND user_id = %s
                """,
                (interview_id, user_id),
            )
            row = cursor.fetchone()
        return _to_interview(row)

    def update_question_count(self, interview_id: int, question_count: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE interviews SET question_count = %s WHERE id = %s",
                (question_count, interview_id),
            )

    def create_qa(
        self,
        interview_id: int,
        sequence: int,
        question_type: str,
        question: str,
        round_id: int | None = None,
        question_kind: str = "main",
        parent_question_id: int | None = None,
        regenerated_from_question_id: int | None = None,
    ) -> QARecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO interview_qa (
                    interview_id, round_id, sequence, question_type, question, question_kind,
                    parent_question_id, regenerated_from_question_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    interview_id,
                    round_id,
                    sequence,
                    question_type,
                    question,
                    question_kind,
                    parent_question_id,
                    regenerated_from_question_id,
                ),
            )
            qa_id = int(cursor.lastrowid)
        return QARecord(
            id=qa_id,
            interview_id=interview_id,
            sequence=sequence,
            question_type=question_type,
            question=question,
            answer=None,
            created_at=datetime.utcnow(),
            round_id=round_id,
            question_kind=question_kind,
            question_status="active",
            parent_question_id=parent_question_id,
            regenerated_from_question_id=regenerated_from_question_id,
        )

    def create_qa_idempotent(
        self,
        interview_id: int,
        sequence: int,
        question_type: str,
        question: str,
        round_id: int | None = None,
        question_kind: str = "main",
        parent_question_id: int | None = None,
        regenerated_from_question_id: int | None = None,
    ) -> QARecord:
        try:
            return self.create_qa(
                interview_id=interview_id,
                sequence=sequence,
                question_type=question_type,
                question=question,
                round_id=round_id,
                question_kind=question_kind,
                parent_question_id=parent_question_id,
                regenerated_from_question_id=regenerated_from_question_id,
            )
        except Exception as exc:
            if not _is_duplicate_key_error(exc):
                raise
            existing = self.get_round_qa_by_sequence(interview_id, round_id, sequence)
            if existing is None:
                raise
            return existing

    def update_answer(self, qa_id: int, answer: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_qa
                SET answer = %s
                WHERE id = %s AND answer IS NULL AND question_status = 'active'
            """,
                (answer, qa_id),
            )
            return int(cursor.rowcount) > 0

    def update_question_status(self, qa_id: int, question_status: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_qa
                SET question_status = %s
                WHERE id = %s AND question_status = 'active' AND answer IS NULL
            """,
                (question_status, qa_id),
            )
            return int(cursor.rowcount) > 0

    def list_qa(self, interview_id: int, include_inactive: bool = False) -> list[QARecord]:
        status_filter = "" if include_inactive else "AND question_status = 'active'"
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, interview_id, round_id, sequence, question_type, question, answer,
                       question_kind, question_status, parent_question_id,
                       regenerated_from_question_id, created_at
                FROM interview_qa
                WHERE interview_id = %s
                  {status_filter}
                ORDER BY sequence ASC
                """,
                (interview_id,),
            )
            rows = cursor.fetchall()
        records: list[QARecord] = []
        for row in rows:
            record = _to_qa(row)
            if record is not None:
                records.append(record)
        return records

    def get_round_qa_by_sequence(
        self,
        interview_id: int,
        round_id: int | None,
        sequence: int,
    ) -> QARecord | None:
        with self.connection.cursor() as cursor:
            if round_id is None:
                cursor.execute(
                    """
                    SELECT id, interview_id, round_id, sequence, question_type, question, answer,
                           question_kind, parent_question_id, created_at
                    FROM interview_qa
                    WHERE interview_id = %s AND round_id IS NULL AND sequence = %s
                    """,
                    (interview_id, sequence),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, interview_id, round_id, sequence, question_type, question, answer,
                           question_kind, parent_question_id, created_at
                    FROM interview_qa
                    WHERE interview_id = %s AND round_id = %s AND sequence = %s
                    """,
                    (interview_id, round_id, sequence),
                )
            row = cursor.fetchone()
        return _to_qa(row)

    def create_feedback_report(
        self,
        interview_id: int,
        score: int,
        weaknesses: list[str],
        suggestions: list[str],
        recommendation: str | None = None,
        round_scores: list[dict[str, Any]] | None = None,
        strengths: list[str] | None = None,
        ability_analysis: list[str] | None = None,
        job_match: str | None = None,
        final_conclusion: str | None = None,
        confidence: str | None = None,
        reference_note: str | None = None,
        used_candidate_memory: bool = False,
        report_reliability_status: str = "normal",
    ) -> FeedbackReportRecord:
        optional_columns = self._existing_columns(
            "feedback_reports",
            ["report_reliability_status"],
        )
        reliability_column = (
            ", report_reliability_status" if "report_reliability_status" in optional_columns else ""
        )
        reliability_value = ", %s" if "report_reliability_status" in optional_columns else ""
        params: list[Any] = [
            interview_id,
            score,
            json.dumps(weaknesses, ensure_ascii=False),
            json.dumps(suggestions, ensure_ascii=False),
            recommendation,
            json.dumps(round_scores, ensure_ascii=False) if round_scores is not None else None,
            json.dumps(strengths, ensure_ascii=False) if strengths is not None else None,
            json.dumps(ability_analysis, ensure_ascii=False)
            if ability_analysis is not None
            else None,
            job_match,
            final_conclusion,
            confidence,
            reference_note,
            used_candidate_memory,
        ]
        if "report_reliability_status" in optional_columns:
            params.append(report_reliability_status)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO feedback_reports (
                    interview_id, score, weaknesses, suggestions, recommendation, round_scores,
                    strengths, ability_analysis, job_match, final_conclusion, confidence,
                    reference_note, used_candidate_memory{reliability_column}
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s{reliability_value})
                """,
                tuple(params),
            )
        return FeedbackReportRecord(
            interview_id=interview_id,
            score=score,
            weaknesses=weaknesses,
            suggestions=suggestions,
            recommendation=recommendation,
            round_scores=round_scores,
            strengths=strengths,
            ability_analysis=ability_analysis,
            job_match=job_match,
            final_conclusion=final_conclusion,
            confidence=confidence,
            reference_note=reference_note,
            used_candidate_memory=used_candidate_memory,
            report_reliability_status=report_reliability_status,
        )

    def create_feedback_report_idempotent(
        self,
        interview_id: int,
        score: int,
        weaknesses: list[str],
        suggestions: list[str],
        recommendation: str | None = None,
        round_scores: list[dict[str, Any]] | None = None,
        strengths: list[str] | None = None,
        ability_analysis: list[str] | None = None,
        job_match: str | None = None,
        final_conclusion: str | None = None,
        confidence: str | None = None,
        reference_note: str | None = None,
        used_candidate_memory: bool = False,
        report_reliability_status: str = "normal",
    ) -> FeedbackReportRecord:
        try:
            return self.create_feedback_report(
                interview_id=interview_id,
                score=score,
                weaknesses=weaknesses,
                suggestions=suggestions,
                recommendation=recommendation,
                round_scores=round_scores,
                strengths=strengths,
                ability_analysis=ability_analysis,
                job_match=job_match,
                final_conclusion=final_conclusion,
                confidence=confidence,
                reference_note=reference_note,
                used_candidate_memory=used_candidate_memory,
                report_reliability_status=report_reliability_status,
            )
        except Exception as exc:
            if not _is_duplicate_key_error(exc):
                raise
            existing = self.get_feedback_report(interview_id)
            if existing is None:
                raise
            return existing

    def get_feedback_report(self, interview_id: int) -> FeedbackReportRecord | None:
        with self.connection.cursor() as cursor:
            optional_columns = self._existing_columns(
                "feedback_reports",
                ["report_reliability_status"],
            )
            optional_select = "".join(f", {column}" for column in optional_columns)
            cursor.execute(
                f"""
                SELECT interview_id, score, weaknesses, suggestions, recommendation,
                       round_scores, strengths, ability_analysis, job_match, final_conclusion,
                       confidence, reference_note, used_candidate_memory
                       {optional_select}
                FROM feedback_reports
                WHERE interview_id = %s
                """,
                (interview_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return FeedbackReportRecord(
            interview_id=int(row["interview_id"]),
            score=int(row["score"]),
            weaknesses=_json_string_list(row.get("weaknesses")),
            suggestions=_json_string_list(row.get("suggestions")),
            recommendation=row.get("recommendation"),
            round_scores=_json_dict_list(row.get("round_scores")),
            strengths=_json_string_list(row.get("strengths")),
            ability_analysis=_json_string_list(row.get("ability_analysis")),
            job_match=row.get("job_match"),
            final_conclusion=row.get("final_conclusion"),
            confidence=row.get("confidence"),
            reference_note=row.get("reference_note"),
            used_candidate_memory=bool(row.get("used_candidate_memory", False)),
            report_reliability_status=str(row.get("report_reliability_status") or "normal"),
        )

    def create_rounds(self, rounds: list[dict[str, Any]]) -> list[InterviewRoundRecord]:
        created: list[InterviewRoundRecord] = []
        with self.connection.cursor() as cursor:
            for item in rounds:
                cursor.execute(
                    """
                    INSERT INTO interview_rounds (
                        interview_id, agent_type, round_type, status, min_main_questions,
                        max_main_questions, min_total_questions, max_total_questions
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        item["interview_id"],
                        item["agent_type"],
                        item["round_type"],
                        item["status"],
                        item["min_main_questions"],
                        item["max_main_questions"],
                        item["min_total_questions"],
                        item["max_total_questions"],
                    ),
                )
                created.append(
                    InterviewRoundRecord(
                        id=int(cursor.lastrowid),
                        interview_id=int(item["interview_id"]),
                        agent_type=str(item["agent_type"]),
                        round_type=str(item["round_type"]),
                        status=str(item["status"]),
                        min_main_questions=int(item["min_main_questions"]),
                        max_main_questions=int(item["max_main_questions"]),
                        min_total_questions=int(item["min_total_questions"]),
                        max_total_questions=int(item["max_total_questions"]),
                        score=None,
                        result=None,
                        summary=None,
                        is_reference_only=False,
                        started_at=None,
                        ended_at=None,
                        execution_status=str(item.get("execution_status") or "pending"),
                        retry_count=int(item.get("retry_count") or 0),
                    )
                )
        return created

    def list_rounds(self, interview_id: int) -> list[InterviewRoundRecord]:
        with self.connection.cursor() as cursor:
            optional_columns = self._existing_columns(
                "interview_rounds",
                ["execution_status", "retry_count"],
            )
            optional_select = "".join(f", {column}" for column in optional_columns)
            cursor.execute(
                f"""
                SELECT id, interview_id, agent_type, round_type, status, min_main_questions,
                       max_main_questions, min_total_questions, max_total_questions, score,
                       result, summary, is_reference_only, started_at, ended_at
                       {optional_select}
                FROM interview_rounds
                WHERE interview_id = %s
                ORDER BY FIELD(round_type, 'resume', 'technical', 'manager', 'hr')
                """,
                (interview_id,),
            )
            rows = cursor.fetchall()
        return [_to_round(row) for row in rows]

    def get_round(self, interview_id: int, round_id: int) -> InterviewRoundRecord | None:
        with self.connection.cursor() as cursor:
            optional_columns = self._existing_columns(
                "interview_rounds",
                ["execution_status", "retry_count"],
            )
            optional_select = "".join(f", {column}" for column in optional_columns)
            cursor.execute(
                f"""
                SELECT id, interview_id, agent_type, round_type, status, min_main_questions,
                       max_main_questions, min_total_questions, max_total_questions, score,
                       result, summary, is_reference_only, started_at, ended_at
                       {optional_select}
                FROM interview_rounds
                WHERE interview_id = %s AND id = %s
                """,
                (interview_id, round_id),
            )
            row = cursor.fetchone()
        return _to_round(row) if row is not None else None

    def mark_round_started(
        self,
        interview_id: int,
        round_id: int,
        round_type: str,
        started_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_rounds
                SET status = %s, started_at = COALESCE(started_at, %s)
                WHERE id = %s AND interview_id = %s
                """,
                ("in_progress", started_at, round_id, interview_id),
            )
            cursor.execute(
                """
                UPDATE interviews
                SET status = %s,
                    overall_status = %s,
                    current_round = %s,
                    started_at = COALESCE(started_at, %s),
                    last_active_at = %s,
                    elapsed_seconds = %s
                WHERE id = %s
                """,
                (
                    "in_progress",
                    "in_progress",
                    round_type,
                    started_at,
                    started_at,
                    elapsed_seconds,
                    interview_id,
                ),
            )

    def touch_interview(
        self,
        interview_id: int,
        last_active_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interviews
                SET last_active_at = %s, elapsed_seconds = %s
                WHERE id = %s
                """,
                (last_active_at, elapsed_seconds, interview_id),
            )

    def pause_interview(
        self,
        interview_id: int,
        paused_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interviews
                SET status = %s,
                    overall_status = %s,
                    last_active_at = %s,
                    elapsed_seconds = %s
                WHERE id = %s
                """,
                ("paused", "paused", paused_at, elapsed_seconds, interview_id),
            )

    def resume_interview(
        self,
        interview_id: int,
        resumed_at: datetime,
        paused_at: datetime | None,
    ) -> None:
        paused_seconds = (
            max(0, int((resumed_at - paused_at).total_seconds()))
            if paused_at is not None
            else 0
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_rounds r
                JOIN interviews i ON i.id = r.interview_id
                SET r.started_at = DATE_ADD(r.started_at, INTERVAL %s SECOND)
                WHERE i.id = %s
                  AND i.current_round = r.round_type
                  AND r.status = %s
                  AND r.started_at IS NOT NULL
                """,
                (paused_seconds, interview_id, "in_progress"),
            )
            cursor.execute(
                """
                UPDATE interviews
                SET status = %s,
                    overall_status = %s,
                    last_active_at = %s
                WHERE id = %s
                """,
                ("in_progress", "in_progress", resumed_at, interview_id),
            )

    def get_round_qa_by_id(
        self,
        interview_id: int,
        round_id: int,
        qa_id: int,
    ) -> QARecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, interview_id, round_id, sequence, question_type, question, answer,
                       question_kind, question_status, parent_question_id,
                       regenerated_from_question_id, created_at
                FROM interview_qa
                WHERE id = %s AND interview_id = %s AND round_id = %s
                """,
                (qa_id, interview_id, round_id),
            )
            row = cursor.fetchone()
        return _to_qa(row)

    def list_round_qa(
        self,
        interview_id: int,
        round_id: int,
        include_inactive: bool = False,
    ) -> list[QARecord]:
        status_filter = "" if include_inactive else "AND question_status = 'active'"
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, interview_id, round_id, sequence, question_type, question, answer,
                       question_kind, question_status, parent_question_id,
                       regenerated_from_question_id, created_at
                FROM interview_qa
                WHERE interview_id = %s AND round_id = %s
                  {status_filter}
                ORDER BY sequence ASC
                """,
                (interview_id, round_id),
            )
            rows = cursor.fetchall()
        records: list[QARecord] = []
        for row in rows:
            record = _to_qa(row)
            if record is not None:
                records.append(record)
        return records

    def get_unanswered_round_question(
        self,
        interview_id: int,
        round_id: int,
    ) -> QARecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, interview_id, round_id, sequence, question_type, question, answer,
                       question_kind, question_status, parent_question_id,
                       regenerated_from_question_id, created_at
                FROM interview_qa
                WHERE interview_id = %s
                  AND round_id = %s
                  AND answer IS NULL
                  AND question_status = 'active'
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (interview_id, round_id),
            )
            row = cursor.fetchone()
        return _to_qa(row)

    def finish_round(
        self,
        interview_id: int,
        round_id: int,
        status: str,
        summary: dict[str, Any],
        ended_at: datetime,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_rounds
                SET status = %s,
                    score = %s,
                    result = %s,
                    summary = %s,
                    is_reference_only = %s,
                    ended_at = %s
                WHERE id = %s AND interview_id = %s
                """,
                (
                    status,
                    summary.get("score"),
                    summary.get("result"),
                    json.dumps(summary, ensure_ascii=False),
                    bool(summary.get("is_reference_only", False)),
                    ended_at,
                    round_id,
                    interview_id,
                ),
            )
            cursor.execute(
                """
                UPDATE interviews i
                JOIN interview_rounds r ON r.interview_id = i.id AND r.id = %s
                SET i.current_round = NULL
                WHERE i.id = %s AND i.current_round = r.round_type
                """,
                (round_id, interview_id),
            )

    def cancel_pending_rounds(self, interview_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interview_rounds
                SET status = %s
                WHERE interview_id = %s AND status = %s
                """,
                ("cancelled", interview_id, "pending"),
            )

    def mark_multi_finished(
        self,
        interview_id: int,
        ended_at: datetime,
        elapsed_seconds: int,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE interviews
                SET status = %s,
                    overall_status = %s,
                    current_round = NULL,
                    ended_at = %s,
                    last_active_at = %s,
                    elapsed_seconds = %s
                WHERE id = %s
                """,
                ("finished", "finished", ended_at, ended_at, elapsed_seconds, interview_id),
            )

    def update_interview_harness(
        self,
        interview_id: int,
        *,
        harness_status: str | None = None,
        last_checkpoint_id: int | None = None,
        recovery_count: int | None = None,
        last_recovered_at: datetime | None = None,
        last_harness_error: str | None = None,
        had_degradation: bool | None = None,
    ) -> None:
        values: dict[str, Any] = {}
        if harness_status is not None:
            values["harness_status"] = harness_status
        if last_checkpoint_id is not None:
            values["last_checkpoint_id"] = last_checkpoint_id
        if recovery_count is not None:
            values["recovery_count"] = recovery_count
        if last_recovered_at is not None:
            values["last_recovered_at"] = last_recovered_at
        if last_harness_error is not None:
            values["last_harness_error"] = last_harness_error[:1000]
        if had_degradation is not None:
            values["had_degradation"] = had_degradation
        self._update_existing_columns("interviews", interview_id, values)

    def update_round_execution(
        self,
        round_id: int,
        *,
        execution_status: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        values: dict[str, Any] = {}
        if execution_status is not None:
            values["execution_status"] = execution_status
        if retry_count is not None:
            values["retry_count"] = retry_count
        self._update_existing_columns("interview_rounds", round_id, values)

    def _existing_columns(self, table: str, candidates: list[str]) -> set[str]:
        if table not in {"interviews", "interview_rounds", "feedback_reports"}:
            return set()
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
        available = self._column_cache[table]
        return {column for column in candidates if column in available}

    def _update_existing_columns(self, table: str, record_id: int, values: dict[str, Any]) -> None:
        columns = self._existing_columns(table, list(values.keys()))
        if not columns:
            return
        assignments = ", ".join(f"{column} = %s" for column in values if column in columns)
        params = [value for column, value in values.items() if column in columns]
        params.append(record_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {assignments} WHERE id = %s",
                tuple(params),
            )


def _to_resume(row: dict[str, Any] | None) -> ResumeRecord | None:
    if row is None:
        return None
    structured_data = row["structured_data"]
    if isinstance(structured_data, str):
        structured_data = json.loads(structured_data)
    return ResumeRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        structured_data=dict(structured_data),
    )


def _to_interview(row: dict[str, Any] | None) -> InterviewRecord | None:
    if row is None:
        return None
    selected_rounds = row.get("selected_rounds")
    return InterviewRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        resume_id=int(row["resume_id"]),
        target_position=str(row["target_position"]),
        status=str(row["status"]),
        question_count=int(row["question_count"]),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
        mode=str(row.get("mode") or "multi_round"),
        job_description=row.get("job_description"),
        selected_rounds=_json_string_list(selected_rounds) if selected_rounds is not None else None,
        current_round=row.get("current_round"),
        overall_status=str(row.get("overall_status") or row["status"]),
        last_active_at=row.get("last_active_at"),
        elapsed_seconds=int(row.get("elapsed_seconds") or 0),
        harness_status=row.get("harness_status"),
        last_checkpoint_id=(
            int(row["last_checkpoint_id"]) if row.get("last_checkpoint_id") is not None else None
        ),
        recovery_count=int(row.get("recovery_count") or 0),
        last_recovered_at=row.get("last_recovered_at"),
        last_harness_error=row.get("last_harness_error"),
        had_degradation=bool(row.get("had_degradation", False)),
        version_bundle_id=(
            int(row["version_bundle_id"]) if row.get("version_bundle_id") is not None else None
        ),
    )


def _to_qa(row: dict[str, Any] | None) -> QARecord | None:
    if row is None:
        return None
    created_at = row.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow()
    answer = row.get("answer")
    return QARecord(
        id=int(row["id"]),
        interview_id=int(row["interview_id"]),
        sequence=int(row["sequence"]),
        question_type=str(row["question_type"]),
        question=str(row["question"]),
        answer=str(answer) if answer is not None else None,
        created_at=created_at,
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        question_kind=str(row.get("question_kind") or "main"),
        question_status=str(row.get("question_status") or "active"),
        parent_question_id=(
            int(row["parent_question_id"]) if row.get("parent_question_id") is not None else None
        ),
        regenerated_from_question_id=(
            int(row["regenerated_from_question_id"])
            if row.get("regenerated_from_question_id") is not None
            else None
        ),
    )


def _to_round(row: dict[str, Any]) -> InterviewRoundRecord:
    summary = row.get("summary")
    return InterviewRoundRecord(
        id=int(row["id"]),
        interview_id=int(row["interview_id"]),
        agent_type=str(row["agent_type"]),
        round_type=str(row["round_type"]),
        status=str(row["status"]),
        min_main_questions=int(row["min_main_questions"]),
        max_main_questions=int(row["max_main_questions"]),
        min_total_questions=int(row["min_total_questions"]),
        max_total_questions=int(row["max_total_questions"]),
        score=int(row["score"]) if row.get("score") is not None else None,
        result=str(row["result"]) if row.get("result") is not None else None,
        summary=_json_dict(summary) if summary is not None else None,
        is_reference_only=bool(row.get("is_reference_only")),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
        execution_status=row.get("execution_status"),
        retry_count=int(row.get("retry_count") or 0),
    )


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _json_dict_list(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return None


def _is_duplicate_key_error(exc: Exception) -> bool:
    args = getattr(exc, "args", ())
    code = args[0] if args else None
    return code == 1062 or "duplicate" in str(exc).casefold()
