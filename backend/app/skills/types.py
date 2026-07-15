from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

JSONDict = dict[str, Any]
RoundType = Literal["resume", "technical", "manager", "hr"]
SkillStage = Literal["pre_question", "post_answer"]


@dataclass(frozen=True)
class SkillContext:
    user_id: int
    interview_id: int
    round_id: int
    round_type: str
    stage: SkillStage
    target_position: str
    job_description: str
    resume: JSONDict
    qa_history: list[JSONDict]
    previous_answer: str | None
    question_kind: str
    effective_memories: list[JSONDict] = field(default_factory=list)
    interview_strategy: JSONDict = field(default_factory=dict)


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    category: Literal["common", "specialized"]
    available_rounds: tuple[str, ...]
    stages: tuple[SkillStage, ...]
    llm_enhanced: bool
    runner: Callable[[SkillContext], SkillResult]


@dataclass(frozen=True)
class SkillSignal:
    code: str
    severity: Literal["info", "warning", "risk"]
    evidence: JSONDict = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSuggestion:
    code: str
    target: str
    priority: Literal["low", "medium", "high"] = "medium"
    evidence: JSONDict = field(default_factory=dict)


@dataclass(frozen=True)
class SkillResult:
    skill_name: str
    summary: str
    signals: list[SkillSignal]
    metrics: JSONDict
    suggestions: list[SkillSuggestion]
    confidence: float
    llm_enhanced: bool = False

    def model_dump(self) -> JSONDict:
        return {
            "skill_name": self.skill_name,
            "summary": self.summary,
            "signals": [
                {
                    "code": signal.code,
                    "severity": signal.severity,
                    "evidence": signal.evidence,
                }
                for signal in self.signals
            ],
            "metrics": self.metrics,
            "suggestions": [
                {
                    "code": suggestion.code,
                    "target": suggestion.target,
                    "priority": suggestion.priority,
                    "evidence": suggestion.evidence,
                }
                for suggestion in self.suggestions
            ],
            "confidence": self.confidence,
            "llm_enhanced": self.llm_enhanced,
        }


@dataclass(frozen=True)
class SkillSelection:
    name: str
    reason: str
    source: Literal["llm", "rule"]


@dataclass(frozen=True)
class SkillCallTrace:
    trace_id: str
    skill_name: str
    round_type: str
    stage: SkillStage
    selection_source: str
    selection_reason: str
    input_summary: JSONDict
    output_summary: JSONDict
    structured_signals: list[JSONDict]
    confidence: float | None
    llm_enhanced: bool
    elapsed_ms: int
    error_message: str | None = None
    result: SkillResult | None = None


@dataclass(frozen=True)
class SkillRunBundle:
    trace_id: str
    selected: list[SkillSelection]
    calls: list[SkillCallTrace]

    def agent_context(self) -> JSONDict:
        successful_calls = [call for call in self.calls if call.result is not None]
        return {
            "trace_id": self.trace_id,
            "selected_skills": [
                {
                    "name": item.name,
                    "reason": item.reason,
                    "source": item.source,
                }
                for item in self.selected
            ],
            "results": [_agent_result_payload(call) for call in successful_calls],
            "failed_skills": [
                {
                    "skill_name": call.skill_name,
                    "error": call.error_message,
                }
                for call in self.calls
                if call.error_message
            ],
        }


def _agent_result_payload(call: SkillCallTrace) -> JSONDict:
    result = call.result
    if result is None:
        return {}
    return {
        "skill_name": call.skill_name,
        "summary": result.summary,
        "output_summary": call.output_summary,
        "signals": call.structured_signals,
        "metrics": result.metrics,
        "suggestions": [
            {
                "code": suggestion.code,
                "target": suggestion.target,
                "priority": suggestion.priority,
                "evidence": suggestion.evidence,
            }
            for suggestion in result.suggestions[:5]
        ],
        "confidence": call.confidence,
        "llm_enhanced": call.llm_enhanced,
    }
