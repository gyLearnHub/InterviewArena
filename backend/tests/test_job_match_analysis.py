from datetime import datetime
from typing import Any

import pytest
from app.api.resumes import get_job_match_llm_client, get_resume_repository
from app.core.errors import AppError, ErrorCode
from app.deps import get_current_user
from app.repositories.resumes import ResumeDetailRecord
from app.repositories.users import UserRecord
from app.schemas.interview import JOB_DESCRIPTION_MAX_LENGTH
from app.services.job_match_analysis import (
    JOB_MATCH_ANALYSIS_BASIS,
    RESUME_NOT_PARSED_MESSAGE,
    JobMatchAnalysisService,
)
from fastapi.testclient import TestClient
from main import create_app


def structured_resume() -> dict[str, Any]:
    return {
        "basic_info": {"name": "张三"},
        "education": [],
        "work_experience": [],
        "project_experience": [
            {"name": "订单平台", "description": "使用 FastAPI 开发接口"}
        ],
        "skills": ["Python", "FastAPI"],
        "certificates_awards": [],
    }


def valid_analysis() -> dict[str, Any]:
    return {
        "summary": "基于当前简历可见信息，后端技能有一定匹配，数据库经验仍需核实。",
        "matched_requirements": [
            {"requirement": "掌握 Python", "evidence": "技能列表包含 Python"}
        ],
        "missing_requirements": [
            {"requirement": "熟悉 MySQL", "evidence_gap": "当前简历未体现 MySQL 使用经历"}
        ],
        "risk_questions": [
            {
                "question": "请介绍你使用 MySQL 进行索引优化的经历。",
                "related_requirement": "熟悉 MySQL",
            }
        ],
        "preparation_suggestions": [
            {
                "suggestion": "准备一个能够说明数据库设计取舍的真实项目案例。",
                "related_requirement": "熟悉 MySQL",
            }
        ],
    }


class StubResumeRepository:
    def __init__(self, resume: ResumeDetailRecord | None) -> None:
        self.resume = resume
        self.calls: list[tuple[int, int]] = []

    def get_detail_for_user(self, resume_id: int, user_id: int) -> ResumeDetailRecord | None:
        self.calls.append((resume_id, user_id))
        return self.resume


