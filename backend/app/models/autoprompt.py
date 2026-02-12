from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(ge=1, le=100)
    max_tokens: int = Field(ge=1)
    max_cost_usd: float = Field(ge=0.0)
    timeout_seconds: int = Field(ge=1)


class DriftConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_keywords: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    min_similarity: float = Field(default=0.1, ge=0.0, le=1.0)


class AutopromptScoringWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_score: float = Field(default=0.25, ge=0.0, le=1.0)
    json_bonus: float = Field(default=0.2, ge=0.0, le=1.0)
    must_bonus: float = Field(default=0.15, ge=0.0, le=1.0)
    length_divisor: int = Field(default=300, ge=1, le=10000)
    length_max_bonus: float = Field(default=0.2, ge=0.0, le=1.0)
    task_relevance_max_bonus: float = Field(default=0.2, ge=0.0, le=1.0)
    keyword_coverage_max_bonus: float = Field(default=0.2, ge=0.0, le=1.0)
    forbidden_pattern_penalty: float = Field(default=0.4, ge=0.0, le=1.0)


class CreateAutopromptRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1)
    baseline_prompt: str = Field(min_length=1)
    budget: BudgetConfig
    constraints: DriftConstraints = Field(default_factory=DriftConstraints)
    session_id: str | None = None
    trace_id: str | None = None


class PromptCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    prompt_version: str
    prompt_text: str
    critique: str
    score: float
    token_used: int
    cost_usd: float
    selected: bool = False
    rejected_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PromptVersionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version: str
    run_id: str
    task_key: str
    prompt_text: str
    score: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BudgetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iterations_used: int = 0
    tokens_used: int = 0
    cost_used_usd: float = 0.0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    timed_out: bool = False


class AutopromptRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_key: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime | None = None
    baseline_prompt_version: str
    best_prompt_version: str | None = None
    budget: BudgetConfig
    metrics: dict[str, Any] = Field(default_factory=dict)

    # Internal/runtime fields
    session_id: str
    trace_id: str
    baseline_prompt: str
    constraints: DriftConstraints
    candidates: list[PromptCandidate] = Field(default_factory=list)
    best_candidate: PromptCandidate | None = None
    budget_usage: BudgetUsage = Field(default_factory=BudgetUsage)

    def contract_view(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_key": self.task_key,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "baseline_prompt_version": self.baseline_prompt_version,
            "best_prompt_version": self.best_prompt_version,
            "budget": self.budget.model_dump(mode="json"),
            "metrics": self.metrics,
        }


class CreateRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: RunStatus
    baseline_prompt_version: str


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_key: str
    status: RunStatus
    baseline_prompt_version: str
    best_prompt_version: str | None
    best_candidate: PromptCandidate | None
    metrics: dict[str, Any]
    budget_usage: BudgetUsage


class DeployPromptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str
    prompt_version: str
    already_active: bool
