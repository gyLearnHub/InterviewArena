from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from app.api import autonomous_evolution as evolution_api
from app.autonomous_evolution import observation
from app.autonomous_evolution import runtime as evolution_runtime
from app.autonomous_evolution.anonymization import (
    anonymize_payload,
    contains_direct_identifier,
)
from app.autonomous_evolution.engine import AutonomousEvolutionEngine
from app.autonomous_evolution.job_family import JobFamilyClassifier
from app.autonomous_evolution.repository import (
    ArtifactRecord,
    AutonomousEvolutionRepository,
    BundleRecord,
    EvolutionRunRecord,
)
from app.core.config import Settings, _validate_settings
from app.repositories.users import UserRecord
from app.services.llm import DeepSeekLLMClient


def _bundle(bundle_id: int, *, parent_id: int | None = None) -> BundleRecord:
    return BundleRecord(
        id=bundle_id,
        bundle_key=f"bundle-{bundle_id}",
        user_id=1,
        job_family_key="backend-engineer",
        parent_bundle_id=parent_id,
        generation=1 if parent_id is None else 2,
        status="active" if parent_id is None else "candidate",
        is_active=parent_id is None,
        baseline_quality=None,
        observation_count=0,
        consecutive_failures=0,
        activated_at=None,
    )


def _run() -> EvolutionRunRecord:
    return EvolutionRunRecord(
        id=7,
        user_id=1,
        job_family_key="backend-engineer",
        trigger_sequence=1,
        trigger_interview_count=10,
        source_interview_ids=list(range(1, 11)),
        baseline_bundle_id=1,
        candidate_bundle_id=None,
        candidate_artifact_key=None,
        candidate_artifact_type=None,
        diagnosis=None,
        proposal=None,
        validation_summary=None,
        decision_summary=None,
        status="processing",
        attempt_count=1,
        max_retries=3,
        processing_token="lease-token",
        heartbeat_at=None,
        trigger_cursor_ended_at=None,
        trigger_cursor_interview_id=None,
    )


def _sample(interview_id: int) -> dict[str, Any]:
    return {
        "id": interview_id,
        "target_position": "后端工程师",
        "job_description": "负责 Python 服务开发",
        "resume": {"skills": ["Python", "MySQL"]},
        "qa_history": [
            {
                "id": interview_id,
                "round_id": interview_id,
                "round_type": "technical",
                "question": "请介绍一个项目",
                "answer": "我负责接口设计",
                "question_kind": "main",
            }
        ],
        "rounds": [],
        "report_score": 80,
        "harness_status": "completed",
        "harness_rules": [{"status": "passed", "severity": "hard"}],
        "harness_traces": [],
        "user_feedback": [],
    }


