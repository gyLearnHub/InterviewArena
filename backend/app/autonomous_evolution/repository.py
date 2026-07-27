from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from app.autonomous_evolution.anonymization import anonymize_payload
from app.autonomous_evolution.catalog import ArtifactSeed
from app.repositories.users import CURRENT_PRIVACY_VERSION

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class BundleRecord:
    id: int
    bundle_key: str
    user_id: int | None
    job_family_key: str
    parent_bundle_id: int | None
    generation: int
    status: str
    is_active: bool
    baseline_quality: float | None
    observation_count: int
    consecutive_failures: int
    activated_at: datetime | None


@dataclass(frozen=True)
class ArtifactRecord:
    id: int
    bundle_id: int
    artifact_key: str
    artifact_type: str
    content: JSONDict
    content_hash: str
    change_summary: str | None


@dataclass(frozen=True)
class EvolutionRunRecord:
    id: int
    user_id: int | None
    job_family_key: str
    trigger_sequence: int
    trigger_interview_count: int
    source_interview_ids: list[int]
    baseline_bundle_id: int
    candidate_bundle_id: int | None
    candidate_artifact_key: str | None
    candidate_artifact_type: str | None
    diagnosis: JSONDict | None
    proposal: JSONDict | None
    validation_summary: JSONDict | None
    decision_summary: JSONDict | None
    status: str
    attempt_count: int
    max_retries: int
    processing_token: str | None
    heartbeat_at: datetime | None
    trigger_cursor_ended_at: datetime | None
    trigger_cursor_interview_id: int | None


class AutonomousEvolutionRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def list_job_family_keys(self, user_id: int | None = None) -> list[str]:
        with self.connection.cursor() as cursor:
            if user_id is None:
                cursor.execute(
                    """
                    SELECT DISTINCT job_family_key
                    FROM interviews
                    WHERE job_family_key IS NOT NULL AND job_family_key <> ''
                    ORDER BY job_family_key
                    LIMIT 200
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT DISTINCT job_family_key
                    FROM interviews
                    WHERE user_id = %s
                      AND job_family_key IS NOT NULL AND job_family_key <> ''
                    ORDER BY job_family_key
                    LIMIT 200
                    """,
                    (user_id,),
                )
            return [str(row["job_family_key"]) for row in cursor.fetchall()]

    def get_status_for_user(self, user_id: int) -> JSONDict:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT job_family_key
                FROM interviews
                WHERE user_id = %s AND job_family_key IS NOT NULL AND job_family_key <> ''
                ORDER BY job_family_key
                LIMIT 200
                """,
                (user_id,),
            )
            family_keys = [str(row["job_family_key"]) for row in cursor.fetchall()]
            families: list[JSONDict] = []
            for family_key in family_keys:
                cursor.execute(
                    """
                    SELECT id, bundle_key, user_id, generation, status, observation_count,
                           consecutive_failures, activated_at
                    FROM harness_artifact_bundles
                    WHERE user_id = %s AND job_family_key = %s AND is_active = 1
                    LIMIT 1
                    """,
                    (user_id, family_key),
                )
                bundle = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT trigger_cursor_ended_at, trigger_cursor_interview_id
                    FROM harness_evolution_runs
                    WHERE user_id = %s AND job_family_key = %s
                    ORDER BY trigger_sequence DESC
                    LIMIT 1
                    """,
                    (user_id, family_key),
                )
                latest = cursor.fetchone()
                cursor_at = latest.get("trigger_cursor_ended_at") if latest else None
                cursor_id = int(latest.get("trigger_cursor_interview_id") or 0) if latest else 0
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM interviews i
                    WHERE i.user_id = %s AND i.job_family_key = %s
                      AND i.overall_status = 'finished'
                      AND i.harness_status = 'completed'
                      AND EXISTS (
                          SELECT 1 FROM feedback_reports f WHERE f.interview_id = i.id
                      )
                      AND (
                          %s IS NULL
                          OR COALESCE(i.ended_at, i.created_at) > %s
                          OR (
                              COALESCE(i.ended_at, i.created_at) = %s
                              AND i.id > %s
                          )
                      )
                    """,
                    (user_id, family_key, cursor_at, cursor_at, cursor_at, cursor_id),
                )
                eligible_count = int(cursor.fetchone()["count"])
                families.append(
                    {
                        "job_family_key": family_key,
                        "active_bundle_id": int(bundle["id"]) if bundle else None,
                        "active_bundle_key": str(bundle["bundle_key"]) if bundle else None,
                        "generation": int(bundle["generation"]) if bundle else 0,
                        "bundle_status": str(bundle["status"]) if bundle else "missing",
                        "observation_count": int(bundle["observation_count"] or 0)
                        if bundle
                        else 0,
                        "consecutive_failures": int(bundle["consecutive_failures"] or 0)
                        if bundle
                        else 0,
                        "eligible_interview_count": eligible_count,
                        "activated_at": bundle.get("activated_at") if bundle else None,
                    }
                )
            cursor.execute(
                """
                SELECT r.id, r.user_id, r.job_family_key, r.trigger_sequence, r.status,
                       r.attempt_count, r.max_retries, r.candidate_artifact_key,
                       r.validation_summary, r.decision_summary, r.error_message,
                       r.created_at, r.started_at, r.heartbeat_at, r.completed_at
                FROM harness_evolution_runs r
                WHERE r.user_id = %s
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 20
                """,
                (user_id,),
            )
            runs = [_json_safe_row(row) for row in cursor.fetchall()]
        return {"families": families, "runs": runs}

    def get_active_bundle(
        self,
        job_family_key: str,
        *,
        user_id: int | None = None,
    ) -> BundleRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_key, user_id, job_family_key, parent_bundle_id,
                       generation, status, is_active, baseline_quality, observation_count,
                       consecutive_failures, activated_at
                FROM harness_artifact_bundles
                WHERE job_family_key = %s AND user_id <=> %s AND is_active = 1
                ORDER BY activated_at DESC, id DESC
                LIMIT 1
                """,
                (job_family_key, user_id),
            )
            return _to_bundle(cursor.fetchone())

    def get_bundle(self, bundle_id: int) -> BundleRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_key, user_id, job_family_key, parent_bundle_id,
                       generation, status, is_active, baseline_quality, observation_count,
                       consecutive_failures, activated_at
                FROM harness_artifact_bundles
                WHERE id = %s
                """,
                (bundle_id,),
            )
            return _to_bundle(cursor.fetchone())

    def ensure_bootstrap_bundle(
        self,
        job_family_key: str,
        artifacts: list[ArtifactSeed],
        *,
        user_id: int | None = None,
    ) -> BundleRecord:
        active = self.get_active_bundle(job_family_key, user_id=user_id)
        if active is not None:
            return active
        digest = hashlib.sha256(
            f"{user_id if user_id is not None else 'legacy'}:{job_family_key}".encode()
        ).hexdigest()[:12]
        bundle_key = f"harness-bootstrap-v1-{digest}"
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT IGNORE INTO harness_artifact_bundles (
                    bundle_key, user_id, job_family_key, generation, status, is_active,
                    activation_reason, activated_at
                ) VALUES (%s, %s, %s, 1, 'active', 1, 'bootstrap-v1', CURRENT_TIMESTAMP)
                """,
                (bundle_key, user_id, job_family_key),
            )
            cursor.execute(
                "SELECT id FROM harness_artifact_bundles WHERE bundle_key = %s",
                (bundle_key,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("failed to create bootstrap Harness bundle")
            bundle_id = int(row["id"])
            for artifact in artifacts:
                cursor.execute(
                    """
                    INSERT IGNORE INTO harness_artifacts (
                        bundle_id, artifact_key, artifact_type, content, content_hash,
                        change_summary
                    ) VALUES (%s, %s, %s, %s, %s, 'bootstrap-v1')
                    """,
                    (
                        bundle_id,
                        artifact.key,
                        artifact.artifact_type,
                        _json_dump(artifact.content),
                        _content_hash(artifact.content),
                    ),
                )
        active = self.get_active_bundle(job_family_key, user_id=user_id)
        if active is None:
            raise RuntimeError("bootstrap Harness bundle is not active")
        return active

    def list_artifacts(self, bundle_id: int) -> list[ArtifactRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_id, artifact_key, artifact_type, content, content_hash,
                       change_summary
                FROM harness_artifacts
                WHERE bundle_id = %s
                ORDER BY artifact_key
                """,
                (bundle_id,),
            )
            return [_to_artifact(row) for row in cursor.fetchall()]

    def get_artifact(self, bundle_id: int, artifact_key: str) -> ArtifactRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, bundle_id, artifact_key, artifact_type, content, content_hash,
                       change_summary
                FROM harness_artifacts
                WHERE bundle_id = %s AND artifact_key = %s
                """,
                (bundle_id, artifact_key),
            )
            row = cursor.fetchone()
        return _to_artifact(row) if row is not None else None

    def create_candidate_bundle(
        self,
        *,
        baseline_bundle_id: int,
        artifact_key: str,
        artifact_type: str,
        content: JSONDict,
        change_summary: str,
        run_id: int,
        processing_token: str,
    ) -> BundleRecord:
        baseline = self.get_bundle(baseline_bundle_id)
        if baseline is None:
            raise ValueError("baseline bundle not found")
        artifacts = self.list_artifacts(baseline_bundle_id)
        if artifact_key not in {item.artifact_key for item in artifacts}:
            raise ValueError("candidate targets an unknown artifact")
        digest = _content_hash(content)[:12]
        nonce = uuid4().hex[:8]
        scope = baseline.user_id if baseline.user_id is not None else "legacy"
        bundle_key = f"harness-evo-{scope}-{baseline.job_family_key}-{run_id}-{digest}-{nonce}"
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM harness_evolution_runs
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                  AND baseline_bundle_id = %s AND candidate_bundle_id IS NULL
                FOR UPDATE
                """,
                (run_id, processing_token, baseline_bundle_id),
            )
            if cursor.fetchone() is None:
                raise RuntimeError("evolution run lease was lost before candidate creation")
            cursor.execute(
                """
                INSERT INTO harness_artifact_bundles (
                    bundle_key, user_id, job_family_key, parent_bundle_id, generation,
                    status, is_active, activation_reason
                ) VALUES (%s, %s, %s, %s, %s, 'candidate', 0, %s)
                """,
                (
                    bundle_key,
                    baseline.user_id,
                    baseline.job_family_key,
                    baseline.id,
                    baseline.generation + 1,
                    f"autonomous evolution run {run_id}",
                ),
            )
            bundle_id = int(cursor.lastrowid)
            for artifact in artifacts:
                next_content = (
                    content
                    if artifact.artifact_key == artifact_key
                    else artifact.content
                )
                cursor.execute(
                    """
                    INSERT INTO harness_artifacts (
                        bundle_id, artifact_key, artifact_type, content, content_hash,
                        change_summary
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        bundle_id,
                        artifact.artifact_key,
                        artifact_type
                        if artifact.artifact_key == artifact_key
                        else artifact.artifact_type,
                        _json_dump(next_content),
                        _content_hash(next_content),
                        change_summary if artifact.artifact_key == artifact_key else None,
                    ),
                )
        candidate = self.get_bundle(bundle_id)
        if candidate is None:
            raise RuntimeError("candidate bundle was not created")
        return candidate

    def assign_interview_context(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
        job_family_key: str,
        bundle_id: int,
    ) -> None:
        with self.connection.cursor() as cursor:
            if user_id is None:
                cursor.execute(
                    """
                    UPDATE interviews
                    SET job_family_key = %s, harness_bundle_id = %s
                    WHERE id = %s
                    """,
                    (job_family_key, bundle_id, interview_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE interviews
                    SET job_family_key = %s, harness_bundle_id = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (job_family_key, bundle_id, interview_id, user_id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("interview is not owned by the requested user")

    def apply_pending_round_limits(
        self,
        interview_id: int,
        *,
        user_id: int,
        limits: dict[str, tuple[int, int]],
    ) -> int:
        updated = 0
        with self.connection.cursor() as cursor:
            for round_type, (max_main_questions, max_total_questions) in limits.items():
                cursor.execute(
                    """
                    UPDATE interview_rounds r
                    JOIN interviews i ON i.id = r.interview_id
                    SET r.max_main_questions = %s,
                        r.max_total_questions = %s
                    WHERE r.interview_id = %s
                      AND r.round_type = %s
                      AND r.status = 'pending'
                      AND i.user_id = %s
                    """,
                    (
                        max_main_questions,
                        max_total_questions,
                        interview_id,
                        round_type,
                        user_id,
                    ),
                )
                updated += int(cursor.rowcount)
        return updated

    def get_next_unbound_interview(self) -> JSONDict | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT i.id, i.user_id, i.target_position, i.job_description
                FROM interviews i
                JOIN users u ON u.id = i.user_id
                WHERE (i.job_family_key IS NULL OR i.harness_bundle_id IS NULL)
                  AND u.external_model_consent_at IS NOT NULL
                  AND u.external_model_consent_version = %s
                ORDER BY i.created_at ASC, i.id ASC
                LIMIT 1
                """,
                (CURRENT_PRIVACY_VERSION,),
            )
            row = cursor.fetchone()
        return _json_safe_row(row) if row is not None else None

    def enqueue_if_due(
        self,
        *,
        user_id: int,
        job_family_key: str,
        trigger_every: int,
        max_retries: int,
    ) -> int | None:
        if trigger_every <= 0:
            return None
        active = self.get_active_bundle(job_family_key, user_id=user_id)
        if active is None:
            return None
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM harness_artifact_bundles WHERE id = %s FOR UPDATE",
                (active.id,),
            )
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM interviews i
                WHERE i.user_id = %s
                  AND i.job_family_key = %s
                  AND i.overall_status = 'finished'
                  AND i.harness_status = 'completed'
                  AND EXISTS (
                      SELECT 1 FROM feedback_reports f WHERE f.interview_id = i.id
                  )
                """,
                (user_id, job_family_key),
            )
            completed_count = int(cursor.fetchone()["count"])
            cursor.execute(
                """
                SELECT trigger_sequence, trigger_cursor_ended_at,
                       trigger_cursor_interview_id
                FROM harness_evolution_runs
                WHERE user_id = %s AND job_family_key = %s
                ORDER BY trigger_sequence DESC
                LIMIT 1
                FOR UPDATE
                """,
                (user_id, job_family_key),
            )
            latest = cursor.fetchone()
            trigger_sequence = int(latest["trigger_sequence"]) + 1 if latest else 1
            cursor_ended_at = latest.get("trigger_cursor_ended_at") if latest else None
            cursor_interview_id = (
                int(latest["trigger_cursor_interview_id"])
                if latest and latest.get("trigger_cursor_interview_id") is not None
                else 0
            )
            cursor.execute(
                """
                SELECT i.id, COALESCE(i.ended_at, i.created_at) AS cursor_at
                FROM interviews i
                WHERE i.user_id = %s
                  AND i.job_family_key = %s
                  AND i.overall_status = 'finished'
                  AND i.harness_status = 'completed'
                  AND EXISTS (
                      SELECT 1 FROM feedback_reports f WHERE f.interview_id = i.id
                  )
                  AND (
                      %s IS NULL
                      OR COALESCE(i.ended_at, i.created_at) > %s
                      OR (
                          COALESCE(i.ended_at, i.created_at) = %s
                          AND i.id > %s
                      )
                  )
                ORDER BY COALESCE(i.ended_at, i.created_at), i.id
                LIMIT %s
                """,
                (
                    user_id,
                    job_family_key,
                    cursor_ended_at,
                    cursor_ended_at,
                    cursor_ended_at,
                    cursor_interview_id,
                    trigger_every,
                ),
            )
            source_rows = list(cursor.fetchall())
            if len(source_rows) != trigger_every:
                return None
            source_ids = [int(row["id"]) for row in source_rows]
            last_source = source_rows[-1]
            cursor.execute(
                """
                INSERT IGNORE INTO harness_evolution_runs (
                    user_id, job_family_key, trigger_sequence, trigger_interview_count,
                    source_interview_ids, baseline_bundle_id, status, max_retries,
                    trigger_cursor_ended_at, trigger_cursor_interview_id
                ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
                """,
                (
                    user_id,
                    job_family_key,
                    trigger_sequence,
                    completed_count,
                    _json_dump(source_ids),
                    active.id,
                    max_retries,
                    last_source["cursor_at"],
                    last_source["id"],
                ),
            )
            if cursor.rowcount == 0:
                return None
            run_id = int(cursor.lastrowid)
        self.record_event(run_id=run_id, event_type="evolution_enqueued", payload={})
        return run_id

    def rebase_run_to_active(
        self,
        run: EvolutionRunRecord,
    ) -> EvolutionRunRecord:
        active = self.get_active_bundle(run.job_family_key, user_id=run.user_id)
        if active is None:
            raise RuntimeError("job family has no active Harness bundle")
        if active.id == run.baseline_bundle_id:
            return run
        if run.candidate_bundle_id is not None:
            raise RuntimeError("cannot rebase a run after candidate creation")
        token = self._require_processing_token(run)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET baseline_bundle_id = %s
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                  AND candidate_bundle_id IS NULL
                """,
                (active.id, run.id, token),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("evolution run could not be rebased")
        self.record_event(
            run_id=run.id,
            bundle_id=active.id,
            event_type="evolution_run_rebased",
            payload={"previous_baseline_bundle_id": run.baseline_bundle_id},
        )
        return replace(run, baseline_bundle_id=active.id)

    def claim_due_run(self, processing_timeout_seconds: int) -> EvolutionRunRecord | None:
        timeout_at = datetime.utcnow() - timedelta(seconds=max(1, processing_timeout_seconds))
        token = uuid4().hex
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.candidate_bundle_id,
                       b.is_active AS candidate_is_active,
                       b.status AS candidate_status
                FROM harness_evolution_runs r
                LEFT JOIN harness_artifact_bundles b ON b.id = r.candidate_bundle_id
                WHERE r.status = 'processing'
                  AND COALESCE(r.heartbeat_at, r.started_at) < %s
                FOR UPDATE
                """,
                (timeout_at,),
            )
            expired_runs = list(cursor.fetchall())
            for expired in expired_runs:
                candidate_bundle_id = expired.get("candidate_bundle_id")
                if candidate_bundle_id is not None:
                    if bool(expired.get("candidate_is_active")) and str(
                        expired.get("candidate_status") or ""
                    ) == "observing":
                        cursor.execute(
                            """
                            UPDATE harness_evolution_runs
                            SET status = 'observing', processing_token = NULL,
                                completed_at = CURRENT_TIMESTAMP, heartbeat_at = NULL,
                                error_message = 'processing lease expired after activation',
                                decision_summary = JSON_SET(
                                    COALESCE(decision_summary, JSON_OBJECT()),
                                    '$.finalized_after_activation_timeout', true
                                )
                            WHERE id = %s AND status = 'processing'
                              AND candidate_bundle_id = %s
                            """,
                            (expired["id"], candidate_bundle_id),
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE harness_artifact_bundles
                            SET status = 'rejected', is_active = 0
                            WHERE id = %s AND is_active = 0
                            """,
                            (candidate_bundle_id,),
                        )
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET status = 'retry_wait', processing_token = NULL,
                    next_retry_at = CURRENT_TIMESTAMP,
                    error_message = 'processing lease expired', heartbeat_at = NULL,
                    candidate_bundle_id = NULL, candidate_artifact_key = NULL,
                    candidate_artifact_type = NULL, diagnosis = NULL, proposal = NULL,
                    anonymization_status = 'pending'
                WHERE status = 'processing'
                  AND COALESCE(heartbeat_at, started_at) < %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM harness_artifact_bundles b
                      WHERE b.id = harness_evolution_runs.candidate_bundle_id
                        AND b.is_active = 1
                        AND b.status = 'observing'
                  )
                """,
                (timeout_at,),
            )
            cursor.execute(
                """
                SELECT r.id
                FROM harness_evolution_runs r
                JOIN users u ON u.id = r.user_id
                WHERE r.status IN ('pending', 'retry_wait')
                  AND (r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)
                  AND u.external_model_consent_at IS NOT NULL
                  AND u.external_model_consent_version = %s
                ORDER BY r.created_at, r.id
                LIMIT 1
                FOR UPDATE
                """,
                (CURRENT_PRIVACY_VERSION,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            run_id = int(row["id"])
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET status = 'processing', processing_token = %s,
                    started_at = CURRENT_TIMESTAMP, attempt_count = attempt_count + 1,
                    heartbeat_at = CURRENT_TIMESTAMP,
                    next_retry_at = NULL, error_message = NULL
                WHERE id = %s AND status IN ('pending', 'retry_wait')
                """,
                (token, run_id),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_run(run_id)

    def heartbeat_run(self, run_id: int, processing_token: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET heartbeat_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                """,
                (run_id, processing_token),
            )
            if int(cursor.rowcount) == 1:
                return True
            cursor.execute(
                """
                SELECT id
                FROM harness_evolution_runs
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                """,
                (run_id, processing_token),
            )
            return cursor.fetchone() is not None

    def assert_run_lease(self, run_id: int, processing_token: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM harness_evolution_runs
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                """,
                (run_id, processing_token),
            )
            if cursor.fetchone() is None:
                raise RuntimeError("evolution run processing lease is no longer owned")

    def get_run(self, run_id: int) -> EvolutionRunRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, user_id, job_family_key, trigger_sequence, trigger_interview_count,
                       source_interview_ids, baseline_bundle_id, candidate_bundle_id,
                       candidate_artifact_key, candidate_artifact_type, diagnosis, proposal,
                       validation_summary, decision_summary, status, attempt_count, max_retries,
                       processing_token, heartbeat_at, trigger_cursor_ended_at,
                       trigger_cursor_interview_id
                FROM harness_evolution_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cursor.fetchone()
        return _to_run(row) if row is not None else None

    def update_run_candidate(
        self,
        run_id: int,
        *,
        candidate_bundle_id: int,
        artifact_key: str,
        artifact_type: str,
        diagnosis: JSONDict,
        proposal: JSONDict,
        processing_token: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET candidate_bundle_id = %s, candidate_artifact_key = %s,
                    candidate_artifact_type = %s, diagnosis = %s, proposal = %s,
                    anonymization_status = 'completed'
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                """,
                (
                    candidate_bundle_id,
                    artifact_key,
                    artifact_type,
                    _json_dump(diagnosis),
                    _json_dump(proposal),
                    run_id,
                    processing_token,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("evolution run lease was lost while saving candidate")

    def save_sample(
        self,
        *,
        run_id: int,
        sample_key: str,
        sample_type: str,
        source_interview_id: int | None,
        input_payload: JSONDict,
        baseline_output: JSONDict | None,
        candidate_output: JSONDict | None,
        objective_metrics: JSONDict,
        judge_results: list[JSONDict],
        winner: str | None,
        hard_gate_status: str,
        processing_token: str,
    ) -> None:
        safe_input = anonymize_payload(input_payload)
        safe_baseline = anonymize_payload(baseline_output) if baseline_output is not None else None
        safe_candidate = (
            anonymize_payload(candidate_output) if candidate_output is not None else None
        )
        safe_judges = anonymize_payload(judge_results)
        self.assert_run_lease(run_id, processing_token)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO harness_evolution_samples (
                    run_id, sample_key, sample_type, source_interview_id, input_payload,
                    baseline_output, candidate_output, objective_metrics, judge_results,
                    winner, hard_gate_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    baseline_output = VALUES(baseline_output),
                    candidate_output = VALUES(candidate_output),
                    objective_metrics = VALUES(objective_metrics),
                    judge_results = VALUES(judge_results),
                    winner = VALUES(winner),
                    hard_gate_status = VALUES(hard_gate_status)
                """,
                (
                    run_id,
                    sample_key,
                    sample_type,
                    source_interview_id,
                    _json_dump(safe_input),
                    _json_dump_or_none(safe_baseline),
                    _json_dump_or_none(safe_candidate),
                    _json_dump(objective_metrics),
                    _json_dump(safe_judges),
                    winner,
                    hard_gate_status,
                ),
            )

    def complete_run(
        self,
        run_id: int,
        *,
        status: str,
        validation_summary: JSONDict,
        decision_summary: JSONDict,
        processing_token: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET status = %s, validation_summary = %s, decision_summary = %s,
                    processing_token = NULL, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                """,
                (
                    status,
                    _json_dump(validation_summary),
                    _json_dump(decision_summary),
                    run_id,
                    processing_token,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("evolution run lease was lost before completion")

    def fail_or_retry_run(self, run: EvolutionRunRecord, error_message: str) -> None:
        token = self._require_processing_token(run)
        retry_cycle_exhausted = run.attempt_count > run.max_retries
        next_retry = datetime.utcnow() + timedelta(
            seconds=300
            if retry_cycle_exhausted
            else min(300, 5 * (2 ** max(0, run.attempt_count - 1)))
        )
        finalized_after_activation = False
        with self.connection.cursor() as cursor:
            if run.candidate_bundle_id is not None:
                cursor.execute(
                    """
                    SELECT is_active, status
                    FROM harness_artifact_bundles
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (run.candidate_bundle_id,),
                )
                candidate = cursor.fetchone()
                if (
                    candidate is not None
                    and bool(candidate.get("is_active"))
                    and str(candidate.get("status") or "") == "observing"
                ):
                    cursor.execute(
                        """
                        UPDATE harness_evolution_runs
                        SET status = 'observing', processing_token = NULL,
                            heartbeat_at = NULL, completed_at = CURRENT_TIMESTAMP,
                            error_message = %s,
                            decision_summary = JSON_SET(
                                COALESCE(decision_summary, JSON_OBJECT()),
                                '$.finalized_after_activation_failure', true,
                                '$.activation_failure_error', %s
                            )
                        WHERE id = %s AND status = 'processing'
                          AND processing_token = %s AND candidate_bundle_id = %s
                        """,
                        (
                            error_message[:1000],
                            error_message[:500],
                            run.id,
                            token,
                            run.candidate_bundle_id,
                        ),
                    )
                    finalized_after_activation = cursor.rowcount == 1
            if not finalized_after_activation:
                cursor.execute(
                    """
                    UPDATE harness_evolution_runs
                    SET status = 'retry_wait', next_retry_at = %s, processing_token = NULL,
                        heartbeat_at = NULL, completed_at = NULL, error_message = %s,
                        attempt_count = %s, candidate_bundle_id = NULL,
                        candidate_artifact_key = NULL, candidate_artifact_type = NULL,
                        diagnosis = NULL, proposal = NULL, anonymization_status = 'pending'
                    WHERE id = %s AND status = 'processing' AND processing_token = %s
                    """,
                    (
                        next_retry,
                        error_message[:1000],
                        0 if retry_cycle_exhausted else run.attempt_count,
                        run.id,
                        token,
                    ),
                )
                if cursor.rowcount != 1:
                    return
                if run.candidate_bundle_id is not None:
                    cursor.execute(
                        """
                        UPDATE harness_artifact_bundles
                        SET status = 'rejected', is_active = 0
                        WHERE id = %s AND is_active = 0
                        """,
                        (run.candidate_bundle_id,),
                    )
        self.record_event(
            run_id=run.id,
            event_type="evolution_run_finalized_after_activation_failure"
            if finalized_after_activation
            else "evolution_retry_cycle_reset"
            if retry_cycle_exhausted
            else "evolution_retry_scheduled",
            payload={"attempt": run.attempt_count, "error": error_message[:500]},
        )

    def activate_candidate_and_complete_run(
        self,
        *,
        run_id: int,
        baseline_bundle_id: int,
        candidate_bundle_id: int,
        baseline_quality: float,
        validation_summary: JSONDict,
        decision_summary: JSONDict,
        processing_token: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM harness_evolution_runs
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                  AND baseline_bundle_id = %s AND candidate_bundle_id = %s
                FOR UPDATE
                """,
                (run_id, processing_token, baseline_bundle_id, candidate_bundle_id),
            )
            if cursor.fetchone() is None:
                raise RuntimeError("evolution run lease was lost before activation")
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 0, status = 'superseded'
                WHERE id = %s AND is_active = 1
                """,
                (baseline_bundle_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("baseline Harness bundle is no longer active")
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 1, status = 'observing', baseline_quality = %s,
                    observation_count = 0, consecutive_failures = 0,
                    activated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND is_active = 0
                """,
                (baseline_quality, candidate_bundle_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("candidate Harness bundle could not be activated")
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET status = 'observing', validation_summary = %s, decision_summary = %s,
                    processing_token = NULL, completed_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                  AND candidate_bundle_id = %s
                """,
                (
                    _json_dump(validation_summary),
                    _json_dump(decision_summary),
                    run_id,
                    processing_token,
                    candidate_bundle_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("evolution run lease was lost before completion")
        self.record_event(
            run_id=run_id,
            bundle_id=candidate_bundle_id,
            event_type="candidate_activated",
            payload={"baseline_bundle_id": baseline_bundle_id},
        )

    def activate_candidate(
        self,
        *,
        run_id: int,
        baseline_bundle_id: int,
        candidate_bundle_id: int,
        baseline_quality: float,
        processing_token: str,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM harness_evolution_runs
                WHERE id = %s AND status = 'processing' AND processing_token = %s
                FOR UPDATE
                """,
                (run_id, processing_token),
            )
            if cursor.fetchone() is None:
                raise RuntimeError("evolution run lease was lost before activation")
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 0, status = 'superseded'
                WHERE id = %s AND is_active = 1
                """,
                (baseline_bundle_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("baseline Harness bundle is no longer active")
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 1, status = 'observing', baseline_quality = %s,
                    observation_count = 0, consecutive_failures = 0,
                    activated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (baseline_quality, candidate_bundle_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("candidate Harness bundle could not be activated")
        self.record_event(
            run_id=run_id,
            bundle_id=candidate_bundle_id,
            event_type="candidate_activated",
            payload={"baseline_bundle_id": baseline_bundle_id},
        )

    def reject_candidate(self, bundle_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE harness_artifact_bundles SET status = 'rejected' WHERE id = %s",
                (bundle_id,),
            )

    @staticmethod
    def _require_processing_token(run: EvolutionRunRecord) -> str:
        if not run.processing_token:
            raise RuntimeError("evolution run has no processing lease token")
        return run.processing_token

    def get_interview_bundle(self, interview_id: int) -> BundleRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT b.id, b.bundle_key, b.user_id, b.job_family_key, b.parent_bundle_id,
                       b.generation, b.status, b.is_active, b.baseline_quality,
                       b.observation_count, b.consecutive_failures, b.activated_at
                FROM interviews i
                JOIN harness_artifact_bundles b ON b.id = i.harness_bundle_id
                WHERE i.id = %s
                """,
                (interview_id,),
            )
            return _to_bundle(cursor.fetchone())

    def record_observation(
        self,
        *,
        bundle_id: int,
        interview_id: int,
        quality_score: float,
        hard_error: bool,
        metrics: JSONDict,
    ) -> tuple[int, float, bool]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT i.harness_bundle_id, b.is_active, b.status
                FROM interviews i
                JOIN harness_artifact_bundles b ON b.id = i.harness_bundle_id
                WHERE i.id = %s
                FOR UPDATE
                """,
                (interview_id,),
            )
            binding = cursor.fetchone()
            if (
                binding is None
                or int(binding["harness_bundle_id"]) != bundle_id
                or not bool(binding["is_active"])
                or binding["status"] != "observing"
            ):
                raise RuntimeError(
                    "observation interview is not bound to the active observing bundle"
                )
            cursor.execute(
                """
                INSERT IGNORE INTO harness_evolution_observations (
                    bundle_id, interview_id, quality_score, hard_error, metrics
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (bundle_id, interview_id, quality_score, hard_error, _json_dump(metrics)),
            )
            cursor.execute(
                """
                SELECT COUNT(*) AS count, AVG(quality_score) AS average_quality,
                       MAX(hard_error) AS has_hard_error
                FROM harness_evolution_observations
                WHERE bundle_id = %s
                """,
                (bundle_id,),
            )
            summary = cursor.fetchone()
            count = int(summary["count"])
            average = float(summary["average_quality"] or 0.0)
            has_hard_error = bool(summary["has_hard_error"])
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET observation_count = %s
                WHERE id = %s
                """,
                (count, bundle_id),
            )
        return count, average, has_hard_error

    def finish_observation(self, bundle_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET status = 'active'
                WHERE id = %s AND is_active = 1 AND status = 'observing'
                """,
                (bundle_id,),
            )
        self.record_event(
            bundle_id=bundle_id,
            event_type="observation_passed",
            payload={},
        )

    def rollback_bundle(self, bundle_id: int, *, reason: str) -> bool:
        bundle = self.get_bundle(bundle_id)
        if bundle is None or bundle.parent_bundle_id is None:
            return False
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 0, status = 'rolled_back', rolled_back_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (bundle.id,),
            )
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET is_active = 1, status = 'active', consecutive_failures = 0,
                    activation_reason = %s, activated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (f"rollback from {bundle.bundle_key}: {reason}"[:500], bundle.parent_bundle_id),
            )
            cursor.execute(
                """
                UPDATE interviews
                SET harness_bundle_id = %s
                WHERE harness_bundle_id = %s AND overall_status <> 'finished'
                """,
                (bundle.parent_bundle_id, bundle.id),
            )
            cursor.execute(
                """
                UPDATE harness_evolution_runs
                SET status = 'rolled_back', decision_summary = JSON_SET(
                    COALESCE(decision_summary, JSON_OBJECT()),
                    '$.rollback_reason', %s,
                    '$.rolled_back', true
                )
                WHERE candidate_bundle_id = %s
                """,
                (reason[:500], bundle.id),
            )
        self.record_event(
            bundle_id=bundle.id,
            event_type="candidate_rolled_back",
            payload={
                "reason": reason,
                "restored_bundle_id": bundle.parent_bundle_id,
            },
        )
        return True

    def record_execution_outcome(
        self,
        interview_id: int,
        *,
        succeeded: bool,
        hard_error: bool = False,
    ) -> bool:
        bundle = self.get_interview_bundle(interview_id)
        if bundle is None or bundle.generation <= 1 or not bundle.is_active:
            return False
        if hard_error:
            return self.rollback_bundle(
                bundle.id,
                reason="runtime privacy, structure, or score hard gate failed",
            )
        with self.connection.cursor() as cursor:
            if succeeded:
                cursor.execute(
                    """
                    UPDATE harness_artifact_bundles
                    SET consecutive_failures = 0
                    WHERE id = %s
                    """,
                    (bundle.id,),
                )
                return False
            cursor.execute(
                """
                UPDATE harness_artifact_bundles
                SET consecutive_failures = consecutive_failures + 1
                WHERE id = %s
                """,
                (bundle.id,),
            )
            cursor.execute(
                "SELECT consecutive_failures FROM harness_artifact_bundles WHERE id = %s",
                (bundle.id,),
            )
            failures = int(cursor.fetchone()["consecutive_failures"])
        if failures >= 2:
            return self.rollback_bundle(
                bundle.id,
                reason="two consecutive runtime execution failures",
            )
        return False

    def record_event(
        self,
        *,
        event_type: str,
        payload: JSONDict,
        run_id: int | None = None,
        bundle_id: int | None = None,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO harness_evolution_events (run_id, bundle_id, event_type, payload)
                VALUES (%s, %s, %s, %s)
                """,
                (run_id, bundle_id, event_type, _json_dump(payload)),
            )

    def load_interview_sample(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
    ) -> JSONDict:
        owner_clause = "AND i.user_id = %s" if user_id is not None else ""
        params: tuple[Any, ...] = (
            (interview_id, user_id) if user_id is not None else (interview_id,)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT i.id, i.target_position, i.job_description, i.interview_goal,
                       i.difficulty, i.time_limit_minutes, i.selected_rounds,
                       i.harness_status, i.had_degradation, r.structured_data AS resume,
                       f.score AS report_score, f.recommendation, f.strengths,
                       f.weaknesses, f.suggestions, f.report_reliability_status
                FROM interviews i
                JOIN resumes r ON r.id = i.resume_id
                LEFT JOIN feedback_reports f ON f.interview_id = i.id
                WHERE i.id = %s
                {owner_clause}
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("source interview not found")
            cursor.execute(
                """
                SELECT qa.id, qa.round_id, ir.round_type, qa.sequence, qa.question_type,
                       qa.question_kind, qa.question, qa.answer, qa.question_status
                FROM interview_qa qa
                LEFT JOIN interview_rounds ir ON ir.id = qa.round_id
                WHERE qa.interview_id = %s
                ORDER BY ir.id, qa.sequence, qa.id
                """,
                (interview_id,),
            )
            qa_history = [_json_safe_row(item) for item in cursor.fetchall()]
            cursor.execute(
                """
                SELECT round_type, score, result, summary, is_reference_only
                FROM interview_rounds
                WHERE interview_id = %s
                ORDER BY id
                """,
                (interview_id,),
            )
            rounds = [_json_safe_row(item) for item in cursor.fetchall()]
            cursor.execute(
                """
                SELECT node_type, purpose, validation_status, status, error_code,
                       output_snapshot, retry_records, degradation_records
                FROM harness_traces
                WHERE interview_id = %s
                ORDER BY created_at, id
                """,
                (interview_id,),
            )
            traces = [_json_safe_row(item) for item in cursor.fetchall()]
            cursor.execute(
                """
                SELECT rule_name, status, severity, overall_grade
                FROM harness_rule_evaluations
                WHERE interview_id = %s
                ORDER BY created_at, id
                """,
                (interview_id,),
            )
            rules = [_json_safe_row(item) for item in cursor.fetchall()]
            cursor.execute(
                """
                SELECT feedback_type, content, rating
                FROM user_feedback_submissions
                WHERE interview_id = %s
                ORDER BY created_at, id
                """,
                (interview_id,),
            )
            feedback = [_json_safe_row(item) for item in cursor.fetchall()]
        payload = _json_safe_row(row)
        payload.update(
            {
                "qa_history": qa_history,
                "rounds": rounds,
                "harness_traces": traces,
                "harness_rules": rules,
                "user_feedback": feedback,
            }
        )
        return payload


def _to_bundle(row: dict[str, Any] | None) -> BundleRecord | None:
    if row is None:
        return None
    return BundleRecord(
        id=int(row["id"]),
        bundle_key=str(row["bundle_key"]),
        user_id=int(row["user_id"]) if row.get("user_id") is not None else None,
        job_family_key=str(row["job_family_key"]),
        parent_bundle_id=int(row["parent_bundle_id"])
        if row.get("parent_bundle_id") is not None
        else None,
        generation=int(row["generation"]),
        status=str(row["status"]),
        is_active=bool(row["is_active"]),
        baseline_quality=float(row["baseline_quality"])
        if row.get("baseline_quality") is not None
        else None,
        observation_count=int(row.get("observation_count") or 0),
        consecutive_failures=int(row.get("consecutive_failures") or 0),
        activated_at=row.get("activated_at"),
    )


def _to_artifact(row: dict[str, Any]) -> ArtifactRecord:
    return ArtifactRecord(
        id=int(row["id"]),
        bundle_id=int(row["bundle_id"]),
        artifact_key=str(row["artifact_key"]),
        artifact_type=str(row["artifact_type"]),
        content=_json_dict(row["content"]),
        content_hash=str(row["content_hash"]),
        change_summary=row.get("change_summary"),
    )


def _to_run(row: dict[str, Any]) -> EvolutionRunRecord:
    return EvolutionRunRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]) if row.get("user_id") is not None else None,
        job_family_key=str(row["job_family_key"]),
        trigger_sequence=int(row["trigger_sequence"]),
        trigger_interview_count=int(row["trigger_interview_count"]),
        source_interview_ids=[int(item) for item in _json_list(row["source_interview_ids"])],
        baseline_bundle_id=int(row["baseline_bundle_id"]),
        candidate_bundle_id=int(row["candidate_bundle_id"])
        if row.get("candidate_bundle_id") is not None
        else None,
        candidate_artifact_key=row.get("candidate_artifact_key"),
        candidate_artifact_type=row.get("candidate_artifact_type"),
        diagnosis=_json_dict_or_none(row.get("diagnosis")),
        proposal=_json_dict_or_none(row.get("proposal")),
        validation_summary=_json_dict_or_none(row.get("validation_summary")),
        decision_summary=_json_dict_or_none(row.get("decision_summary")),
        status=str(row["status"]),
        attempt_count=int(row["attempt_count"]),
        max_retries=int(row["max_retries"]),
        processing_token=row.get("processing_token"),
        heartbeat_at=row.get("heartbeat_at"),
        trigger_cursor_ended_at=row.get("trigger_cursor_ended_at"),
        trigger_cursor_interview_id=int(row["trigger_cursor_interview_id"])
        if row.get("trigger_cursor_interview_id") is not None
        else None,
    )


def _content_hash(value: JSONDict) -> str:
    return hashlib.sha256(_json_dump(value).encode("utf-8")).hexdigest()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_dump_or_none(value: Any | None) -> str | None:
    return _json_dump(value) if value is not None else None


def _json_dict(value: Any) -> JSONDict:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value or {})


def _json_dict_or_none(value: Any) -> JSONDict | None:
    return None if value is None else _json_dict(value)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return list(value or [])


def _json_safe_row(row: dict[str, Any]) -> JSONDict:
    result: JSONDict = {}
    for key, value in row.items():
        if isinstance(value, str) and key in {
            "resume",
            "selected_rounds",
            "strengths",
            "weaknesses",
            "suggestions",
            "summary",
            "retry_records",
            "degradation_records",
            "output_snapshot",
            "validation_summary",
            "decision_summary",
        }:
            try:
                result[key] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result
