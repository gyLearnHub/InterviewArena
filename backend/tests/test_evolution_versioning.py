from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from app.evolution.versioning import resolve_active_version_bundle_id
from app.repositories.evolution import DEFAULT_VERSION_BUNDLE_KEY, EvolutionRepository
from app.repositories.interviews import InterviewRecord
from app.services.interviews import InterviewService
from test_interview import FakeInterviewRepository, FakeLLMClient


def test_new_interview_binds_current_active_version_bundle() -> None:
    repository = _VersionedFakeInterviewRepository(active_bundle_id=11)
    repository.add_resume(1, 7)
    service = InterviewService(repository=repository, llm_client=FakeLLMClient())  # type: ignore[arg-type]

    interview = service.create_interview(
        user_id=7,
        resume_id=1,
        target_position="后端开发",
        selected_rounds=["resume"],
    )
    repository.active_bundle_id = 99

    stored = repository.get_interview_for_user(interview.id, 7)
    assert stored is not None
    assert interview.version_bundle_id == 11
    assert stored.version_bundle_id == 11


def test_repository_creates_bootstrap_default_version_bundle_once() -> None:
    connection = _BundleConnection()
    repository = EvolutionRepository(connection)

    created = repository.get_or_create_active_default_version_bundle()
    second = repository.get_or_create_active_default_version_bundle()

    assert created.id == second.id
    assert created.bundle_key == DEFAULT_VERSION_BUNDLE_KEY
    assert created.scope_type == "global"
    assert created.status == "active"
    assert connection.insert_count == 1


def test_version_resolution_prefers_developer_then_job_family_then_global() -> None:
    repository = _ScopedVersionRepository(
        {
            ("developer_canary", "7"): 701,
            ("job_family", "后端开发"): 501,
            ("global", None): 101,
        }
    )

    assert (
        resolve_active_version_bundle_id(
            repository,
            job_family="后端开发",
            developer_user_id=7,
        )
        == 701
    )
    repository.bundles.pop(("developer_canary", "7"))
    assert (
        resolve_active_version_bundle_id(
            repository,
            job_family="后端开发",
            developer_user_id=7,
        )
        == 501
    )
    repository.bundles.pop(("job_family", "后端开发"))
    assert (
        resolve_active_version_bundle_id(
            repository,
            job_family="后端开发",
            developer_user_id=7,
        )
        == 101
    )


class _VersionedFakeInterviewRepository(FakeInterviewRepository):
    def __init__(self, *, active_bundle_id: int) -> None:
        super().__init__()
        self.active_bundle_id = active_bundle_id

    def get_active_version_bundle(
        self,
        *,
        scope_type: str = "global",
        scope_key: str | None = None,
    ) -> Any:
        return SimpleNamespace(id=self.active_bundle_id)

    def get_or_create_active_default_version_bundle(self) -> Any:
        return SimpleNamespace(id=self.active_bundle_id)

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
        interview = InterviewRecord(
            id=self.next_interview_id,
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
        self.next_interview_id += 1
        self.interviews[interview.id] = interview
        self.qa[interview.id] = []
        self.rounds[interview.id] = []
        return interview


class _ScopedVersionRepository:
    def __init__(self, bundles: dict[tuple[str, str | None], int]) -> None:
        self.bundles = bundles

    def get_active_version_bundle(
        self,
        *,
        scope_type: str = "global",
        scope_key: str | None = None,
    ) -> Any:
        bundle_id = self.bundles.get((scope_type, scope_key))
        return SimpleNamespace(id=bundle_id) if bundle_id is not None else None

    def get_or_create_active_default_version_bundle(self) -> Any:
        return SimpleNamespace(id=999)


class _BundleConnection:
    def __init__(self) -> None:
        self.bundles: list[dict[str, Any]] = []
        self.insert_count = 0
        self.cursor_obj = _BundleCursor(self)

    def cursor(self) -> Any:
        return self.cursor_obj


class _BundleCursor:
    def __init__(self, connection: _BundleConnection) -> None:
        self.connection = connection
        self._row: dict[str, Any] | None = None
        self.lastrowid = 0

    def __enter__(self) -> _BundleCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if "WHERE bundle_key = %s" in sql:
            bundle_key = str(params[0])
            self._row = next(
                (item for item in self.connection.bundles if item["bundle_key"] == bundle_key),
                None,
            )
            return
        if "INSERT INTO evolution_version_bundles" in sql:
            self.connection.insert_count += 1
            self.lastrowid = len(self.connection.bundles) + 1
            self.connection.bundles.append(
                {
                    "id": self.lastrowid,
                    "bundle_key": params[0],
                    "parent_bundle_id": None,
                    "scope_type": "global",
                    "scope_key": None,
                    "status": "active",
                    "risk_level": "low",
                    "content_hash": "hash",
                    "diff": {"reason": "v3.2 bootstrap default bundle"},
                    "validation_summary": {"status": "bootstrap", "phase": "stage_1"},
                    "rollback_point": {"type": "bootstrap_default"},
                    "created_by_run_id": None,
                    "created_at": datetime.utcnow(),
                    "activated_at": datetime.utcnow(),
                }
            )
            self._row = None
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self) -> dict[str, Any] | None:
        return self._row