class FakeGenerator:
    model_name = "deepseek-chat"

    def __init__(self, *, leak_identifier: bool = False) -> None:
        self.leak_identifier = leak_identifier
        self.synthetic_requested = 0
        self.question_prompts: list[str] = []

    def generate_json(
        self,
        _system_prompt: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if "artifact_manifest" in payload:
            return {
                "summary": "技术追问缺少证据约束",
                "evidence": ["回答缺少可验证细节"],
                "selected_artifact_key": "interviewer.technical",
                "expected_improvements": ["提高追问针对性"],
                "risks": ["问题可能过长"],
            }
        if "target_artifact" in payload:
            return {
                "artifact_key": "interviewer.technical",
                "artifact_type": "prompt",
                "change_summary": "要求基于回答证据生成技术追问",
                "rationale": "真实样本显示证据追问不足",
                "content": {
                    "text": "candidate prompt: 只返回 JSON，并生成基于证据的技术追问。"
                },
            }
        if "sample_count" in payload:
            self.synthetic_requested = int(payload["sample_count"])
            return {
                "samples": [
                    _sample(1000 + index)
                    for index in range(self.synthetic_requested)
                ]
            }
        if "question_evaluations" in payload:
            return {
                "total_score": 86,
                "result": "passed",
                "dimension_scores": [
                    {"dimension": "回答质量", "score": 86, "reason": "证据充分"}
                ],
                "strengths": ["证据充分"],
                "weaknesses": [],
                "suggestions": ["保持结构化表达"],
                "evidence": ["接口设计"],
                "is_reference_only": False,
            }
        if "round_evaluations" in payload:
            return {
                "total_score": 86,
                "round_scores": [
                    {"round_type": "technical", "score": 86, "result": "passed"}
                ],
                "ability_analysis": ["技术基础扎实"],
                "job_match": "匹配",
                "core_strengths": ["表达清晰"],
                "main_risks": [],
                "improvement_plan": ["继续补充量化证据"],
                "final_conclusion": "建议通过",
                "confidence": "high",
            }
        if "question" in payload and "answer" in payload:
            return {
                "total_score": 86,
                "dimension_scores": [
                    {"dimension": "回答质量", "score": 86, "reason": "证据充分"}
                ],
                "strengths": ["证据充分"],
                "issues": [],
                "evidence": ["接口设计"],
                "should_follow_up": False,
            }
        raise AssertionError(f"unexpected generator payload: {sorted(payload)}")

    def generate_question(
        self,
        *,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None,
        system_prompt: str,
    ) -> dict[str, Any]:
        del resume, target_position, qa_history, previous_answer
        self.question_prompts.append(system_prompt)
        candidate = system_prompt.startswith("candidate prompt")
        output: dict[str, Any] = {
            "question_type": "technical",
            "question": "候选版本的证据追问" if candidate else "基线版本的普通追问",
        }
        if candidate and self.leak_identifier:
            output["name"] = "张三"
        return output


class FakeJudge:
    model_name = "deepseek-flash"

    def __init__(self) -> None:
        self.calls = 0

    def generate_json(
        self,
        _system_prompt: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        comparisons = []
        for item in payload["comparisons"]:
            candidate_is_a = "候选版本" in str(item["A"].get("question") or "")
            comparisons.append(
                {
                    "sample_key": item["sample_key"],
                    "winner": "A" if candidate_is_a else "B",
                    "reason": "候选版本更贴合回答证据",
                    "quality_a": 90 if candidate_is_a else 60,
                    "quality_b": 60 if candidate_is_a else 90,
                }
            )
        return {"comparisons": comparisons}


class FakeEvolutionRepository:
    def __init__(self) -> None:
        self.baseline = ArtifactRecord(
            id=1,
            bundle_id=1,
            artifact_key="interviewer.technical",
            artifact_type="prompt",
            content={"text": "baseline prompt: 只返回 JSON，并生成技术面试追问。"},
            content_hash="baseline",
            change_summary=None,
        )
        self.candidate: ArtifactRecord | None = None
        self.saved_samples: list[dict[str, Any]] = []
        self.activated: dict[str, Any] | None = None
        self.rejected_bundle_id: int | None = None
        self.completed: dict[str, Any] | None = None
        self.rebased = False

    def rebase_run_to_active(self, run: EvolutionRunRecord) -> EvolutionRunRecord:
        self.rebased = True
        return run

    def load_interview_sample(
        self,
        interview_id: int,
        *,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        assert user_id == 1
        return _sample(interview_id)

    def get_artifact(self, bundle_id: int, artifact_key: str) -> ArtifactRecord | None:
        if artifact_key != "interviewer.technical":
            return None
        return self.baseline if bundle_id == 1 else self.candidate

    def list_artifacts(self, bundle_id: int) -> list[ArtifactRecord]:
        selected = self.baseline if bundle_id == 1 else self.candidate
        assert selected is not None
        common = [
            ArtifactRecord(
                id=10 + index,
                bundle_id=bundle_id,
                artifact_key=key,
                artifact_type="prompt",
                content={"text": "只返回 JSON，并完成匿名回放评分。"},
                content_hash=f"hash-{index}",
                change_summary=None,
            )
            for index, key in enumerate(
                ("evaluation.question", "evaluation.round.technical", "evaluation.final")
            )
        ]
        return [selected, *common]

    def create_candidate_bundle(self, **payload: Any) -> BundleRecord:
        self.candidate = replace(
            self.baseline,
            id=2,
            bundle_id=2,
            content=payload["content"],
            change_summary=payload["change_summary"],
        )
        return _bundle(2, parent_id=1)

    def update_run_candidate(self, _run_id: int, **_payload: Any) -> None:
        return None

    def save_sample(self, **payload: Any) -> None:
        self.saved_samples.append(payload)

    def activate_candidate(self, **payload: Any) -> None:
        self.activated = payload

    def activate_candidate_and_complete_run(self, **payload: Any) -> None:
        self.activated = payload
        self.completed = {
            "run_id": payload["run_id"],
            "status": "observing",
            "validation_summary": payload["validation_summary"],
            "decision_summary": payload["decision_summary"],
            "processing_token": payload["processing_token"],
        }

    def reject_candidate(self, bundle_id: int) -> None:
        self.rejected_bundle_id = bundle_id

    def complete_run(self, run_id: int, **payload: Any) -> None:
        self.completed = {"run_id": run_id, **payload}


def test_model_driven_cycle_generates_tests_judges_and_activates_one_artifact() -> None:
    repository = FakeEvolutionRepository()
    generator = FakeGenerator()
    judge = FakeJudge()

    decision = AutonomousEvolutionEngine(
        repository,  # type: ignore[arg-type]
        generator_client=generator,
        judge_client=judge,
        synthetic_sample_count=10,
    ).run(_run())

    assert decision["activate"] is True
    assert repository.rebased is True
    assert generator.synthetic_requested == 10
    assert judge.calls == 12
    assert len(repository.saved_samples) == 20
    assert {item["sample_type"] for item in repository.saved_samples} == {
        "real",
        "synthetic",
    }
    assert repository.activated is not None
    assert repository.rejected_bundle_id is None
    assert repository.completed is not None
    assert repository.completed["status"] == "observing"
    assert repository.candidate is not None
    assert repository.candidate.artifact_key == "interviewer.technical"
    assert all(
        len(item["candidate_output"]["affected_chain"]) == 4
        for item in repository.saved_samples
    )


def test_privacy_hard_gate_rejects_an_otherwise_winning_candidate() -> None:
    repository = FakeEvolutionRepository()
    decision = AutonomousEvolutionEngine(
        repository,  # type: ignore[arg-type]
        generator_client=FakeGenerator(leak_identifier=True),
        judge_client=FakeJudge(),
        synthetic_sample_count=10,
    ).run(_run())

    assert decision["activate"] is False
    assert repository.activated is None
    assert repository.rejected_bundle_id == 2
    assert all(
        item["hard_gate_status"] == "failed"
        for item in repository.saved_samples
    )


def test_anonymization_scrubs_known_values_from_free_text() -> None:
    payload = {
        "name": "张三",
        "phone": "13812345678",
        "email": "zhangsan@example.com",
        "company": "星河科技",
        "school": "远山大学",
        "answer": "我叫张三，毕业于远山大学，曾在星河科技工作。",
    }

    anonymized = anonymize_payload(payload)

    assert anonymized["name"] == "[REDACTED]"
    assert anonymized["company"] == "[COMPANY]"
    assert anonymized["school"] == "[SCHOOL]"
    assert anonymized["answer"] == (
        "我叫[REDACTED]，毕业于[SCHOOL]，曾在[COMPANY]工作。"
    )
    assert contains_direct_identifier(anonymized) is False


def test_classifier_falls_back_to_global_without_model_created_family() -> None:
    class Repository:
        def list_job_family_keys(self) -> list[str]:
            return ["backend-engineer"]

    class FailingModel:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("offline")

    decision = JobFamilyClassifier(
        Repository(),  # type: ignore[arg-type]
        FailingModel(),
    ).classify("量子算法顾问", None)

    assert decision.key == "global-default"
    assert decision.matched_existing is False


@pytest.mark.parametrize(
    ("summary", "expected_reason"),
    [
        ((1, 0.75, True), "runtime hard gate failed"),
        ((5, 0.70, False), "observation quality dropped by more than 10 percent"),
    ],
)
def test_observation_rolls_back_on_hard_error_or_quality_drop(
    monkeypatch: pytest.MonkeyPatch,
    summary: tuple[int, float, bool],
    expected_reason: str,
) -> None:
    class Repository:
        def __init__(self) -> None:
            self.rollback_reason: str | None = None

        def get_interview_bundle(self, _interview_id: int) -> BundleRecord:
            return replace(
                _bundle(2, parent_id=1),
                status="observing",
                is_active=True,
                baseline_quality=0.80,
            )

        def load_interview_sample(self, _interview_id: int) -> dict[str, Any]:
            return _sample(1)

        def record_observation(self, **_payload: Any) -> tuple[int, float, bool]:
            return summary

        def record_event(self, **_payload: Any) -> None:
            return None

        def rollback_bundle(self, _bundle_id: int, *, reason: str) -> bool:
            self.rollback_reason = reason
            return True

        def finish_observation(self, _bundle_id: int) -> None:
            raise AssertionError("observation should not finish after a rollback gate")

    repository = Repository()
    monkeypatch.setattr(
        observation,
        "AutonomousEvolutionRepository",
        lambda _connection: repository,
    )
    monkeypatch.setattr(
        observation,
        "get_settings",
        lambda: SimpleNamespace(evolution_observation_interviews=5),
    )

    observation.observe_completed_interview(object(), 1)

    assert repository.rollback_reason == expected_reason


def test_deepseek_flash_judge_shares_configured_key_and_base_url() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "{}"}}]}

    class HTTPClient:
        def __init__(self) -> None:
            self.request: dict[str, Any] | None = None

        def post(self, url: str, **kwargs: Any) -> Response:
            self.request = {"url": url, **kwargs}
            return Response()

    http_client = HTTPClient()
    client = DeepSeekLLMClient(
        settings=Settings(
            deepseek_api_key="shared-key",
            deepseek_base_url="https://deepseek.local/v1",
            deepseek_model="main-model",
            deepseek_retry_count=0,
        ),
        http_client=http_client,  # type: ignore[arg-type]
        model_name="deepseek-flash",
    )

    assert client.generate_json("只返回 JSON", {"input": "test"}) == {}
    assert http_client.request is not None
    assert http_client.request["url"] == "https://deepseek.local/v1/chat/completions"
    assert http_client.request["json"]["model"] == "deepseek-flash"
    assert http_client.request["headers"]["Authorization"] == "Bearer shared-key"


