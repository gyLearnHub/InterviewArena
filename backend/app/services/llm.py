import json
import time
from typing import Any, Protocol, TypeVar

import httpx
from fastapi import status
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.schemas.llm import FeedbackResult, QuestionResult, StructuredResume

JSONDict = dict[str, Any]
TModel = TypeVar("TModel", bound=BaseModel)


class LLMClient(Protocol):
    @property
    def model_name(self) -> str:
        ...

    def parse_resume(self, resume_text: str) -> JSONDict:
        ...

    def generate_question(
        self,
        resume: JSONDict,
        target_position: str,
        qa_history: list[JSONDict],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> JSONDict:
        ...

    def generate_feedback(
        self,
        resume: JSONDict,
        target_position: str,
        qa_history: list[JSONDict],
    ) -> JSONDict:
        ...

    def generate_json(self, system_prompt: str, user_payload: JSONDict) -> JSONDict:
        ...


class DeepSeekLLMClient:
    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
        model_name: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.http_client = http_client
        self._model_name = model_name or self.settings.deepseek_model

    @property
    def model_name(self) -> str:
        return self._model_name

    def parse_resume(self, resume_text: str) -> JSONDict:
        payload = self._complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是简历结构化解析助手。只返回 JSON，不要返回解释。"
                        "JSON 必须包含 basic_info、education、work_experience、"
                        "project_experience、skills、certificates_awards。"
                        "必须完整提取原文中的所有项目，不能只保留代表项目；"
                        "只有项目标题、细节暂缺的项目也必须保留在 project_experience 中，"
                        "不得补写原文没有的项目事实。"
                    ),
                },
                {"role": "user", "content": resume_text},
            ]
        )
        return self._validate_payload(payload, StructuredResume).model_dump()

    def generate_question(
        self,
        resume: JSONDict,
        target_position: str,
        qa_history: list[JSONDict],
        previous_answer: str | None = None,
        system_prompt: str | None = None,
    ) -> JSONDict:
        user_payload = {
            "resume": resume,
            "target_position": target_position,
            "qa_history": qa_history,
            "previous_answer": previous_answer,
        }
        question_system_prompt = system_prompt or (
            "你是模拟面试官。只返回 JSON，字段为 question_type 和 question。"
            "问题应贴合简历、目标岗位和历史问答。"
        )
        payload = self._complete_json(
            [
                {"role": "system", "content": question_system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ]
        )
        return self._validate_payload(payload, QuestionResult).model_dump()

    def generate_feedback(
        self,
        resume: JSONDict,
        target_position: str,
        qa_history: list[JSONDict],
    ) -> JSONDict:
        user_payload = {
            "resume": resume,
            "target_position": target_position,
            "qa_history": qa_history,
        }
        payload = self._complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是面试反馈评估助手。只返回 JSON，字段为 score、weaknesses、"
                        "suggestions。score 必须是 0 到 100 的整数，weaknesses 和 "
                        "suggestions 必须是字符串数组。"
                    ),
                },
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ]
        )
        return self._validate_payload(payload, FeedbackResult).model_dump()

    def generate_json(self, system_prompt: str, user_payload: JSONDict) -> JSONDict:
        return self._complete_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ]
        )

    def _complete_json(self, messages: list[JSONDict]) -> JSONDict:
        if not self.settings.deepseek_api_key:
            raise AppError(
                ErrorCode.LLM_API_KEY_MISSING,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = self._post_with_retry(messages)
        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise self._invalid_response_error() from exc
        if not isinstance(content, str) or not content.strip():
            raise self._invalid_response_error()
        return self._parse_json_content(content)

    def _post_with_retry(self, messages: list[JSONDict]) -> JSONDict:
        last_error: Exception | None = None
        for attempt in range(self.settings.deepseek_retry_count + 1):
            try:
                response = self._post(messages)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise self._invalid_response_error()
                return data
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= self.settings.deepseek_retry_count:
                    raise AppError(
                        ErrorCode.NETWORK_TIMEOUT,
                        status.HTTP_504_GATEWAY_TIMEOUT,
                        details={"provider": "deepseek", "error": "timeout"},
                    ) from exc
                _wait_before_retry(attempt)
            except httpx.RequestError as exc:
                last_error = exc
                if attempt >= self.settings.deepseek_retry_count:
                    raise AppError(
                        ErrorCode.BUSINESS_ERROR,
                        status.HTTP_502_BAD_GATEWAY,
                        details={
                            "provider": "deepseek",
                            "error": exc.__class__.__name__,
                        },
                    ) from exc
                _wait_before_retry(attempt)
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if (
                    _is_retryable_status(exc.response.status_code)
                    and attempt < self.settings.deepseek_retry_count
                ):
                    _wait_before_retry(attempt, exc.response)
                    continue
                raise AppError(
                    ErrorCode.BUSINESS_ERROR,
                    status.HTTP_502_BAD_GATEWAY,
                    details=_response_error_details(exc.response),
                ) from exc
            except json.JSONDecodeError as exc:
                last_error = exc
                raise AppError(
                    ErrorCode.BUSINESS_ERROR,
                    status.HTTP_502_BAD_GATEWAY,
                    details={"provider": "deepseek", "error": "invalid_response_json"},
                ) from exc

        raise AppError(
            ErrorCode.BUSINESS_ERROR,
            status.HTTP_502_BAD_GATEWAY,
            details={"provider": "deepseek", "error": "unknown"},
        ) from last_error

    def _post(self, messages: list[JSONDict]) -> httpx.Response:
        request_body = {
            "model": self._model_name,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        url = self.settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        if self.http_client is not None:
            return self.http_client.post(url, json=request_body, headers=headers)
        with httpx.Client(timeout=self.settings.deepseek_timeout_seconds) as client:
            return client.post(url, json=request_body, headers=headers)

    def _parse_json_content(self, content: str) -> JSONDict:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise self._invalid_response_error() from exc
        if not isinstance(payload, dict):
            raise self._invalid_response_error()
        return payload

    def _validate_payload(self, payload: JSONDict, schema: type[TModel]) -> TModel:
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            raise self._invalid_response_error() from exc

    def _invalid_response_error(self) -> AppError:
        return AppError(
            ErrorCode.BUSINESS_ERROR,
            status.HTTP_502_BAD_GATEWAY,
            details={"provider": "deepseek", "error": "invalid_model_output"},
        )


def get_llm_client() -> LLMClient:
    return DeepSeekLLMClient()


def _response_error_details(response: httpx.Response) -> JSONDict:
    details: JSONDict = {
        "provider": "deepseek",
        "status_code": response.status_code,
    }
    try:
        data = response.json()
    except json.JSONDecodeError:
        details["error"] = "provider_error"
        return details
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            details["error"] = {
                "code": error.get("code"),
                "type": error.get("type"),
            }
        else:
            details["error"] = "provider_error"
    return details


def _is_retryable_status(status_code: int) -> bool:
    return status_code == status.HTTP_429_TOO_MANY_REQUESTS or status_code >= 500


def _wait_before_retry(attempt: int, response: httpx.Response | None = None) -> None:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    delay_seconds: float
    try:
        delay_seconds = float(retry_after) if retry_after is not None else 0.0
    except ValueError:
        delay_seconds = 0.0
    if delay_seconds <= 0:
        delay_seconds = min(2.0, 0.25 * (2**attempt))
    time.sleep(min(delay_seconds, 5.0))
