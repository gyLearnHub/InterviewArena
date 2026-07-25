import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

if __package__ in {None, ""}:
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

from app.autonomous_evolution.catalog import bootstrap_artifacts
from app.autonomous_evolution.repository import AutonomousEvolutionRepository
from app.db.mysql import create_connection
from app.repositories.history import HistoryRepository


def verify(connection: Any) -> dict[str, bool]:
    repository = AutonomousEvolutionRepository(connection)
    suffix = uuid4().hex[:12]
    family_key = f"verification-{suffix}"
    resume_snapshot = {"skills": ["Python"]}
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (f"evolution-check-{suffix}", "not-a-real-password-hash"),
        )
        user_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO resumes (user_id, original_file_path, structured_data)
            VALUES (%s, %s, %s)
            """,
            (user_id, "verification-only", json.dumps(resume_snapshot)),
        )
        resume_id = int(cursor.lastrowid)

    baseline = repository.ensure_bootstrap_bundle(
        family_key,
        bootstrap_artifacts(),
        user_id=user_id,
    )
    interview_ids: list[int] = []
    with connection.cursor() as cursor:
        for index in range(10):
            cursor.execute(
                """
                INSERT INTO interviews (
                    user_id, resume_id, resume_snapshot, target_position, status, mode,
                    job_description, selected_rounds, job_family_key,
                    harness_bundle_id, overall_status, ended_at, harness_status
                ) VALUES (
                    %s, %s, %s, '事务验证工程师', 'finished', 'multi_round',
                    '仅用于自动进化事务验证', %s, %s,
                    %s, 'finished', DATE_ADD('2026-01-01 00:00:00', INTERVAL %s SECOND),
                    'completed'
                )
                """,
                (
                    user_id,
                    resume_id,
                    json.dumps(resume_snapshot),
                    json.dumps(["technical"]),
                    family_key,
                    baseline.id,
                    index,
                ),
            )
            interview_id = int(cursor.lastrowid)
            interview_ids.append(interview_id)
            cursor.execute(
                """
                INSERT INTO feedback_reports (
                    interview_id, score, weaknesses, suggestions, recommendation
                ) VALUES (%s, 85, %s, %s, 'recommended')
                """,
                (interview_id, json.dumps([]), json.dumps(["继续保持"])),
            )

    run_id = repository.enqueue_if_due(
        user_id=user_id,
        job_family_key=family_key,
        trigger_every=10,
        max_retries=3,
    )
    if run_id is None:
        raise RuntimeError("ten valid interviews did not enqueue an evolution run")
    if repository.enqueue_if_due(
        user_id=user_id,
        job_family_key=family_key,
        trigger_every=10,
        max_retries=3,
    ) is not None:
        raise RuntimeError("the same trigger batch was enqueued twice")

    claimed = repository.claim_due_run(processing_timeout_seconds=3600)
    if claimed is None or claimed.id != run_id or not claimed.processing_token:
        raise RuntimeError("the due evolution run was not claimed with a lease")
    token = claimed.processing_token
    if not repository.heartbeat_run(claimed.id, token):
        raise RuntimeError("the owned evolution lease could not heartbeat")

    baseline_artifact = repository.get_artifact(baseline.id, "interviewer.technical")
    if baseline_artifact is None:
        raise RuntimeError("bootstrap technical interviewer artifact is missing")
    candidate_creation_token_rejected = False
    try:
        repository.create_candidate_bundle(
            baseline_bundle_id=baseline.id,
            artifact_key=baseline_artifact.artifact_key,
            artifact_type=baseline_artifact.artifact_type,
            content=baseline_artifact.content,
            change_summary="stale transaction verification candidate",
            run_id=claimed.id,
            processing_token="stale-token",
        )
    except RuntimeError:
        candidate_creation_token_rejected = True
    if not candidate_creation_token_rejected:
        raise RuntimeError("a stale worker created an evolution candidate")
    candidate = repository.create_candidate_bundle(
        baseline_bundle_id=baseline.id,
        artifact_key=baseline_artifact.artifact_key,
        artifact_type=baseline_artifact.artifact_type,
        content=baseline_artifact.content,
        change_summary="transaction verification candidate",
        run_id=claimed.id,
        processing_token=token,
    )
    repository.update_run_candidate(
        claimed.id,
        candidate_bundle_id=candidate.id,
        artifact_key=baseline_artifact.artifact_key,
        artifact_type=baseline_artifact.artifact_type,
        diagnosis={"summary": "verification"},
        proposal={"summary": "verification"},
        processing_token=token,
    )
    repository.save_sample(
        run_id=claimed.id,
        sample_key="real-01",
        sample_type="real",
        source_interview_id=interview_ids[0],
        input_payload={"id": interview_ids[0], "answer": "匿名验证回答"},
        baseline_output={"question": "基线验证问题"},
        candidate_output={"question": "候选验证问题"},
        objective_metrics={"baseline": {"valid_output": 1.0}},
        judge_results=[],
        winner="candidate",
        hard_gate_status="passed",
        processing_token=token,
    )
    stale_token_rejected = False
    try:
        repository.complete_run(
            claimed.id,
            status="rejected",
            validation_summary={},
            decision_summary={},
            processing_token="stale-token",
        )
    except RuntimeError:
        stale_token_rejected = True
    if not stale_token_rejected:
        raise RuntimeError("a stale worker completed an evolution run")

    repository.activate_candidate_and_complete_run(
        run_id=claimed.id,
        baseline_bundle_id=baseline.id,
        candidate_bundle_id=candidate.id,
        baseline_quality=0.85,
        validation_summary={"passed": True},
        decision_summary={"activate": True},
        processing_token=token,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE interviews SET harness_bundle_id = %s WHERE id = %s",
            (candidate.id, interview_ids[-1]),
        )
    observation_count, _, _ = repository.record_observation(
        bundle_id=candidate.id,
        interview_id=interview_ids[-1],
        quality_score=0.86,
        hard_error=False,
        metrics={"quality_score": 0.86},
    )
    if observation_count != 1:
        raise RuntimeError("candidate observation was not recorded")
    if not repository.rollback_bundle(candidate.id, reason="transaction verification"):
        raise RuntimeError("candidate rollback failed")
    restored = repository.get_active_bundle(family_key, user_id=user_id)
    if restored is None or restored.id != baseline.id:
        raise RuntimeError("rollback did not restore the baseline bundle")

    if not HistoryRepository(connection).delete_by_id_for_user(interview_ids[0], user_id):
        raise RuntimeError("verification interview history was not deleted")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM harness_evolution_samples WHERE run_id = %s",
            (claimed.id,),
        )
        sample_count = int(cursor.fetchone()["count"])
        cursor.execute(
            """
            SELECT source_interview_ids, diagnosis, proposal,
                   trigger_cursor_ended_at, trigger_cursor_interview_id
            FROM harness_evolution_runs WHERE id = %s
            """,
            (claimed.id,),
        )
        scrubbed_run = cursor.fetchone()
    source_ids = scrubbed_run["source_interview_ids"]
    if isinstance(source_ids, str):
        source_ids = json.loads(source_ids)
    proposal = scrubbed_run["proposal"]
    if isinstance(proposal, str):
        proposal = json.loads(proposal)
    history_scrubbed = (
        sample_count == 0
        and interview_ids[0] not in source_ids
        and scrubbed_run["diagnosis"] is None
        and proposal.get("scrubbed_after_source_deletion") is True
        and scrubbed_run["trigger_cursor_ended_at"] == claimed.trigger_cursor_ended_at
        and int(scrubbed_run["trigger_cursor_interview_id"])
        == claimed.trigger_cursor_interview_id
    )
    if not history_scrubbed:
        raise RuntimeError("history deletion left autonomous evolution source data behind")

    return {
        "trigger_cursor": True,
        "lease_heartbeat": True,
        "stale_token_rejected": stale_token_rejected,
        "candidate_creation_token_rejected": candidate_creation_token_rejected,
        "candidate_activated": True,
        "observation_recorded": True,
        "rollback_restored_baseline": True,
        "history_scrubbed": history_scrubbed,
    }


def main() -> None:
    connection = create_connection()
    try:
        result = verify(connection)
        print(json.dumps({"status": "ok", "checks": result}, sort_keys=True))
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