def test_runtime_output_hard_gate_catches_privacy_and_score_boundaries() -> None:
    with pytest.raises(observation.RuntimeHardGateError):
        observation.validate_runtime_output({"name": "张三", "total_score": 90})
    with pytest.raises(observation.RuntimeHardGateError):
        observation.validate_runtime_output({"total_score": 101})

    observation.validate_runtime_output({"score": None, "total_score": 100})


def test_cycle_failure_retries_and_resets_the_retry_cycle_without_dropping_the_batch() -> None:
    class Cursor:
        rowcount = 1
        lastrowid = 1

        def __init__(self) -> None:
            self.executed: list[tuple[str, Any]] = []

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, sql: str, params: Any = None) -> None:
            self.executed.append((" ".join(sql.split()), params))

        def fetchone(self) -> dict[str, Any] | None:
            return {"is_active": 0, "status": "candidate"}

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_instance

    connection = Connection()
    repository = AutonomousEvolutionRepository(connection)

    repository.fail_or_retry_run(replace(_run(), attempt_count=3), "temporary")
    update_params = connection.cursor_instance.executed[0][1]
    assert update_params[0] is not None
    assert update_params[2] == 3

    connection.cursor_instance.executed.clear()
    repository.fail_or_retry_run(replace(_run(), attempt_count=4), "terminal")
    update_params = connection.cursor_instance.executed[0][1]
    assert update_params[0] is not None
    assert update_params[2] == 0

    connection.cursor_instance.executed.clear()
    repository.fail_or_retry_run(
        replace(_run(), candidate_bundle_id=44),
        "candidate failed",
    )
    _, run_update, candidate_update = connection.cursor_instance.executed[:3]
    assert "UPDATE harness_evolution_runs" in run_update[0]
    assert "UPDATE harness_artifact_bundles" in candidate_update[0]
    assert candidate_update[1] == (44,)


