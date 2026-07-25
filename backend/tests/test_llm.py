import json
from typing import Any

import httpx
import pytest
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services.llm import DeepSeekLLMClient


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": Settings.database_url,
        "jwt_secret_key": Settings.jwt_secret_key,
        "jwt_algorithm": Settings.jwt_algorithm,
        "jwt_expire_minutes": Settings.jwt_expire_minutes,
        "deepseek_api_key": "test-key",
        "deepseek_base_url": "https://unit.test",
        "deepseek_model": "deepseek-v4-pro",
        "deepseek_timeout_seconds": 60,
        "deepseek_retry_count": 2,
        "upload_dir": Settings.upload_dir,
    }
    values.update(overrides)
    return Settings(**values)


def make_client(content: str, captured_bodies: list[dict[str, Any]] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        if captured_bodies is not None:
            captured_bodies.append(body)
        assert request.url == "https://unit.test/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == "deepseek-v4-pro"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def valid_resume_payload() -> str:
    return json.dumps(
        {
            "basic_info": {"name": "张三"},
            "education": [{"school": "A University"}],
            "work_experience": [],
            "project_experience": [],
            "skills": ["Python"],
            "certificates_awards": [],
        },
        ensure_ascii=False,
    )


def test_parse_resume_requires_api_key() -> None:
    client = DeepSeekLLMClient(settings=make_settings(deepseek_api_key=""))

    with pytest.raises(AppError) as exc_info:
        client.parse_resume("resume text")

    assert exc_info.value.code == ErrorCode.LLM_API_KEY_MISSING


def test_parse_resume_validates_structure() -> None:
    client = DeepSeekLLMClient(
        settings=make_settings(),
        http_client=make_client('{"basic_info": {}, "education": []}'),
    )

    with pytest.raises(AppError) as exc_info:
        client.parse_resume("resume text")

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR


def test_generate_question_returns_valid_question() -> None:
    client = DeepSeekLLMClient(
        settings=make_settings(),
        http_client=make_client('{"question_type": "skill_check", "question": "请介绍 Python。"}'),
    )

    result = client.generate_question(
        resume=json.loads(valid_resume_payload()),
        target_position="后端开发",
        qa_history=[],
        previous_answer=None,
    )

    assert result == {"question_type": "skill_check", "question": "请介绍 Python。"}


def test_generate_question_uses_custom_system_prompt() -> None:
    captured_bodies: list[dict[str, Any]] = []
    client = DeepSeekLLMClient(
        settings=make_settings(),
        http_client=make_client(
            '{"question_type": "skill_check", "question": "请介绍项目。"}',
            captured_bodies=captured_bodies,
        ),
    )

    result = client.generate_question(
        resume=json.loads(valid_resume_payload()),
        target_position="后端开发",
        qa_history=[],
        previous_answer=None,
        system_prompt="你是简历面试官。只返回 JSON。",
    )

    assert result == {"question_type": "skill_check", "question": "请介绍项目。"}
    assert captured_bodies[0]["messages"][0] == {
        "role": "system",
        "content": "你是简历面试官。只返回 JSON。",
    }


def test_generate_feedback_returns_valid_feedback() -> None:
    client = DeepSeekLLMClient(
        settings=make_settings(),
        http_client=make_client(
            '{"score": 88, "weaknesses": ["项目细节不足"], "suggestions": ["补充量化结果"]}'
        ),
    )

    result = client.generate_feedback(
        resume=json.loads(valid_resume_payload()),
        target_position="后端开发",
        qa_history=[
            {
                "sequence": 1,
                "question_type": "skill_check",
                "question": "问题",
                "answer": "回答",
            }
        ],
    )

    assert result == {
        "score": 88,
        "weaknesses": ["项目细节不足"],
        "suggestions": ["补充量化结果"],
    }


def test_timeout_is_converted_after_retries() -> None:
    attempts: list[str] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append("called")
        raise httpx.TimeoutException("timeout")

    client = DeepSeekLLMClient(
        settings=make_settings(deepseek_retry_count=2),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AppError) as exc_info:
        client.generate_question(
            resume=json.loads(valid_resume_payload()),
            target_position="后端开发",
            qa_history=[],
            previous_answer=None,
        )

    assert exc_info.value.code == ErrorCode.NETWORK_TIMEOUT
    assert len(attempts) == 3


@pytest.mark.parametrize("transient_status", [429, 500, 503])
def test_transient_http_status_is_retried(
    transient_status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    monkeypatch.setattr("app.services.llm.time.sleep", lambda _seconds: None)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(transient_status, headers={"Retry-After": "1"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"question_type":"skill_check","question":"问题"}'
                        }
                    }
                ]
            },
        )

    client = DeepSeekLLMClient(
        settings=make_settings(deepseek_retry_count=2),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.generate_question({}, "后端开发", [])

    assert result["question"] == "问题"
    assert attempts == 2


def test_invalid_response_json_is_business_error() -> None:
    client = DeepSeekLLMClient(
        settings=make_settings(),
        http_client=make_client("not json"),
    )

    with pytest.raises(AppError) as exc_info:
        client.generate_feedback(
            resume=json.loads(valid_resume_payload()),
            target_position="后端开发",
            qa_history=[],
        )

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR


def test_http_status_error_keeps_redacted_diagnostics() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"code": "invalid_request", "message": "payload too large"}},
        )

    client = DeepSeekLLMClient(
        settings=make_settings(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(AppError) as exc_info:
        client.generate_json("只返回 JSON", {"text": "hello"})

    assert exc_info.value.code == ErrorCode.BUSINESS_ERROR
    assert exc_info.value.details == {
        "provider": "deepseek",
        "status_code": 400,
        "error": {
            "code": "invalid_request",
            "type": None,
        },
    }
    assert "test-key" not in str(exc_info.value)
    assert "authorization" not in str(exc_info.value).lower()
