from __future__ import annotations

import random
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any

from app.autonomous_evolution.anonymization import anonymize_payload
from app.autonomous_evolution.catalog import artifact_manifest
from app.autonomous_evolution.contracts import (
    EvolutionDiagnosis,
    EvolutionProposal,
    JudgeBatch,
    SyntheticSampleBatch,
)
from app.autonomous_evolution.metrics import (
    aggregate_metrics,
    historical_quality_score,
    max_regression,
)
from app.autonomous_evolution.repository import (
    ArtifactRecord,
    AutonomousEvolutionRepository,
    EvolutionRunRecord,
)
from app.autonomous_evolution.shadow import ShadowExecutor, validate_candidate_content
from app.prompts.loader import load_prompt


@dataclass
class EvaluatedSample:
    key: str
    sample_type: str
    source_interview_id: int | None
    payload: dict[str, Any]
    baseline_output: dict[str, Any]
    candidate_output: dict[str, Any]
    baseline_metrics: dict[str, float]
    candidate_metrics: dict[str, float]
    candidate_hard_gate_passed: bool
    candidate_hard_gate_errors: list[str]
    judge_results: list[dict[str, Any]] = field(default_factory=list)
    winner: str | None = None


class AutonomousEvolutionEngine:
    def __init__(
        self,
        repository: AutonomousEvolutionRepository,
        *,
        generator_client: Any,
        judge_client: Any,
        synthetic_sample_count: int = 10,
    ) -> None:
        self.repository = repository
        self.generator_client = generator_client
        self.judge_client = judge_client
        self.synthetic_sample_count = synthetic_sample_count
        self.shadow = ShadowExecutor(generator_client)

    def run(self, run: EvolutionRunRecord) -> dict[str, Any]:
        processing_token = run.processing_token
        if not processing_token:
            raise RuntimeError("evolution run must own a processing lease")
        self._heartbeat(run)
        run = self.repository.rebase_run_to_active(run)
        real_samples = [
            anonymize_payload(
                self.repository.load_interview_sample(interview_id, user_id=run.user_id)
            )
            for interview_id in run.source_interview_ids
        ]
        self._heartbeat(run)
        diagnosis = self._diagnose(run, real_samples)
        baseline_artifact = self.repository.get_artifact(
            run.baseline_bundle_id,
            diagnosis.selected_artifact_key,
        )
        if baseline_artifact is None:
            raise ValueError("analysis selected an artifact absent from the baseline bundle")
        proposal = self._propose(run, diagnosis, baseline_artifact, real_samples)
        self._validate_proposal(baseline_artifact, proposal)
        candidate_bundle = self.repository.create_candidate_bundle(
            baseline_bundle_id=run.baseline_bundle_id,
            artifact_key=proposal.artifact_key,
            artifact_type=proposal.artifact_type,
            content=proposal.content,
            change_summary=proposal.change_summary,
            run_id=run.id,
            processing_token=processing_token,
        )
        self.repository.update_run_candidate(
            run.id,
            candidate_bundle_id=candidate_bundle.id,
            artifact_key=proposal.artifact_key,
            artifact_type=proposal.artifact_type,
            diagnosis=diagnosis.model_dump(),
            proposal=proposal.model_dump(),
            processing_token=processing_token,
        )
        self._heartbeat(run)
        candidate_artifact = self.repository.get_artifact(
            candidate_bundle.id,
            proposal.artifact_key,
        )
        if candidate_artifact is None:
            raise RuntimeError("candidate artifact was not persisted")
        baseline_artifacts = self.repository.list_artifacts(run.baseline_bundle_id)
        candidate_artifacts = self.repository.list_artifacts(candidate_bundle.id)

        synthetic_samples = self._generate_synthetic_samples(run, diagnosis, real_samples)
        evaluated = self._execute_samples(
            baseline_artifacts,
            candidate_artifacts,
            proposal.artifact_key,
            real_samples,
            synthetic_samples,
            run.source_interview_ids,
        )
        self._judge_three_rounds(run, evaluated)
        self._heartbeat(run)
        validation, decision = self._decide(evaluated, real_samples)
        for sample in evaluated:
            self.repository.save_sample(
                run_id=run.id,
                sample_key=sample.key,
                sample_type=sample.sample_type,
                source_interview_id=sample.source_interview_id,
                input_payload=sample.payload,
                baseline_output=sample.baseline_output,
                candidate_output=sample.candidate_output,
                objective_metrics={
                    "baseline": sample.baseline_metrics,
                    "candidate": sample.candidate_metrics,
                    "candidate_hard_gate_errors": sample.candidate_hard_gate_errors,
                },
                judge_results=sample.judge_results,
                winner=sample.winner,
                hard_gate_status="passed" if sample.candidate_hard_gate_passed else "failed",
                processing_token=processing_token,
            )

        if decision["activate"]:
            self.repository.activate_candidate_and_complete_run(
                run_id=run.id,
                baseline_bundle_id=run.baseline_bundle_id,
                candidate_bundle_id=candidate_bundle.id,
                baseline_quality=fmean(historical_quality_score(item) for item in real_samples),
                validation_summary=validation,
                decision_summary=decision,
                processing_token=processing_token,
            )
        else:
            self.repository.reject_candidate(candidate_bundle.id)
            self.repository.complete_run(
                run.id,
                status="rejected",
                validation_summary=validation,
                decision_summary=decision,
                processing_token=processing_token,
            )
        return decision

    def _diagnose(
        self,
        run: EvolutionRunRecord,
        real_samples: list[dict[str, Any]],
    ) -> EvolutionDiagnosis:
        self._heartbeat(run)
        response = self.generator_client.generate_json(
            load_prompt("evolution_analyzer.md"),
            {
                "job_family_key": run.job_family_key,
                "artifact_manifest": artifact_manifest(),
                "real_samples": [_compact_sample(item) for item in real_samples],
                "quality_scores": [historical_quality_score(item) for item in real_samples],
            },
        )
        self._heartbeat(run)
        return EvolutionDiagnosis.model_validate(anonymize_payload(response))

    def _propose(
        self,
        run: EvolutionRunRecord,
        diagnosis: EvolutionDiagnosis,
        baseline_artifact: ArtifactRecord,
        real_samples: list[dict[str, Any]],
    ) -> EvolutionProposal:
        self._heartbeat(run)
        response = self.generator_client.generate_json(
            load_prompt("evolution_optimizer.md"),
            {
                "job_family_key": run.job_family_key,
                "diagnosis": diagnosis.model_dump(),
                "target_artifact": {
                    "artifact_key": baseline_artifact.artifact_key,
                    "artifact_type": baseline_artifact.artifact_type,
                    "current_content": baseline_artifact.content,
                },
                "real_samples": [_compact_sample(item) for item in real_samples],
            },
        )
        self._heartbeat(run)
        return EvolutionProposal.model_validate(anonymize_payload(response))

    def _generate_synthetic_samples(
        self,
        run: EvolutionRunRecord,
        diagnosis: EvolutionDiagnosis,
        real_samples: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        self._heartbeat(run)
        response = self.generator_client.generate_json(
            load_prompt("evolution_synthetic_samples.md"),
            {
                "job_family_key": run.job_family_key,
                "target_artifact_key": diagnosis.selected_artifact_key,
                "sample_count": self.synthetic_sample_count,
                "real_sample_patterns": [_compact_sample(item) for item in real_samples],
            },
        )
        self._heartbeat(run)
        batch = SyntheticSampleBatch.model_validate(anonymize_payload(response))
        if len(batch.samples) != self.synthetic_sample_count:
            raise ValueError("synthetic sample count does not match configured count")
        return [anonymize_payload(item) for item in batch.samples]

    def _execute_samples(
        self,
        baseline_artifacts: list[ArtifactRecord],
        candidate_artifacts: list[ArtifactRecord],
        target_artifact_key: str,
        real_samples: list[dict[str, Any]],
        synthetic_samples: list[dict[str, Any]],
        source_interview_ids: list[int],
    ) -> list[EvaluatedSample]:
        evaluated: list[EvaluatedSample] = []
        specs = [
            *[
                (f"real-{index + 1:02d}", "real", interview_id, payload)
                for index, (interview_id, payload) in enumerate(
                    zip(source_interview_ids, real_samples, strict=True)
                )
            ],
            *[
                (f"synthetic-{index + 1:02d}", "synthetic", None, payload)
                for index, payload in enumerate(synthetic_samples)
            ],
        ]
        for key, sample_type, interview_id, payload in specs:
            baseline_result = self.shadow.execute_bundle(
                baseline_artifacts,
                target_artifact_key,
                payload,
            )
            candidate_result = self.shadow.execute_bundle(
                candidate_artifacts,
                target_artifact_key,
                payload,
            )
            baseline_output = anonymize_payload(baseline_result.output)
            candidate_output = anonymize_payload(candidate_result.output)
            evaluated.append(
                EvaluatedSample(
                    key=key,
                    sample_type=sample_type,
                    source_interview_id=interview_id,
                    payload=payload,
                    baseline_output=baseline_output,
                    candidate_output=candidate_output,
                    baseline_metrics=baseline_result.metrics,
                    candidate_metrics=candidate_result.metrics,
                    candidate_hard_gate_passed=candidate_result.hard_gate_passed,
                    candidate_hard_gate_errors=candidate_result.hard_gate_errors,
                )
            )
        return evaluated

    def _judge_three_rounds(
        self,
        run: EvolutionRunRecord,
        samples: list[EvaluatedSample],
    ) -> None:
        for judge_round in range(1, 4):
            rng = random.Random(f"{run.id}:{judge_round}")
            swaps: dict[str, bool] = {}
            comparisons: list[dict[str, Any]] = []
            for sample in samples:
                swap = rng.choice([True, False])
                swaps[sample.key] = swap
                comparisons.append(
                    {
                        "sample_key": sample.key,
                        "input": _judge_input(sample.payload),
                        "A": sample.candidate_output if swap else sample.baseline_output,
                        "B": sample.baseline_output if swap else sample.candidate_output,
                    }
                )
            by_key = {}
            for offset in range(0, len(comparisons), 5):
                chunk = comparisons[offset : offset + 5]
                response = self.judge_client.generate_json(
                    load_prompt("evolution_judge.md"),
                    {"judge_round": judge_round, "comparisons": chunk},
                )
                self._heartbeat(run)
                batch = JudgeBatch.model_validate(anonymize_payload(response))
                expected_keys = {str(item["sample_key"]) for item in chunk}
                chunk_by_key = {item.sample_key: item for item in batch.comparisons}
                if len(batch.comparisons) != len(chunk) or set(chunk_by_key) != expected_keys:
                    raise ValueError("judge response did not cover its complete sample chunk")
                by_key.update(chunk_by_key)
            if set(by_key) != {
                sample.key for sample in samples
            }:
                raise ValueError("judge response did not cover the complete sample set")
            for sample in samples:
                result = by_key[sample.key]
                candidate_winner = _candidate_winner(result.winner, swaps[sample.key])
                sample.judge_results.append(
                    {
                        "judge_round": judge_round,
                        "winner": candidate_winner,
                        "reason": result.reason,
                        "candidate_quality": result.quality_a
                        if swaps[sample.key]
                        else result.quality_b,
                        "baseline_quality": result.quality_b
                        if swaps[sample.key]
                        else result.quality_a,
                    }
                )
        for sample in samples:
            votes = [item["winner"] for item in sample.judge_results]
            candidate_votes = votes.count("candidate")
            baseline_votes = votes.count("baseline")
            if candidate_votes > baseline_votes and candidate_votes >= 2:
                sample.winner = "candidate"
            elif baseline_votes > candidate_votes and baseline_votes >= 2:
                sample.winner = "baseline"
            else:
                sample.winner = "tie"

    def _decide(
        self,
        samples: list[EvaluatedSample],
        real_samples: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        real = [item for item in samples if item.sample_type == "real"]
        synthetic = [item for item in samples if item.sample_type == "synthetic"]
        real_win_rate = _win_rate(real)
        synthetic_win_rate = _win_rate(synthetic)
        all_hard_gates_passed = all(item.candidate_hard_gate_passed for item in samples)

        baseline_real = aggregate_metrics([item.baseline_metrics for item in real])
        candidate_real = aggregate_metrics([item.candidate_metrics for item in real])
        baseline_synthetic = aggregate_metrics([item.baseline_metrics for item in synthetic])
        candidate_synthetic = aggregate_metrics([item.candidate_metrics for item in synthetic])
        real_regression, real_regressed_keys = max_regression(baseline_real, candidate_real)
        synthetic_regression, synthetic_regressed_keys = max_regression(
            baseline_synthetic,
            candidate_synthetic,
        )
        round_consistency = []
        for index in range(3):
            candidate_votes = sum(
                item.judge_results[index]["winner"] == "candidate" for item in samples
            )
            baseline_votes = sum(
                item.judge_results[index]["winner"] == "baseline" for item in samples
            )
            round_consistency.append(candidate_votes > baseline_votes)

        activate = (
            all_hard_gates_passed
            and real_win_rate >= 0.60
            and synthetic_win_rate >= 0.65
            and real_regression <= 0.05
            and synthetic_regression <= 0.05
            and all(round_consistency)
        )
        validation = {
            "all_hard_gates_passed": all_hard_gates_passed,
            "real_win_rate": real_win_rate,
            "synthetic_win_rate": synthetic_win_rate,
            "real_metrics": {"baseline": baseline_real, "candidate": candidate_real},
            "synthetic_metrics": {
                "baseline": baseline_synthetic,
                "candidate": candidate_synthetic,
            },
            "real_max_regression": real_regression,
            "synthetic_max_regression": synthetic_regression,
            "regressed_metric_keys": sorted(
                set(real_regressed_keys + synthetic_regressed_keys)
            ),
            "judge_rounds_consistent": round_consistency,
            "historical_quality_baseline": fmean(
                historical_quality_score(item) for item in real_samples
            ),
        }
        decision = {
            "activate": activate,
            "reason": "candidate passed every autonomous gate"
            if activate
            else "candidate did not pass every autonomous gate",
            "required_real_win_rate": 0.60,
            "required_synthetic_win_rate": 0.65,
            "maximum_metric_regression": 0.05,
        }
        return validation, decision

    def _heartbeat(self, run: EvolutionRunRecord) -> None:
        heartbeat = getattr(self.repository, "heartbeat_run", None)
        if not callable(heartbeat):
            return
        token = run.processing_token
        if not token or not heartbeat(run.id, token):
            raise RuntimeError("evolution run processing lease was lost")
        connection = getattr(self.repository, "connection", None)
        commit = getattr(connection, "commit", None)
        if callable(commit):
            commit()

    @staticmethod
    def _validate_proposal(
        baseline_artifact: ArtifactRecord,
        proposal: EvolutionProposal,
    ) -> None:
        if proposal.artifact_key != baseline_artifact.artifact_key:
            raise ValueError("proposal changed the selected artifact key")
        if proposal.artifact_type != baseline_artifact.artifact_type:
            raise ValueError("proposal changed the selected artifact type")
        errors = validate_candidate_content(proposal.artifact_type, proposal.content)
        if errors:
            raise ValueError("; ".join(errors))


def _compact_sample(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": sample.get("id"),
        "target_position": sample.get("target_position"),
        "job_description": str(sample.get("job_description") or "")[:3000],
        "resume": _compact_value(sample.get("resume")),
        "qa_history": _compact_value(list(sample.get("qa_history") or [])[-16:]),
        "rounds": _compact_value(sample.get("rounds")),
        "report_score": sample.get("report_score"),
        "report_reliability_status": sample.get("report_reliability_status"),
        "harness_status": sample.get("harness_status"),
        "had_degradation": sample.get("had_degradation"),
        "harness_traces": _compact_value(list(sample.get("harness_traces") or [])[-30:]),
        "harness_rules": _compact_value(list(sample.get("harness_rules") or [])[-30:]),
        "user_feedback": _compact_value(sample.get("user_feedback")),
    }


def _judge_input(sample: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_sample(sample)
    compact.pop("harness_traces", None)
    return compact


def _candidate_winner(winner: str, swapped: bool) -> str:
    if winner == "tie":
        return "tie"
    if (winner == "A" and swapped) or (winner == "B" and not swapped):
        return "candidate"
    return "baseline"


def _win_rate(samples: list[EvaluatedSample]) -> float:
    if not samples:
        return 0.0
    return sum(item.winner == "candidate" for item in samples) / len(samples)


def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, dict):
        return {
            str(key)[:128]: _compact_value(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [_compact_value(item, depth=depth + 1) for item in list(value)[:20]]
    return value