def test_cycle_failure_after_activation_finalizes_the_observing_run() -> None:
    class Cursor:
        rowcount = 1

        def __init__(self) -> None:
            self.executed: list[tuple[str, Any]] = []

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, sql: str, params: Any = None) -> None:
            self.executed.append((" ".join(sql.split()), params))

        def fetchone(self) -> dict[str, Any] | None:
            return {"is_active": 1, "status": "observing"}

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_instance

    connection = Connection()
    AutonomousEvolutionRepository(connection).fail_or_retry_run(
        replace(_run(), candidate_bundle_id=44),
        "complete failed",
    )

    statements = [item[0] for item in connection.cursor_instance.executed]
    assert any("SET status = 'observing'" in sql for sql in statements)
    assert not any("candidate_bundle_id = NULL" in sql for sql in statements)
    assert any(
        "evolution_run_finalized_after_activation_failure" in str(params)
        for _, params in connection.cursor_instance.executed
    )


def test_observation_rejects_an_interview_bound_to_another_bundle() -> None:
    class Cursor:
        rowcount = 1

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, _sql: str, _params: Any = None) -> None:
            return None

        def fetchone(self) -> dict[str, Any]:
            return {"harness_bundle_id": 8, "is_active": 1, "status": "observing"}

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    with pytest.raises(RuntimeError, match="not bound"):
        AutonomousEvolutionRepository(Connection()).record_observation(
            bundle_id=9,
            interview_id=12,
            quality_score=0.8,
            hard_error=False,
            metrics={},
        )


