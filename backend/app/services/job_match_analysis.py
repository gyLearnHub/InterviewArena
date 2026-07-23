from typing import Protocol

from fastapi import status
from pydantic import ValidationError

from app.core.errors import AppError, ErrorCode
from app.prompts.loader import load_prompt
from app.repositories.resumes import ResumeDetailRecord
from app.schemas.resume import (
    JobMatchAnalysisResponse,
    JobMatchAnalysisResult,
    StructuredResumeData,
)
from app.services.llm import LLMClient
from app.services.usage_limits import usage_limiter

JOB_MATCH_ANALYSIS_BASIS = (
    "本分析仅依据当前简历中可见的信息与职位描述生成，未体现的内容不代表候选人不具备，"
    "结果仅用于面试准备参考。"
)
RESUME_NOT_PARSED_MESSAGE = "简历尚未解析成功，暂不能进行岗位匹配分析。"


class JobMatchResumeRepository(Protocol):
    def get_detail_for_user(self, resume_id: int, user_id: int) -> ResumeDetailRecord | None:
        ...


class JobMatchAnalysisService:
    def __init__(
        self,
        repository: JobMatchResumeRepository,
        llm_client: LLMClient,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client

    def analyze(
        self,
        *,
        resume_id: int,
        user_id: int,
        target_position: str,
        job_description: str,
    ) -> JobMatchAnalysisResponse:
        resume = self.repository.get_detail_for_user(resume_id, user_id)
        if resume is None:
            raise AppError(ErrorCode.NOT_FOUND, status.HTTP_404_NOT_FOUND)
        if resume.parse_status != "parsed":
            raise AppError(
                ErrorCode.CONFLICT,
                status.HTTP_409_CONFLICT,
                message=RESUME_NOT_PARSED_MESSAGE,
            )

        try:
            structured_resume = StructuredResumeData.model_validate(resume.structured_data)
        except ValidationError as exc:
            raise AppError(
                ErrorCode.RESUME_PARSE_FAILED,
                status.HTTP_409_CONFLICT,
                message=RESUME_NOT_PARSED_MESSAGE,
            ) from exc

        with usage_limiter.guard(user_id, "job_match_analysis"):
            raw_result = self.llm_client.generate_json(
                load_prompt("job_match_analysis.md"),
                {
                    "resume": structured_resume.model_dump(),
                    "target_position": target_position,
                    "job_description": job_description,
                },
            )
        try:
            result = JobMatchAnalysisResult.model_validate(raw_result)
        except ValidationError as exc:
            raise AppError(
                ErrorCode.BUSINESS_ERROR,
                status.HTTP_502_BAD_GATEWAY,
                details={"provider": "deepseek", "error": "invalid_model_output"},
            ) from exc

        return JobMatchAnalysisResponse(
            resume_id=resume_id,
            target_position=target_position,
            analysis_basis=JOB_MATCH_ANALYSIS_BASIS,
            **result.model_dump(),
        )
