from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

JSONDict = dict[str, Any]


class JobFamilyDecision(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=128)
    matched_existing: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        normalized = "-".join(value.strip().lower().replace("_", "-").split())
        allowed = "".join(char for char in normalized if char.isalnum() or char == "-")
        if not allowed:
            raise ValueError("job family key is empty after normalization")
        return allowed[:128]


class EvolutionDiagnosis(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(min_length=1, max_length=20)
    selected_artifact_key: str = Field(min_length=1, max_length=128)
    expected_improvements: list[str] = Field(min_length=1, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)


class PromptArtifactContent(BaseModel):
    text: str = Field(min_length=20, max_length=60000)


class ConfigArtifactContent(BaseModel):
    config: JSONDict


class EvolutionProposal(BaseModel):
    artifact_key: str = Field(min_length=1, max_length=128)
    artifact_type: Literal["prompt", "flow_config", "harness_policy"]
    change_summary: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=3000)
    content: JSONDict


class SyntheticSampleBatch(BaseModel):
    samples: list[JSONDict] = Field(min_length=1, max_length=50)


class JudgeItem(BaseModel):
    sample_key: str = Field(min_length=1, max_length=128)
    winner: Literal["A", "B", "tie"]
    reason: str = Field(min_length=1, max_length=1000)
    quality_a: float = Field(ge=0.0, le=100.0)
    quality_b: float = Field(ge=0.0, le=100.0)


class JudgeBatch(BaseModel):
    comparisons: list[JudgeItem]


class ShadowResult(BaseModel):
    output: JSONDict
    metrics: dict[str, float]
    hard_gate_passed: bool
    hard_gate_errors: list[str] = Field(default_factory=list)