def test_anonymization_blocks_extended_direct_identifiers_in_free_text() -> None:
    payload = {
        "id": 99,
        "user_id": 7,
        "answer": (
            "我叫李雷，身份证110101199001011234，微信号 lilei_88，"
            "QQ号 12345678，住北京市海淀区中关村路1号，"
            "主页 https://github.com/lilei。"
        )
    }

    anonymized = anonymize_payload(payload)

    assert "李雷" not in anonymized["answer"]
    assert "110101199001011234" not in anonymized["answer"]
    assert "lilei_88" not in anonymized["answer"]
    assert "12345678" not in anonymized["answer"]
    assert "北京市海淀区" not in anonymized["answer"]
    assert "github.com/lilei" not in anonymized["answer"]
    assert anonymized["id"] == 0
    assert anonymized["user_id"] == 0
    assert contains_direct_identifier(anonymized) is False


def test_runtime_failures_rollback_immediately_for_hard_gate_or_after_two_llm_failures() -> None:
    class Cursor:
        rowcount = 1

        def __init__(self, connection: Connection) -> None:
            self.connection = connection

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, sql: str, _params: Any = None) -> None:
            if "consecutive_failures = consecutive_failures + 1" in sql:
                self.connection.failures += 1
            elif "consecutive_failures = 0" in sql:
                self.connection.failures = 0

        def fetchone(self) -> dict[str, int]:
            return {"consecutive_failures": self.connection.failures}

    class Connection:
        def __init__(self) -> None:
            self.failures = 0

        def cursor(self) -> Cursor:
            return Cursor(self)

    class Repository(AutonomousEvolutionRepository):
        def __init__(self) -> None:
            super().__init__(Connection())
            self.rollback_reasons: list[str] = []

        def get_interview_bundle(self, _interview_id: int) -> BundleRecord:
            return replace(
                _bundle(2, parent_id=1),
                status="observing",
                is_active=True,
            )

        def rollback_bundle(self, _bundle_id: int, *, reason: str) -> bool:
            self.rollback_reasons.append(reason)
            return True

    hard_repository = Repository()
    assert hard_repository.record_execution_outcome(
        1,
        succeeded=False,
        hard_error=True,
    )
    assert len(hard_repository.rollback_reasons) == 1

    llm_repository = Repository()
    assert not llm_repository.record_execution_outcome(1, succeeded=False)
    assert llm_repository.record_execution_outcome(1, succeeded=False)
    assert llm_repository.rollback_reasons == [
        "two consecutive runtime execution failures"
    ]


@pytest.mark.parametrize(
    "settings",
    [
        Settings(app_env="test", evolution_trigger_interviews=0),
        Settings(app_env="test", evolution_synthetic_samples=0),
        Settings(
            app_env="test",
            evolution_task_heartbeat_seconds=10,
            evolution_task_processing_timeout_seconds=10,
        ),
        Settings(app_env="test", evolution_observation_interviews=0),
    ],
)
def test_invalid_autonomous_evolution_settings_are_rejected(settings: Settings) -> None:
    with pytest.raises(RuntimeError):
        _validate_settings(settings)


