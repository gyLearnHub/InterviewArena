import inspect
import subprocess
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from app.api.resumes import (
    get_resume_parser,
    get_resume_repository,
    resume_content_hash,
)
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.deps import get_current_user
from app.repositories.resumes import (
    ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
    ResumeDetailRecord,
    ResumeParseTaskRecord,
    ResumeRecord,
    ResumeRepository,
    ResumeSummaryRecord,
)
from app.repositories.users import UserRecord
from app.services import resume_parser as resume_parser_module
from app.services.resume_parser import (
    MAX_DOCX_MEMBER_BYTES,
    ResumeParserService,
    convert_doc_to_docx,
    extract_docx_text,
    store_resume_upload,
)
from app.services.resumes import ACTIVE_INTERVIEW_DELETE_MESSAGE, ResumeService
from app.services.usage_limits import usage_limiter
from docx import Document
from fastapi.testclient import TestClient
from main import create_app


def datetime_for_tests() -> datetime:
    return datetime(2026, 6, 18, 12, 0)


def structured_resume() -> dict[str, Any]:
    return {
        "basic_info": {"name": "张三"},
        "education": [],
        "work_experience": [],
        "project_experience": [],
        "skills": ["Python"],
        "certificates_awards": [],
    }


def make_docx_bytes(text: str = "张三\nPython 开发") -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def test_resume_content_hash_changes_when_parser_version_changes() -> None:
    content = b"same resume bytes"

    assert resume_content_hash(content) == resume_content_hash(content)
    assert resume_content_hash(content) != sha256(content).hexdigest()


def make_textbox_docx_bytes(text: str) -> bytes:
    from io import BytesIO

    source = BytesIO(make_docx_bytes(""))
    target = BytesIO()
    textbox_xml = (
        "<w:p><w:r><w:pict><v:shape><v:textbox><w:txbxContent>"
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
    )

    with ZipFile(source) as input_docx, ZipFile(target, "w", ZIP_DEFLATED) as output_docx:
        for item in input_docx.infolist():
            data = input_docx.read(item.filename)
            if item.filename == "word/document.xml":
                xml = data.decode("utf-8")
                data = xml.replace("</w:body>", f"{textbox_xml}</w:body>").encode("utf-8")
            output_docx.writestr(item, data)

    return target.getvalue()


