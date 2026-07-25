from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.errors import safe_error_code
from app.skills.registry import DEFAULT_SKILL_REGISTRY, SkillRegistry
from app.skills.selector import select_skills
from app.skills.types import SkillCallTrace, SkillContext, SkillRunBundle
from app.skills.utils import input_summary, output_summary


class SkillRunner:
    def __init__(
        self,
        registry: SkillRegistry | None = None,
        *,
        max_skills_per_call: int = 2,
    ) -> None:
        self.registry = registry or DEFAULT_SKILL_REGISTRY
        self.max_skills_per_call = max_skills_per_call

    def run(self, *, context: SkillContext, llm_client: Any) -> SkillRunBundle:
        trace_id = uuid.uuid4().hex
        candidates = self.registry.list_available(context.round_type, context.stage)
        selected = select_skills(
            context=context,
            candidates=candidates,
            llm_client=llm_client,
            max_skills=self.max_skills_per_call,
        )
        calls: list[SkillCallTrace] = []
        summary = input_summary(context)
        for item in selected:
            definition = self.registry.get(item.name)
            if definition is None:
                continue
            start = time.perf_counter()
            try:
                result = definition.runner(context)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                calls.append(
                    SkillCallTrace(
                        trace_id=trace_id,
                        skill_name=definition.name,
                        round_type=context.round_type,
                        stage=context.stage,
                        selection_source=item.source,
                        selection_reason=item.reason,
                        input_summary=summary,
                        output_summary=output_summary(
                            signals=result.signals,
                            suggestions=result.suggestions,
                            confidence=result.confidence,
                            metrics=result.metrics,
                        ),
                        structured_signals=[
                            {
                                "code": signal.code,
                                "severity": signal.severity,
                                "evidence": signal.evidence,
                            }
                            for signal in result.signals
                        ],
                        confidence=result.confidence,
                        llm_enhanced=result.llm_enhanced,
                        elapsed_ms=elapsed_ms,
                        result=result,
                    )
                )
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                calls.append(
                    SkillCallTrace(
                        trace_id=trace_id,
                        skill_name=definition.name,
                        round_type=context.round_type,
                        stage=context.stage,
                        selection_source=item.source,
                        selection_reason=item.reason,
                        input_summary=summary,
                        output_summary={},
                        structured_signals=[],
                        confidence=None,
                        llm_enhanced=definition.llm_enhanced,
                        elapsed_ms=elapsed_ms,
                        error_message=safe_error_code(exc),
                    )
                )
        return SkillRunBundle(trace_id=trace_id, selected=selected, calls=calls)


DEFAULT_SKILL_RUNNER = SkillRunner()