def test_autonomous_evolution_is_opt_in() -> None:
    assert Settings().evolution_enabled is False


def test_status_endpoint_is_read_only_and_reports_trigger_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        def get_status_for_user(self, user_id: int) -> dict[str, Any]:
            assert user_id == 1
            return {
                "families": [
                    {
                        "job_family_key": "backend-engineer",
                        "active_bundle_id": 2,
                        "active_bundle_key": "bundle-2",
                        "generation": 2,
                        "bundle_status": "observing",
                        "observation_count": 2,
                        "consecutive_failures": 0,
                        "eligible_interview_count": 4,
                        "activated_at": None,
                    }
                ],
                "runs": [],
            }

    monkeypatch.setattr(
        evolution_api,
        "get_settings",
        lambda: Settings(app_env="test", evolution_enabled=True),
    )
    response = evolution_api.get_autonomous_evolution_status(
        UserRecord(id=1, username="local", password_hash="hash"),
        Repository(),  # type: ignore[arg-type]
    )

    assert response.enabled is True
    assert response.families[0].eligible_interview_count == 4
    assert response.runs == []


def test_complete_run_requires_the_current_processing_token() -> None:
    class Cursor:
        rowcount = 0

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, _sql: str, _params: Any = None) -> None:
            return None

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    with pytest.raises(RuntimeError, match="lease was lost"):
        AutonomousEvolutionRepository(Connection()).complete_run(
            7,
            status="rejected",
            validation_summary={},
            decision_summary={},
            processing_token="stale-token",
        )


def test_same_second_heartbeat_keeps_an_owned_lease_alive() -> None:
    class Cursor:
        rowcount = 0

        def __init__(self) -> None:
            self.last_sql = ""

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, sql: str, _params: Any = None) -> None:
            self.last_sql = " ".join(sql.split())

        def fetchone(self) -> dict[str, int] | None:
            return {"id": 7} if self.last_sql.startswith("SELECT id") else None

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    assert AutonomousEvolutionRepository(Connection()).heartbeat_run(7, "lease-token")


def test_claim_rejects_and_clears_an_expired_run_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Cursor:
        rowcount = 1

        def __init__(self) -> None:
            self.executed: list[tuple[str, Any]] = []
            self.last_sql = ""

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, sql: str, params: Any = None) -> None:
            self.last_sql = " ".join(sql.split())
            self.executed.append((self.last_sql, params))

        def fetchall(self) -> list[dict[str, Any]]:
            return [
                {
                    "id": 6,
                    "candidate_bundle_id": 55,
                    "candidate_is_active": 0,
                    "candidate_status": "candidate",
                }
            ]

        def fetchone(self) -> dict[str, Any] | None:
            if "LIMIT 1 FOR UPDATE" in self.last_sql:
                return {"id": 6}
            return None

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_instance

    connection = Connection()
    repository = AutonomousEvolutionRepository(connection)
    monkeypatch.setattr(
        repository,
        "get_run",
        lambda _run_id: replace(_run(), id=6, processing_token="new-token"),
    )

    claimed = repository.claim_due_run(processing_timeout_seconds=60)

    assert claimed is not None
    statements = [item[0] for item in connection.cursor_instance.executed]
    assert "SELECT r.id, r.candidate_bundle_id" in statements[0]
    assert "UPDATE harness_artifact_bundles" in statements[1]
    assert connection.cursor_instance.executed[1][1] == (55,)
    assert "candidate_bundle_id = NULL" in statements[2]