class FakeLLMClient:
    def __init__(self, result: dict[str, Any] | AppError | None = None) -> None:
        self.result = result or structured_resume()
        self.received_text = ""
        self.parse_calls = 0

    def parse_resume(self, resume_text: str) -> dict[str, Any]:
        self.parse_calls += 1
        self.received_text = resume_text
        if isinstance(self.result, AppError):
            raise self.result
        return self.result

    def generate_question(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_feedback(
        self,
        resume: dict[str, Any],
        target_position: str,
        qa_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError


class FakeResumeRepository:
    def __init__(self) -> None:
        self.created: list[ResumeRecord] = []
        self.summaries: list[ResumeSummaryRecord] = []
        self.next_id = 1
        self.next_task_id = 1
        self.create_error: Exception | None = None
        self.list_by_user_calls = 0
        self.parse_tasks: list[ResumeParseTaskRecord] = []
        self.unfinished_interview_resume_ids: set[tuple[int, int]] = set()
        self.parser: ResumeParserService | None = None
        self.commit_error: Exception | None = None
        self.cleanup_paths: list[str] = []

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error

    def create(
        self,
        user_id: int,
        original_file_path: str,
        structured_data: dict[str, Any],
        content_hash: str | None = None,
    ) -> ResumeRecord:
        if self.create_error is not None:
            raise self.create_error
        record = ResumeRecord(
            id=self.next_id,
            user_id=user_id,
            original_file_path=original_file_path,
            structured_data=structured_data,
            content_hash=content_hash,
        )
        self.next_id += 1
        self.created.append(record)
        return record

    def get_by_content_hash(self, user_id: int, content_hash: str) -> ResumeRecord | None:
        return next(
            (
                record
                for record in self.created
                if record.user_id == user_id and record.content_hash == content_hash
            ),
            None,
        )

    def list_by_user(self, user_id: int) -> list[ResumeRecord]:
        self.list_by_user_calls += 1
        return [record for record in self.created if record.user_id == user_id]

    def list_summaries_by_user(self, user_id: int) -> list[ResumeSummaryRecord]:
        return list(self.summaries)

    def get_detail_for_user(self, resume_id: int, user_id: int) -> ResumeDetailRecord | None:
        record = next(
            (
                item
                for item in self.created
                if item.id == resume_id and item.user_id == user_id and item.deleted_at is None
            ),
            None,
        )
        if record is None:
            return None
        return ResumeDetailRecord(
            id=record.id,
            name=record.display_name or Path(record.original_file_path).name,
            uploaded_at=record.created_at or datetime_for_tests(),
            last_used_at=None,
            parse_status="parsed",
            structured_data=record.structured_data,
            is_default=record.is_default,
        )

    def rename_for_user(self, resume_id: int, user_id: int, name: str) -> ResumeDetailRecord | None:
        updated: list[ResumeRecord] = []
        renamed = False
        for record in self.created:
            if record.id == resume_id and record.user_id == user_id and record.deleted_at is None:
                updated.append(ResumeRecord(**{**record.__dict__, "display_name": name}))
                renamed = True
            else:
                updated.append(record)
        self.created = updated
        return self.get_detail_for_user(resume_id, user_id) if renamed else None

    def set_default_for_user(
        self,
        resume_id: int,
        user_id: int,
    ) -> ResumeDetailRecord | None:
        if self.get_detail_for_user(resume_id, user_id) is None:
            return None
        self.created = [
            ResumeRecord(
                **{
                    **record.__dict__,
                    "is_default": (
                        record.id == resume_id
                        if record.user_id == user_id and record.deleted_at is None
                        else record.is_default
                    ),
                }
            )
            for record in self.created
        ]
        return self.get_detail_for_user(resume_id, user_id)

    def soft_delete_for_user(self, resume_id: int, user_id: int) -> bool:
        deleted = False
        updated: list[ResumeRecord] = []
        for record in self.created:
            if record.id == resume_id and record.user_id == user_id and record.deleted_at is None:
                updated.append(
                    ResumeRecord(
                        **{
                            **record.__dict__,
                            "deleted_at": datetime_for_tests(),
                            "is_default": False,
                            "original_file_path": "",
                            "structured_data": {},
                            "content_hash": None,
                        }
                    )
                )
                deleted = True
            else:
                updated.append(record)
        self.created = updated
        return deleted

    def get_original_file_path_for_user(self, resume_id: int, user_id: int) -> str | None:
        for record in self.created:
            if record.id == resume_id and record.user_id == user_id and record.deleted_at is None:
                return record.original_file_path
        return None

    def enqueue_file_cleanup(
        self,
        original_file_path: str,
        *,
        max_retries: int = 20,
    ) -> None:
        _ = max_retries
        self.cleanup_paths.append(original_file_path)

    def has_unfinished_interview_for_resume(self, resume_id: int, user_id: int) -> bool:
        return self.has_active_interview_dependency_for_resume(resume_id, user_id)

    def has_active_interview_dependency_for_resume(
        self,
        resume_id: int,
        user_id: int,
    ) -> bool:
        return (resume_id, user_id) in self.unfinished_interview_resume_ids

    def create_parse_task(
        self,
        *,
        user_id: int,
        original_file_path: str,
        content_hash: str,
    ) -> ResumeParseTaskRecord:
        task = ResumeParseTaskRecord(
            id=self.next_task_id,
            user_id=user_id,
            original_file_path=original_file_path,
            content_hash=content_hash,
            status="pending",
        )
        self.next_task_id += 1
        self.parse_tasks.append(task)
        return task

    def get_or_create_completed_parse_task(
        self,
        *,
        user_id: int,
        original_file_path: str,
        content_hash: str,
        resume_id: int,
    ) -> ResumeParseTaskRecord:
        existing = next(
            (
                task
                for task in reversed(self.parse_tasks)
                if task.user_id == user_id
                and task.content_hash == content_hash
                and task.resume_id == resume_id
                and task.status == "completed"
            ),
            None,
        )
        if existing is not None:
            return existing
        task = ResumeParseTaskRecord(
            id=self.next_task_id,
            user_id=user_id,
            original_file_path=original_file_path,
            content_hash=content_hash,
            status="completed",
            resume_id=resume_id,
            completed_at=datetime_for_tests(),
        )
        self.next_task_id += 1
        self.parse_tasks.append(task)
        return task

    def get_parse_task_for_user(
        self,
        task_id: int,
        user_id: int,
    ) -> ResumeParseTaskRecord | None:
        return next(
            (task for task in self.parse_tasks if task.id == task_id and task.user_id == user_id),
            None,
        )

    def get_parse_task(self, task_id: int) -> ResumeParseTaskRecord | None:
        return next((task for task in self.parse_tasks if task.id == task_id), None)

    def get_active_parse_task_by_content_hash(
        self,
        user_id: int,
        content_hash: str,
    ) -> ResumeParseTaskRecord | None:
        return next(
            (
                task
                for task in reversed(self.parse_tasks)
                if task.user_id == user_id
                and task.content_hash == content_hash
                and task.status in {"pending", "processing"}
            ),
            None,
        )

    def mark_parse_task_completed(self, task_id: int, resume_id: int) -> None:
        self.parse_tasks = [
            ResumeParseTaskRecord(
                **{
                    **task.__dict__,
                    "status": "completed",
                    "resume_id": resume_id,
                    "completed_at": datetime_for_tests(),
                }
            )
            if task.id == task_id
            else task
            for task in self.parse_tasks
        ]

    def mark_parse_task_processing(self, task_id: int) -> bool:
        updated = False
        tasks: list[ResumeParseTaskRecord] = []
        for task in self.parse_tasks:
            if task.id == task_id and task.status == "pending":
                tasks.append(
                    ResumeParseTaskRecord(
                        **{
                            **task.__dict__,
                            "status": "processing",
                            "started_at": datetime_for_tests(),
                        }
                    )
                )
                updated = True
            else:
                tasks.append(task)
        self.parse_tasks = tasks
        return updated

    def mark_parse_task_failed(self, task_id: int, error_message: str) -> None:
        self.parse_tasks = [
            ResumeParseTaskRecord(
                **{
                    **task.__dict__,
                    "status": "failed",
                    "error_message": error_message,
                    "completed_at": datetime_for_tests(),
                }
            )
            if task.id == task_id
            else task
            for task in self.parse_tasks
        ]


@pytest.fixture()
def resume_client(tmp_path: Path) -> tuple[TestClient, FakeResumeRepository, FakeLLMClient]:
    repository = FakeResumeRepository()
    llm_client = FakeLLMClient()
    settings = Settings(upload_dir=str(tmp_path / "resume"))
    parser = ResumeParserService(llm_client=llm_client, settings=settings)
    repository.parser = parser
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        id=42,
        username="alice",
        password_hash="hash",
        external_model_consent=True,
    )
    app.dependency_overrides[get_resume_repository] = lambda: repository
    app.dependency_overrides[get_resume_parser] = lambda: parser
    return TestClient(app), repository, llm_client


def read_parse_task(
    client: TestClient,
    repository: FakeResumeRepository,
    enqueue_response: Any,
) -> dict[str, Any]:
    assert enqueue_response.status_code == 202
    task_id = int(enqueue_response.json()["task_id"])
    task = repository.get_parse_task_for_user(task_id, 42)
    if task is None:
        task = repository.get_parse_task(task_id)
    assert task is not None
    if task.status == "pending":
        assert repository.parser is not None
        repository.mark_parse_task_processing(task_id)
        try:
            structured_data = repository.parser.parse(Path(task.original_file_path))
            resume = repository.create(
                user_id=task.user_id,
                original_file_path=task.original_file_path,
                structured_data=structured_data,
                content_hash=task.content_hash,
            )
            repository.mark_parse_task_completed(task_id, resume.id)
        except Exception as exc:
            Path(task.original_file_path).unlink(missing_ok=True)
            repository.mark_parse_task_failed(task_id, str(exc) or exc.__class__.__name__)
    task_response = client.get(
        f"/api/resumes/upload-tasks/{task_id}"
    )
    assert task_response.status_code == 200
    return task_response.json()


def test_upload_docx_success_binds_current_user(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, llm_client = resume_client

    response = client.post(
        "/api/resumes/upload-async",
        files={
            "file": (
                "resume.docx",
                make_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "completed"
    assert task["resume_id"] == 1
    assert task["structured_data"] == structured_resume()
    assert len(repository.created) == 1
    assert repository.created[0].user_id == 42
    stored_path = Path(repository.created[0].original_file_path)
    assert stored_path.parent.name == "42"
    assert stored_path.suffix == ".docx"
    assert "Python 开发" in llm_client.received_text
    assert llm_client.parse_calls == 1


def test_async_upload_duplicate_returns_completed_task(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, llm_client = resume_client
    content = make_docx_bytes()
    first_response = client.post(
        "/api/resumes/upload-async",
        files={
            "file": (
                "resume.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    first_task = read_parse_task(client, repository, first_response)
    assert first_task["status"] == "completed"

    responses = [
        client.post(
            "/api/resumes/upload-async",
            files={
                "file": (
                    "resume.docx",
                    content,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        for _ in range(20)
    ]

    assert all(response.status_code == 202 for response in responses)
    assert {response.json()["task_id"] for response in responses} == {1}
    assert all(response.json()["status"] == "completed" for response in responses)
    assert all(
        response.json()["resume_id"] == first_task["resume_id"]
        for response in responses
    )
    assert all(
        response.json()["structured_data"] == structured_resume()
        for response in responses
    )
    assert len(repository.parse_tasks) == 1
    assert llm_client.parse_calls == 1


def test_async_upload_reuses_pending_parse_task_before_writing_duplicate(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, llm_client = resume_client
    content = make_docx_bytes()
    content_hash = resume_content_hash(content)
    existing_task = repository.create_parse_task(
        user_id=42,
        original_file_path="already-uploaded.docx",
        content_hash=content_hash,
    )

    response = client.post(
        "/api/resumes/upload-async",
        files={
            "file": (
                "resume.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == existing_task.id
    assert response.json()["status"] == "pending"
    assert len(repository.parse_tasks) == 1
    assert llm_client.parse_calls == 0


def test_list_resumes_returns_history_metadata(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    from datetime import datetime

    client, repository, _llm_client = resume_client
    repository.summaries = [
        ResumeSummaryRecord(
            id=3,
            name="backend-resume.docx",
            uploaded_at=datetime(2026, 6, 15, 8, 30),
            last_used_at=datetime(2026, 6, 16, 9, 45),
            parse_status="parsed",
            is_default=True,
        )
    ]

    response = client.get("/api/resumes")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 3,
            "name": "backend-resume.docx",
            "uploaded_at": "2026-06-15T08:30:00",
            "last_used_at": "2026-06-16T09:45:00",
            "parse_status": "parsed",
            "is_default": True,
        }
    ]


def test_resume_detail_returns_structured_data(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path="resume/backend.docx",
            structured_data=structured_resume(),
            display_name="后端简历",
            is_default=True,
            created_at=datetime_for_tests(),
        )
    )

    response = client.get("/api/resumes/7")

    assert response.status_code == 200
    assert response.json()["name"] == "后端简历"
    assert response.json()["is_default"] is True
    assert response.json()["structured_data"] == structured_resume()


def test_rename_resume_updates_owned_resume(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path="resume/backend.docx",
            structured_data=structured_resume(),
            created_at=datetime_for_tests(),
        )
    )

    response = client.patch("/api/resumes/7", json={"name": "后端开发简历"})

    assert response.status_code == 200
    assert response.json()["name"] == "后端开发简历"
    assert repository.created[0].display_name == "后端开发简历"


def test_set_default_resume_clears_previous_default(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client
    repository.created.extend(
        [
            ResumeRecord(
                id=1,
                user_id=42,
                original_file_path="resume/a.docx",
                structured_data=structured_resume(),
                is_default=True,
            ),
            ResumeRecord(
                id=2,
                user_id=42,
                original_file_path="resume/b.docx",
                structured_data=structured_resume(),
            ),
        ]
    )

    response = client.post("/api/resumes/2/default")

    assert response.status_code == 200
    assert response.json()["is_default"] is True
    assert [record.is_default for record in repository.created] == [False, True]


def test_delete_resume_soft_deletes_owned_resume(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path="resume/backend.docx",
            structured_data=structured_resume(),
            is_default=True,
        )
    )

    response = client.delete("/api/resumes/7")

    assert response.status_code == 204
    assert repository.created[0].deleted_at is not None
    assert repository.created[0].is_default is False
    assert client.get("/api/resumes/7").status_code == 404


def test_delete_resume_rejects_unfinished_interview_dependency(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path="resume/backend.docx",
            structured_data=structured_resume(),
            is_default=True,
        )
    )
    repository.unfinished_interview_resume_ids.add((7, 42))

    response = client.delete("/api/resumes/7")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == ErrorCode.CONFLICT
    assert response.json()["error"]["message"] == ACTIVE_INTERVIEW_DELETE_MESSAGE
    assert repository.created[0].deleted_at is None
    assert repository.created[0].is_default is True


def test_resume_service_delete_rejects_active_interview_dependency() -> None:
    repository = FakeResumeRepository()
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path="resume/backend.docx",
            structured_data=structured_resume(),
            is_default=True,
        )
    )
    repository.unfinished_interview_resume_ids.add((7, 42))
    service = ResumeService(repository)

    with pytest.raises(AppError) as exc_info:
        service.delete_resume(resume_id=7, user_id=42)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == ErrorCode.CONFLICT
    assert exc_info.value.message == ACTIVE_INTERVIEW_DELETE_MESSAGE
    assert repository.created[0].deleted_at is None


def test_resume_service_preserves_file_when_commit_fails(tmp_path: Path) -> None:
    upload_dir = tmp_path / "resume"
    upload_dir.mkdir()
    original_path = upload_dir / "backend.docx"
    original_path.write_bytes(b"resume")
    repository = FakeResumeRepository()
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path=str(original_path),
            structured_data=structured_resume(),
        )
    )
    repository.commit_error = RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        ResumeService(repository, upload_dir=upload_dir).delete_resume(
            resume_id=7,
            user_id=42,
        )

    assert original_path.exists()


def test_resume_service_queues_file_cleanup_when_unlink_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_dir = tmp_path / "resume"
    upload_dir.mkdir()
    original_path = upload_dir / "backend.docx"
    original_path.write_bytes(b"resume")
    repository = FakeResumeRepository()
    repository.created.append(
        ResumeRecord(
            id=7,
            user_id=42,
            original_file_path=str(original_path),
            structured_data=structured_resume(),
        )
    )
    monkeypatch.setattr("app.services.resumes.delete_resume_file", lambda *_args: False)

    ResumeService(repository, upload_dir=upload_dir).delete_resume(
        resume_id=7,
        user_id=42,
    )

    assert repository.created[0].deleted_at is not None
    assert repository.cleanup_paths == [str(original_path)]


def test_upload_same_deleted_resume_creates_fresh_record(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, llm_client = resume_client
    content = make_docx_bytes()
    first_response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", content, "application/octet-stream")},
    )
    first_task = read_parse_task(client, repository, first_response)
    original_path = Path(repository.created[0].original_file_path)
    assert original_path.exists()
    delete_response = client.delete(f"/api/resumes/{first_task['resume_id']}")
    usage_limiter.reset()

    assert delete_response.status_code == 204
    assert not original_path.exists()

    replacement_response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", content, "application/octet-stream")},
    )

    replacement_task = read_parse_task(client, repository, replacement_response)
    assert replacement_task["status"] == "completed"
    assert replacement_task["resume_id"] != first_task["resume_id"]
    assert repository.created[0].deleted_at is not None
    assert repository.created[0].content_hash is None
    assert llm_client.parse_calls == 2


def test_upload_same_resume_reuses_existing_file_and_record(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, llm_client = resume_client
    content = make_docx_bytes()

    first_response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", content, "application/octet-stream")},
    )
    second_response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", content, "application/octet-stream")},
    )

    first_task = read_parse_task(client, repository, first_response)
    second_task = read_parse_task(client, repository, second_response)
    assert first_task["status"] == "completed"
    assert second_task["status"] == "completed"
    assert second_task["resume_id"] == first_task["resume_id"]
    assert len(repository.created) == 1
    stored_path = Path(repository.created[0].original_file_path)
    assert stored_path.parent.name == "42"
    assert stored_path.suffix == ".docx"
    assert list(stored_path.parent.iterdir()) == [stored_path]
    assert llm_client.parse_calls == 1


def test_resume_repository_create_locks_user_before_default_insert() -> None:
    source = inspect.getsource(ResumeRepository.create).lower()

    assert "_lock_user_resumes" in source
    assert "_has_active_resume_with_cursor" in source
    assert "default_key" in source
    assert source.index("_lock_user_resumes") < source.index("insert into resumes")


def test_resume_repository_default_paths_keep_unique_default_key() -> None:
    set_default_source = inspect.getsource(ResumeRepository.set_default_for_user).lower()
    soft_delete_source = inspect.getsource(ResumeRepository.soft_delete_for_user).lower()

    assert "for update" in set_default_source
    assert "default_key = null" in set_default_source
    assert "default_key = %s" in set_default_source
    assert "default_key = null" in soft_delete_source


class RecordingCursor:
    def __init__(self, row: dict[str, Any] | None = None, rowcount: int = 0) -> None:
        self.row = row
        self.rowcount = rowcount
        self.sql = ""
        self.params: tuple[Any, ...] = ()
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self.sql = sql
        self.params = params
        self.executed.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self.cursor_obj = cursor

    def cursor(self) -> RecordingCursor:
        return self.cursor_obj


def test_completed_parse_task_reuse_is_locked_and_does_not_insert() -> None:
    completed_at = datetime_for_tests()
    cursor = RecordingCursor(
        row={
            "id": 9,
            "user_id": 42,
            "original_file_path": "resume.docx",
            "content_hash": "a" * 64,
            "status": "completed",
            "resume_id": 7,
            "error_message": None,
            "created_at": completed_at,
            "started_at": None,
            "completed_at": completed_at,
        }
    )
    repository = ResumeRepository(RecordingConnection(cursor))

    task = repository.get_or_create_completed_parse_task(
        user_id=42,
        original_file_path="resume.docx",
        content_hash="a" * 64,
        resume_id=7,
    )

    statements = [" ".join(sql.lower().split()) for sql, _params in cursor.executed]
    assert task.id == 9
    assert statements[0] == "select id from users where id = %s for update"
    assert "from resume_parse_tasks" in statements[1]
    assert all("insert into resume_parse_tasks" not in sql for sql in statements)


def test_resume_repository_active_dependency_checks_status_and_overall_status() -> None:
    cursor = RecordingCursor(row={"exists": 1})
    repository = ResumeRepository(RecordingConnection(cursor))

    assert repository.has_active_interview_dependency_for_resume(7, 42) is True

    sql = " ".join(cursor.executed[0][0].lower().split())
    assert "coalesce" not in sql
    assert "status in" in sql
    assert "overall_status in" in sql
    assert "pending" not in cursor.params
    assert cursor.executed[0][1] == (
        7,
        42,
        *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
        *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
    )


def test_resume_repository_soft_delete_is_guarded_by_active_interview_dependency() -> None:
    cursor = RecordingCursor(rowcount=1)
    repository = ResumeRepository(RecordingConnection(cursor))

    assert repository.soft_delete_for_user(7, 42) is True

    sql = " ".join(cursor.executed[0][0].lower().split())
    assert "not exists" in sql
    assert "from interviews i" in sql
    assert "i.status in" in sql
    assert "i.overall_status in" in sql
    assert cursor.executed[0][1] == (
        7,
        42,
        *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
        *ACTIVE_INTERVIEW_DEPENDENCY_STATUSES,
    )
    snapshot_sql = " ".join(cursor.executed[1][0].lower().split())
    assert "set resume_snapshot = json_object()" in snapshot_sql
    assert cursor.executed[1][1] == (7, 42)


def test_upload_does_not_scan_historical_files_without_matching_hash(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repository, llm_client = resume_client
    repository.created.extend(
        [
            ResumeRecord(
                id=index,
                user_id=42,
                original_file_path=f"missing-{index}.docx",
                structured_data=structured_resume(),
                content_hash=None,
            )
            for index in range(1, 101)
        ]
    )
    repository.next_id = 101

    original_read_bytes = Path.read_bytes

    def fail_on_historical_read_bytes(path: Path) -> bytes:
        if path.name.startswith("missing-"):
            raise AssertionError("upload should not scan historical resume files")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_on_historical_read_bytes)

    response = client.post(
        "/api/resumes/upload-async",
        files={
            "file": (
                "fresh.docx",
                make_docx_bytes("一份全新的简历"),
                "application/octet-stream",
            )
        },
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "completed"
    assert task["resume_id"] == 101
    assert len(repository.created) == 101
    assert repository.list_by_user_calls == 0
    stored_path = Path(repository.created[-1].original_file_path)
    assert stored_path.parent.name == "42"
    assert stored_path.suffix == ".docx"
    assert llm_client.parse_calls == 1


def test_upload_rejects_unsupported_format(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client

    response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.pdf", b"fake", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.INVALID_UPLOAD_TYPE
    assert repository.created == []


def test_upload_rejects_oversized_file(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client

    response = client.post(
        "/api/resumes/upload-async",
        files={
            "file": (
                "resume.docx",
                b"x" * (10 * 1024 * 1024 + 1),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert repository.created == []


def test_upload_returns_parse_failed_when_docx_text_extraction_fails(
    resume_client: tuple[TestClient, FakeResumeRepository, FakeLLMClient],
) -> None:
    client, repository, _llm_client = resume_client

    response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", b"not a real docx", "application/octet-stream")},
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "failed"
    assert ErrorCode.RESUME_PARSE_FAILED in task["error_message"]
    assert repository.created == []


def test_upload_removes_file_when_parse_fails(tmp_path: Path) -> None:
    repository = FakeResumeRepository()
    upload_dir = tmp_path / "resume"
    parser = ResumeParserService(
        llm_client=FakeLLMClient(
            AppError(ErrorCode.RESUME_PARSE_FAILED, status_code=422),
        ),
        settings=Settings(upload_dir=str(upload_dir)),
    )
    repository.parser = parser
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        1,
        "alice",
        "hash",
        external_model_consent=True,
    )
    app.dependency_overrides[get_resume_repository] = lambda: repository
    app.dependency_overrides[get_resume_parser] = lambda: parser
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", make_docx_bytes(), "application/octet-stream")},
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "failed"
    assert repository.created == []
    assert upload_dir.exists()
    assert not any(path.is_file() for path in upload_dir.rglob("*"))


def test_upload_removes_file_when_database_create_fails(tmp_path: Path) -> None:
    repository = FakeResumeRepository()
    repository.create_error = RuntimeError("database unavailable")
    upload_dir = tmp_path / "resume"
    parser = ResumeParserService(
        llm_client=FakeLLMClient(),
        settings=Settings(upload_dir=str(upload_dir)),
    )
    repository.parser = parser
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        1,
        "alice",
        "hash",
        external_model_consent=True,
    )
    app.dependency_overrides[get_resume_repository] = lambda: repository
    app.dependency_overrides[get_resume_parser] = lambda: parser
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", make_docx_bytes(), "application/octet-stream")},
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "failed"
    assert repository.created == []
    assert upload_dir.exists()
    assert not any(path.is_file() for path in upload_dir.rglob("*"))


def test_upload_doc_conversion_uses_isolated_temp_output(tmp_path: Path) -> None:
    repository = FakeResumeRepository()
    upload_dir = tmp_path / "resume"
    upload_dir.mkdir()
    existing_docx = upload_dir / "resume.docx"
    existing_docx.write_bytes(make_docx_bytes("旧简历内容"))
    converted_dirs: list[Path] = []

    def fake_converter(input_path: Path, output_dir: Path) -> Path:
        converted_dirs.append(output_dir)
        converted_path = output_dir / f"{input_path.stem}.docx"
        converted_path.write_bytes(make_docx_bytes("本次转换后的简历"))
        return converted_path

    llm_client = FakeLLMClient()
    parser = ResumeParserService(
        llm_client=llm_client,
        settings=Settings(upload_dir=str(upload_dir)),
        converter=fake_converter,
    )
    repository.parser = parser
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        1,
        "alice",
        "hash",
        external_model_consent=True,
    )
    app.dependency_overrides[get_resume_repository] = lambda: repository
    app.dependency_overrides[get_resume_parser] = lambda: parser
    client = TestClient(app)

    response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.doc", b"legacy doc content", "application/msword")},
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "completed"
    stored_path = Path(repository.created[0].original_file_path)
    assert stored_path.parent.name == "1"
    assert stored_path.suffix == ".doc"
    assert "本次转换后的简历" in llm_client.received_text
    assert "旧简历内容" in extract_docx_text(existing_docx)
    assert converted_dirs
    assert converted_dirs[0].parent == upload_dir / "1"
    assert not converted_dirs[0].exists()
    assert sorted(path.name for path in upload_dir.iterdir()) == ["1", "resume.docx"]


def test_upload_propagates_deepseek_failure(tmp_path: Path) -> None:
    repository = FakeResumeRepository()
    parser = ResumeParserService(
        llm_client=FakeLLMClient(
            AppError(ErrorCode.LLM_API_KEY_MISSING, status_code=500),
        ),
        settings=Settings(upload_dir=str(tmp_path / "resume")),
    )
    repository.parser = parser
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        1,
        "alice",
        "hash",
        external_model_consent=True,
    )
    app.dependency_overrides[get_resume_repository] = lambda: repository
    app.dependency_overrides[get_resume_parser] = lambda: parser
    client = TestClient(app)

    response = client.post(
        "/api/resumes/upload-async",
        files={"file": ("resume.docx", make_docx_bytes(), "application/octet-stream")},
    )

    task = read_parse_task(client, repository, response)
    assert task["status"] == "failed"
    assert ErrorCode.LLM_API_KEY_MISSING in task["error_message"]
    assert repository.created == []


def test_doc_conversion_flow_is_mockable(tmp_path: Path) -> None:
    doc_path = tmp_path / "resume.doc"
    doc_path.write_bytes(b"legacy doc content")
    calls: list[tuple[Path, Path]] = []

    def fake_converter(input_path: Path, output_dir: Path) -> Path:
        calls.append((input_path, output_dir))
        converted_path = output_dir / f"{input_path.stem}.docx"
        converted_path.write_bytes(make_docx_bytes("转换后的简历"))
        return converted_path

    llm_client = FakeLLMClient()
    parser = ResumeParserService(
        llm_client=llm_client,
        settings=Settings(upload_dir=str(tmp_path)),
        converter=fake_converter,
    )

    result = parser.parse(doc_path)

    assert result == structured_resume()
    assert calls[0][0] == doc_path
    assert calls[0][1].parent == tmp_path
    assert calls[0][1].name.startswith("resume-converted-")
    assert not calls[0][1].exists()
    assert "转换后的简历" in llm_client.received_text


def test_extract_docx_text_reads_textbox_content(tmp_path: Path) -> None:
    docx_path = tmp_path / "textbox-resume.docx"
    docx_path.write_bytes(make_textbox_docx_bytes("文本框里的简历内容"))

    text = extract_docx_text(docx_path)

    assert "文本框里的简历内容" in text


def test_store_resume_upload_uses_exclusive_unique_paths(tmp_path: Path) -> None:
    first = store_resume_upload("resume.docx", tmp_path, b"first")
    second = store_resume_upload("resume.docx", tmp_path, b"second")

    assert first != second
    assert first.suffix == second.suffix == ".docx"
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_extract_docx_text_rejects_oversized_archive_member(tmp_path: Path) -> None:
    docx_path = tmp_path / "bomb.docx"
    with ZipFile(docx_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", b"A" * (MAX_DOCX_MEMBER_BYTES + 1))

    with pytest.raises(AppError) as exc_info:
        extract_docx_text(docx_path)

    assert exc_info.value.code == ErrorCode.RESUME_PARSE_FAILED


def test_parse_restores_project_title_missing_from_llm_result(tmp_path: Path) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(
        make_docx_bytes(
            "项目经历\n"
            "2026.5至今 医疗知识问答系统\n"
            "2026.4至今 基于LangGraph的多Agent智能旅行规划系统 github\n"
            "教育经历\n"
            "2022.9-2026.6 湖北大学 人工智能/本科"
        )
    )
    llm_result = structured_resume()
    llm_result["education"] = [{"school": "湖北大学"}]
    llm_result["project_experience"] = [
        {"name": "基于LangGraph的多Agent智能旅行规划系统"}
    ]
    parser = ResumeParserService(
        llm_client=FakeLLMClient(llm_result),
        settings=Settings(upload_dir=str(tmp_path)),
    )

    result = parser.parse(docx_path)

    project_names = [item.get("name") for item in result["project_experience"]]
    assert project_names == [
        "基于LangGraph的多Agent智能旅行规划系统",
        "医疗知识问答系统",
    ]
    assert all("湖北大学" not in str(item) for item in result["project_experience"])


def test_invalid_structured_resume_is_parse_failed(tmp_path: Path) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(make_docx_bytes())
    parser = ResumeParserService(
        llm_client=FakeLLMClient({"basic_info": {}, "education": []}),
        settings=Settings(upload_dir=str(tmp_path)),
    )

    with pytest.raises(AppError) as exc_info:
        parser.parse(docx_path)

    assert exc_info.value.code == ErrorCode.RESUME_PARSE_FAILED


def test_parse_rejects_expanded_text_over_limit_before_llm(tmp_path: Path) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(make_docx_bytes("Python " * 50))
    llm_client = FakeLLMClient()
    parser = ResumeParserService(
        llm_client=llm_client,
        settings=Settings(upload_dir=str(tmp_path), resume_max_text_chars=20),
    )

    with pytest.raises(AppError) as exc_info:
        parser.parse(docx_path)

    assert exc_info.value.code == ErrorCode.RESUME_PARSE_FAILED
    assert llm_client.parse_calls == 0


def test_doc_conversion_timeout_is_parse_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_path = tmp_path / "resume.doc"
    doc_path.write_bytes(b"legacy doc content")
    output_dir = tmp_path / "converted"
    monkeypatch.setattr(resume_parser_module.shutil, "which", lambda _name: "libreoffice")

    def timeout_run(*args: object, **kwargs: object) -> None:
        _ = args, kwargs
        raise subprocess.TimeoutExpired(cmd="libreoffice", timeout=1)

    monkeypatch.setattr(resume_parser_module.subprocess, "run", timeout_run)

    with pytest.raises(AppError) as exc_info:
        convert_doc_to_docx(doc_path, output_dir)

    assert exc_info.value.code == ErrorCode.RESUME_PARSE_FAILED
