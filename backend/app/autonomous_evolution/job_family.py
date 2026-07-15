from __future__ import annotations

import hashlib
import re
from typing import Any

from app.autonomous_evolution.contracts import JobFamilyDecision
from app.autonomous_evolution.repository import AutonomousEvolutionRepository

CLASSIFIER_PROMPT = """
你负责把面试目标岗位归入稳定的岗位类型。只能返回 JSON。
优先复用 existing_keys；只有都不合适时才创建新的简短英文 kebab-case key。
不得根据候选人的姓名、学校或公司分类。
返回字段：key、label、matched_existing、confidence。
""".strip()


class JobFamilyClassifier:
    def __init__(self, repository: AutonomousEvolutionRepository, llm_client: Any) -> None:
        self.repository = repository
        self.llm_client = llm_client

    def classify(
        self,
        target_position: str,
        job_description: str | None,
        *,
        user_id: int | None = None,
    ) -> JobFamilyDecision:
        if user_id is None:
            existing_keys = self.repository.list_job_family_keys()
        else:
            existing_keys = self.repository.list_job_family_keys(user_id=user_id)
        try:
            payload = self.llm_client.generate_json(
                CLASSIFIER_PROMPT,
                {
                    "target_position": target_position,
                    "job_description": (job_description or "")[:6000],
                    "existing_keys": existing_keys,
                },
            )
            decision = JobFamilyDecision.model_validate(payload)
            if decision.matched_existing and decision.key not in existing_keys:
                raise ValueError("classifier selected a missing existing job family")
            if decision.key in existing_keys and not decision.matched_existing:
                decision = decision.model_copy(update={"matched_existing": True})
            return decision
        except Exception:
            fallback_key = _fallback_key(target_position)
            if fallback_key in existing_keys:
                return JobFamilyDecision(
                    key=fallback_key,
                    label=target_position.strip()[:128] or "未分类岗位",
                    matched_existing=True,
                    confidence=0.0,
                )
            return JobFamilyDecision(
                key="global-default",
                label="通用岗位",
                matched_existing="global-default" in existing_keys,
                confidence=0.0,
            )


def _fallback_key(target_position: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", target_position.casefold()).strip("-")
    if normalized:
        return normalized[:96]
    digest = hashlib.sha256(target_position.encode("utf-8")).hexdigest()[:16]
    return f"unclassified-{digest}"