def test_trigger_uses_a_monotonic_cursor_instead_of_offset_batches() -> None:
    class Cursor:
        rowcount = 1
        lastrowid = 33

        def __init__(self) -> None:
            self.sql: list[str] = []
            self.last_sql = ""

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def execute(self, sql: str, _params: Any = None) -> None:
            self.last_sql = " ".join(sql.split())
            self.sql.append(self.last_sql)

        def fetchone(self) -> dict[str, Any] | None:
            if (
                "FROM harness_artifact_bundles" in self.last_sql
                and "is_active = 1" in self.last_sql
            ):
                return {
                    "id": 1,
                    "bundle_key": "bundle-1",
                    "user_id": 1,
                    "job_family_key": "backend-engineer",
                    "parent_bundle_id": None,
                    "generation": 1,
                    "status": "active",
                    "is_active": 1,
                    "baseline_quality": None,
                    "observation_count": 0,
                    "consecutive_failures": 0,
                    "activated_at": None,
                }
            if "COUNT(*) AS count" in self.last_sql:
                return {"count": 20}
            if "ORDER BY trigger_sequence DESC" in self.last_sql:
                return {
                    "trigger_sequence": 1,
                    "trigger_cursor_ended_at": "2026-07-01 12:00:00",
                    "trigger_cursor_interview_id": 10,
                }
            return None

        def fetchall(self) -> list[dict[str, Any]]:
            if "AS cursor_at" in self.last_sql:
                return [
                    {"id": interview_id, "cursor_at": "2026-07-02 12:00:00"}
                    for interview_id in range(11, 21)
                ]
            return []

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()

        def cursor(self) -> Cursor:
            return self.cursor_instance

    connection = Connection()
    run_id = AutonomousEvolutionRepository(connection).enqueue_if_due(
        user_id=1,
        job_family_key="backend-engineer",
        trigger_every=10,
        max_retries=3,
    )

    assert run_id == 33
    source_query = next(sql for sql in connection.cursor_instance.sql if "AS cursor_at" in sql)
    assert "OFFSET" not in source_query
    assert "i.user_id = %s" in source_query
    assert "i.id > %s" in source_query
    insert_query = next(
        sql
        for sql in connection.cursor_instance.sql
        if "INSERT IGNORE INTO harness_evolution_runs" in sql
    )
    assert "trigger_cursor_ended_at" in insert_query
    assert "trigger_cursor_interview_id" in insert_query
    assert "user_id" in insert_query


def test_binding_applies_evolved_limits_to_pending_rounds(monkeypatch) -> None:
    class Repository:
        def __init__(self) -> None:
            self.assigned: dict[str, Any] | None = None
            self.limits: dict[str, tuple[int, int]] | None = None

        def list_job_family_keys(self, *, user_id: int) -> list[str]:
            assert user_id == 1
            return ["backend-engineer"]

        def ensure_bootstrap_bundle(self, *_args: Any, **_kwargs: Any) -> BundleRecord:
            return _bundle(9)

        def assign_interview_context(self, interview_id: int, **payload: Any) -> None:
            self.assigned = {"interview_id": interview_id, **payload}

        def apply_pending_round_limits(
            self,
            _interview_id: int,
            *,
            user_id: int,
            limits: dict[str, tuple[int, int]],
        ) -> int:
            assert user_id == 1
            self.limits = limits
            return len(limits)

        def get_artifact(self, bundle_id: int, artifact_key: str) -> ArtifactRecord | None:
            assert bundle_id == 9
            if artifact_key == "flow.rounds":
                return ArtifactRecord(
                    id=1,
                    bundle_id=9,
                    artifact_key=artifact_key,
                    artifact_type="flow",
                    content={
                        "config": {
                            "technical": {
                                "max_main_questions": 8,
                                "max_total_questions": 12,
                            }
                        }
                    },
                    content_hash="hash",
                    change_summary=None,
                )
            return None

        def record_event(self, **_payload: Any) -> int:
            return 1

    class LLM:
        def generate_json(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {
                "key": "backend-engineer",
                "label": "后端工程师",
                "matched_existing": True,
                "confidence": 0.95,
            }

    repository = Repository()
    monkeypatch.setattr(
        evolution_runtime,
        "AutonomousEvolutionRepository",
        lambda _connection: repository,
    )

    result = evolution_runtime.prepare_interview_evolution_context(
        connection=object(),
        llm_client=LLM(),
        user_id=1,
        interview_id=88,
        target_position="后端工程师",
        job_description="负责 Python 服务",
    )

    assert result == ("backend-engineer", 9)
    assert repository.assigned == {
        "interview_id": 88,
        "user_id": 1,
        "job_family_key": "backend-engineer",
        "bundle_id": 9,
    }
    assert repository.limits is not None
    assert repository.limits["technical"] == (8, 12)
