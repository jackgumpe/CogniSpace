from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
CollaborationMode = Literal["SOLO", "TEAM"]
GitAdviceAction = Literal["FORK_OR_BRANCH", "COMMIT", "PRUNE", "SYNC", "NOOP"]
GitSnapshotStatus = Literal["OK", "UNAVAILABLE"]
MetaMetricDirection = Literal["HIGHER_IS_BETTER", "LOWER_IS_BETTER", "TARGET_RANGE"]
MetaMetricLayer = Literal["PLAN", "IMPLEMENTATION", "POST_IMPLEMENTATION", "TEAM"]
MetaSquaredMode = Literal["OFF", "PATCH"]
GitExecutionStepStatus = Literal["PLANNED", "SKIPPED", "SUCCEEDED", "FAILED"]
GitHandoffStatus = Literal["DRY_RUN", "SUCCEEDED", "FAILED"]


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
    changed_paths: list[str] = Field(default_factory=list)
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


class GitMetaPlanMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    layer: MetaMetricLayer
    definition: str
    signal_source: str
    cadence: str
    direction: MetaMetricDirection
    warn_threshold: float
    critical_threshold: float


class GitMetaPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    repo_name: str = Field(default="CogniSpace", min_length=1)
    risk_level: RiskLevel = "MEDIUM"
    include_hf_scan: bool = True
    meta_squared_mode: MetaSquaredMode = "PATCH"
    session_id: str | None = None
    trace_id: str | None = None


class GitMetaSquaredThresholdUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    previous_warn_threshold: float
    previous_critical_threshold: float
    proposed_warn_threshold: float
    proposed_critical_threshold: float
    bounded: bool = True
    rationale: str


class GitMetaSquaredAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: MetaSquaredMode = "PATCH"
    enabled: bool = False
    triggered: bool = False
    trigger_reasons: list[str] = Field(default_factory=list)
    metric_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    threshold_fitness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    decision_alignment_score: float = Field(default=0.0, ge=0.0, le=1.0)
    bounded_threshold_updates: list[GitMetaSquaredThresholdUpdate] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class GitMetaPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    objective: str
    repo_snapshot: GitRepoSnapshot
    specialist_team: list[GitAgentRecommendation] = Field(default_factory=list)
    meta_metrics: list[GitMetaPlanMetric] = Field(default_factory=list)
    autoprompt_tracks: list[str] = Field(default_factory=list)
    update_loop: list[str] = Field(default_factory=list)
    fork_policy: list[str] = Field(default_factory=list)
    prune_policy: list[str] = Field(default_factory=list)
    merge_policy: list[str] = Field(default_factory=list)
    baseline_targets: dict[str, float] = Field(default_factory=dict)
    meta_squared: GitMetaSquaredAssessment = Field(default_factory=GitMetaSquaredAssessment)
    session_id: str
    trace_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitBootstrapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo: str | None = None
    resource_group: str | None = None
    location: str = "eastus"
    acr_name: str | None = None
    container_app_environment: str = "cae-cognispace-dev"
    container_app_name: str = "ca-cognispace-backend"
    static_web_app_name: str = "swa-cognispace-frontend"
    database_url: str = "sqlite+pysqlite:////tmp/cognispace.db"


class GitExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    description: str
    command: str | None = None
    status: GitExecutionStepStatus
    return_code: int | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    requires_tool: str | None = None


class GitHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1)
    repo_name: str = Field(default="CogniSpace", min_length=1)
    risk_level: RiskLevel = "HIGH"
    meta_squared_mode: MetaSquaredMode = "PATCH"
    dry_run: bool = True
    run_tests: bool = True
    test_command: str = "python -m pytest tests/test_gitops_api.py tests/test_gitops_mocking.py tests/test_cli.py -q"
    pathspec: list[str] = Field(default_factory=list)
    push_branch: bool = True
    create_pr: bool = False
    include_bootstrap: bool = False
    trigger_workflows: bool = False
    bootstrap: GitBootstrapConfig | None = None
    session_id: str | None = None
    trace_id: str | None = None


class GitHandoffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    objective: str
    status: GitHandoffStatus
    dry_run: bool
    branch_name: str
    pathspec: list[str] = Field(default_factory=list)
    repo_snapshot_before: GitRepoSnapshot
    repo_snapshot_after: GitRepoSnapshot
    meta_plan: GitMetaPlanResponse
    steps: list[GitExecutionStep] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    session_id: str
    trace_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
