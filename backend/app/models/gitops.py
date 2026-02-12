from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
CollaborationMode = Literal["SOLO", "TEAM"]
GitAdviceAction = Literal["FORK_OR_BRANCH", "COMMIT", "PRUNE", "SYNC", "NOOP"]
GitSnapshotStatus = Literal["OK", "UNAVAILABLE"]


class GitRepoSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GitSnapshotStatus = "OK"
    repo_root: str
    current_branch: str
    remote_name: str | None = None
    remote_url: str | None = None
    is_github_remote: bool = False
    is_detached_head: bool = False
    staged_files: int = Field(default=0, ge=0)
    modified_files: int = Field(default=0, ge=0)
    untracked_files: int = Field(default=0, ge=0)
    total_changed_files: int = Field(default=0, ge=0)
    ahead_count: int = Field(default=0, ge=0)
    behind_count: int = Field(default=0, ge=0)
    stale_local_branches: list[str] = Field(default_factory=list)
    merged_local_branches: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GitAgentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    focus: str
    confidence: float = Field(ge=0.0, le=1.0)
    primary_action: GitAdviceAction
    rationale: str
    commands: list[str] = Field(default_factory=list)


class GitAdviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    changes_summary: str | None = None
    risk_level: RiskLevel = "MEDIUM"
    collaboration_mode: CollaborationMode = "TEAM"
    include_bootstrap_plan: bool = False
    repo_name: str = Field(default="CogniSpace", min_length=1)
    remote_url: str | None = None
    session_id: str | None = None
    trace_id: str | None = None


class GitAdviceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advice_id: str
    objective: str
    repo_snapshot: GitRepoSnapshot
    agent_recommendations: list[GitAgentRecommendation] = Field(default_factory=list)
    consolidated_actions: list[str] = Field(default_factory=list)
    suggested_commit_message: str
    suggested_pr_comment: str
    should_fork: bool = False
    should_prune: bool = False
    bootstrap_commands: list[str] = Field(default_factory=list)
    session_id: str
    trace_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