class StubLLMClient:
    def __init__(self, result: dict[str, Any] | AppError) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def generate_json(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((system_prompt, user_payload))
        if isinstance(self.result, AppError):
            raise self.result
        return self.result


def resume_detail(
    *,
    parse_status: str = "parsed",
    data: dict[str, Any] | None = None,
) -> ResumeDetailRecord:
    return ResumeDetailRecord(
        id=7,
        name="后端简历",
        uploaded_at=datetime(2026, 7, 20, 12, 0),
        last_used_at=None,
        parse_status=parse_status,
        structured_data=structured_resume() if data is None else data,
        is_default=True,
    )


def test_service_generates_structured_analysis_from_owned_parsed_resume() -> None:
    repository = StubResumeRepository(resume_detail())
    llm_client = StubLLMClient(valid_analysis())
    service = JobMatchAnalysisService(repository, llm_client)  # type: ignore[arg-type]

    result = service.analyze(
        resume_id=7,
        user_id=42,
        target_position="后端开发工程师",
        job_description="要求掌握 Python、FastAPI 和 MySQL。",
    )

    assert repository.calls == [(7, 42)]
    assert len(llm_client.calls) == 1
    prompt, payload = llm_client.calls[0]
    assert "当前简历未体现" in prompt
    assert payload == {
        "resume": structured_resume(),
        "target_position": "后端开发工程师",
        "job_description": "要求掌握 Python、FastAPI 和 MySQL。",
    }
    assert result.resume_id == 7
    assert result.target_position == "后端开发工程师"
    assert result.analysis_basis == JOB_MATCH_ANALYSIS_BASIS
    assert result.matched_requirements[0].evidence == "技能列表包含 Python"
    assert result.missing_requirements[0].evidence_gap == "当前简历未体现 MySQL 使用经历"


def test_service_does_not_call_llm_for_unowned_resume() -> None:
    llm_client = StubLLMClient(valid_analysis())
    service = JobMatchAnalysisService(
        StubResumeRepository(None),
        llm_client,  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as exc_info:
        service.analyze(
            resume_id=7,
            user_id=42,
            target_position="后端开发工程师",
            job_description="要求掌握 Python。",
        )

    assert exc_info.value.code == ErrorCode.NOT_FOUND
    assert exc_info.value.status_code == 404
    assert llm_client.calls == []


@pytest.mark.parametrize(
    ("resume", "expected_code"),
    [
        (resume_detail(parse_status="processing"), ErrorCode.CONFLICT),
        (resume_detail(data={}), ErrorCode.RESUME_PARSE_FAILED),
    ],
)
def test_service_rejects_resume_that_is_not_successfully_parsed(
    resume: ResumeDetailRecord,
    expected_code: ErrorCode,
) -> None:
    llm_client = StubLLMClient(valid_analysis())
    service = JobMatchAnalysisService(
        StubResumeRepository(resume),
        llm_client,  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as exc_info:
        service.analyze(
            resume_id=7,
            user_id=42,
            target_position="后端开发工程师",
            job_description="要求掌握 Python。",
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == 409
    assert exc_info.value.message == RESUME_NOT_PARSED_MESSAGE
    assert llm_client.calls == []


def test_service_rejects_invalid_model_output_without_fallback() -> None:
    llm_client = StubLLMClient({"summary": "缺少结构化列表"})
    service = JobMatchAnalysisService(
        StubResumeRepository(resume_detail()),
        llm_client,  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as exc_info:
        service.analyze(
            resume_id=7,
            user_id=42,
            target_position="后端开发工程师",
            job_description="要求掌握 Python。",
        )

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR
    assert exc_info.value.status_code == 502
    assert exc_info.value.details == {
        "provider": "deepseek",
        "error": "invalid_model_output",
    }
    assert len(llm_client.calls) == 1


def test_service_propagates_llm_failure_without_making_up_analysis() -> None:
    llm_error = AppError(
        ErrorCode.LLM_API_KEY_MISSING,
        500,
    )
    llm_client = StubLLMClient(llm_error)
    service = JobMatchAnalysisService(
        StubResumeRepository(resume_detail()),
        llm_client,  # type: ignore[arg-type]
    )

    with pytest.raises(AppError) as exc_info:
        service.analyze(
            resume_id=7,
            user_id=42,
            target_position="后端开发工程师",
            job_description="要求掌握 Python。",
        )

    assert exc_info.value is llm_error
    assert len(llm_client.calls) == 1


@pytest.fixture()
def api_client() -> tuple[TestClient, StubResumeRepository, StubLLMClient]:
    repository = StubResumeRepository(resume_detail())
    llm_client = StubLLMClient(valid_analysis())
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserRecord(
        id=42,
        username="alice",
        password_hash="hash",
    )
    app.dependency_overrides[get_resume_repository] = lambda: repository
    app.dependency_overrides[get_job_match_llm_client] = lambda: llm_client
    return TestClient(app), repository, llm_client


def test_job_match_analysis_api_returns_validated_contract(
    api_client: tuple[TestClient, StubResumeRepository, StubLLMClient],
) -> None:
    client, repository, llm_client = api_client

    response = client.post(
        "/api/resumes/7/job-match-analysis",
        json={
            "target_position": "  后端开发工程师  ",
            "job_description": "  要求掌握 Python、FastAPI 和 MySQL。  ",
        },
    )

    assert response.status_code == 200
    assert repository.calls == [(7, 42)]
    assert llm_client.calls[0][1]["target_position"] == "后端开发工程师"
    assert llm_client.calls[0][1]["job_description"] == "要求掌握 Python、FastAPI 和 MySQL。"
    assert response.json() == {
        "resume_id": 7,
        "target_position": "后端开发工程师",
        **valid_analysis(),
        "analysis_basis": JOB_MATCH_ANALYSIS_BASIS,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"target_position": "后端开发工程师", "job_description": "   "},
        {
            "target_position": "后端开发工程师",
            "job_description": "J" * (JOB_DESCRIPTION_MAX_LENGTH + 1),
        },
        {"target_position": "   ", "job_description": "要求掌握 Python。"},
    ],
)
def test_job_match_analysis_api_validates_request_before_llm(
    api_client: tuple[TestClient, StubResumeRepository, StubLLMClient],
    payload: dict[str, str],
) -> None:
    client, repository, llm_client = api_client

    response = client.post("/api/resumes/7/job-match-analysis", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR
    assert repository.calls == []
    assert llm_client.calls == []


def test_job_match_analysis_api_hides_unowned_resume(
    api_client: tuple[TestClient, StubResumeRepository, StubLLMClient],
) -> None:
    client, repository, llm_client = api_client
    repository.resume = None

    response = client.post(
        "/api/resumes/99/job-match-analysis",
        json={
            "target_position": "后端开发工程师",
            "job_description": "要求掌握 Python。",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == ErrorCode.NOT_FOUND
    assert repository.calls == [(99, 42)]
    assert llm_client.calls == []


def test_job_match_analysis_api_returns_llm_error(
    api_client: tuple[TestClient, StubResumeRepository, StubLLMClient],
) -> None:
    client, _repository, llm_client = api_client
    llm_client.result = AppError(ErrorCode.NETWORK_TIMEOUT, 504)

    response = client.post(
        "/api/resumes/7/job-match-analysis",
        json={
            "target_position": "后端开发工程师",
            "job_description": "要求掌握 Python。",
        },
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == ErrorCode.NETWORK_TIMEOUT


def test_job_match_analysis_api_rate_limits_repeated_llm_calls(
    api_client: tuple[TestClient, StubResumeRepository, StubLLMClient],
) -> None:
    client, _repository, llm_client = api_client
    payload = {
        "target_position": "后端开发工程师",
        "job_description": "要求掌握 Python。",
    }

    first_response = client.post("/api/resumes/7/job-match-analysis", json=payload)
    second_response = client.post("/api/resumes/7/job-match-analysis", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == ErrorCode.TOO_MANY_REQUESTS
    assert len(llm_client.calls) == 1
