import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class EvaluationRecord:
    id: int
    evaluation_type: str
    evaluation_key: str
    interview_id: int
    round_id: int | None
    question_id: int | None
    status: str
    dimension_scores: list[JSONDict]
    total_score: int | None
    evidence: list[str]
    result: JSONDict | None
    error_message: str | None
    prompt_version: str
    model_name: str
    created_at: datetime | None
    updated_at: datetime | None


class EvaluationRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get_by_key(self, evaluation_type: str, evaluation_key: str) -> EvaluationRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, evaluation_type, evaluation_key, interview_id, round_id, question_id,
                       status, dimension_scores, total_score, evidence, result, error_message,
                       prompt_version, model_name, created_at, updated_at
                FROM evaluation_records
                WHERE evaluation_type = %s AND evaluation_key = %s
                """,
                (evaluation_type, evaluation_key),
            )
            row = cursor.fetchone()
        return _to_record(row)

    def list_by_interview(
        self,
        interview_id: int,
        evaluation_type: str | None = None,
        round_id: int | None = None,
    ) -> list[EvaluationRecord]:
        conditions = ["interview_id = %s"]
        params: list[Any] = [interview_id]
        if evaluation_type is not None:
            conditions.append("evaluation_type = %s")
            params.append(evaluation_type)
        if round_id is not None:
            conditions.append("round_id = %s")
            params.append(round_id)

        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, evaluation_type, evaluation_key, interview_id, round_id, question_id,
                       status, dimension_scores, total_score, evidence, result, error_message,
                       prompt_version, model_name, created_at, updated_at
                FROM evaluation_records
                WHERE {" AND ".join(conditions)}
                ORDER BY COALESCE(round_id, 0), COALESCE(question_id, 0), id
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
        records: list[EvaluationRecord] = []
        for row in rows:
            record = _to_record(row)
            if record is not None:
                records.append(record)
        return records

    def save_success(
        self,
        *,
        evaluation_type: str,
        evaluation_key: str,
        interview_id: int,
        round_id: int | None,
        question_id: int | None,
        dimension_scores: list[JSONDict],
        total_score: int | None,
        evidence: list[str],
        result: JSONDict,
        prompt_version: str,
        model_name: str,
    ) -> EvaluationRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evaluation_records (
                    evaluation_type, evaluation_key, interview_id, round_id, question_id,
                    status, dimension_scores, total_score, evidence, result, error_message,
                    prompt_version, model_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    dimension_scores = VALUES(dimension_scores),
                    total_score = VALUES(total_score),
                    evidence = VALUES(evidence),
                    result = VALUES(result),
                    error_message = NULL,
                    prompt_version = VALUES(prompt_version),
                    model_name = VALUES(model_name),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    evaluation_type,
                    evaluation_key,
                    interview_id,
                    round_id,
                    question_id,
                    "succeeded",
                    json.dumps(dimension_scores, ensure_ascii=False),
                    total_score,
                    json.dumps(evidence, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    prompt_version,
                    model_name,
                ),
            )
        record = self.get_by_key(evaluation_type, evaluation_key)
        if record is None:
            raise RuntimeError("evaluation record was not saved")
        return record

    def save_failure(
        self,
        *,
        evaluation_type: str,
        evaluation_key: str,
        interview_id: int,
        round_id: int | None,
        question_id: int | None,
        error_message: str,
        prompt_version: str,
        model_name: str,
    ) -> EvaluationRecord:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO evaluation_records (
                    evaluation_type, evaluation_key, interview_id, round_id, question_id,
                    status, dimension_scores, total_score, evidence, result, error_message,
                    prompt_version, model_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, JSON_ARRAY(), NULL, JSON_ARRAY(), NULL, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    error_message = VALUES(error_message),
                    prompt_version = VALUES(prompt_version),
                    model_name = VALUES(model_name),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    evaluation_type,
                    evaluation_key,
                    interview_id,
                    round_id,
                    question_id,
                    "failed",
                    error_message[:1000],
                    prompt_version,
                    model_name,
                ),
            )
        record = self.get_by_key(evaluation_type, evaluation_key)
        if record is None:
            raise RuntimeError("evaluation failure record was not saved")
        return record


def _to_record(row: dict[str, Any] | None) -> EvaluationRecord | None:
    if row is None:
        return None
    return EvaluationRecord(
        id=int(row["id"]),
        evaluation_type=str(row["evaluation_type"]),
        evaluation_key=str(row["evaluation_key"]),
        interview_id=int(row["interview_id"]),
        round_id=int(row["round_id"]) if row.get("round_id") is not None else None,
        question_id=int(row["question_id"]) if row.get("question_id") is not None else None,
        status=str(row["status"]),
        dimension_scores=_json_dict_list(row.get("dimension_scores")),
        total_score=int(row["total_score"]) if row.get("total_score") is not None else None,
        evidence=_json_string_list(row.get("evidence")),
        result=_json_dict(row.get("result")),
        error_message=row.get("error_message"),
        prompt_version=str(row["prompt_version"]),
        model_name=str(row["model_name"]),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _json_dict(value: Any) -> JSONDict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return None


def _json_dict_list(value: Any) -> list[JSONDict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _json_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []
