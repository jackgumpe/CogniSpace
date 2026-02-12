from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["GEMINI", "CLAUDE", "CODEX", "DEEPSEEK"]
BaseRole = Literal["SUPERVISOR", "LEAD", "DEV"]
KanbanColumn = Literal["BACKLOG", "TODO", "IN_PROGRESS", "REVIEW", "DONE"]
DebateMode = Literal["SYNC", "ASYNC", "MIXED"]
DecisionMode = Literal["DEMOCRATIC_WITH_ESCALATION"]
ProtocolSeverity = Literal["NORMAL", "CAUTIOUS", "CRITICAL"]
CardPriority = Literal["P0", "P1", "P2"]


class MetaAutopromptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta_loop: list[str] = Field(default_factory=list)
    response_format: list[str] = Field(default_factory=list)
    anti_drift_rules: list[str] = Field(default_factory=list)


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    provider: Provider
    base_role: BaseRole
    dynamic_role: str
    authority_rank: int = Field(ge=1, le=3)
    specialties: list[str] = Field(default_factory=list)
    internal_meta_prompt: str


class KanbanCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    title: str
    objective: str
    owner_agent_id: str
    column: KanbanColumn
    acceptance_checks: list[str] = Field(default_factory=list)
    debate_required: bool = False


class TeamPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: Literal["KANBAN"] = "KANBAN"
    debate_mode: DebateMode
    decision_mode: DecisionMode = "DEMOCRATIC_WITH_ESCALATION"
    final_authority: list[str] = Field(
        default_factory=lambda: ["SUPERVISOR", "LEAD"],
    )
    culture_rules: list[str] = Field(default_factory=list)


class GlobalProtocolDirectives(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ProtocolSeverity = "NORMAL"
    cautious_mode: bool = False
    agents_required: int = Field(default=7, ge=7, le=20)
    debate_mode_override: DebateMode | None = None
    min_debate_cycles: int = Field(default=1, ge=1, le=8)
    context_handoff_required: bool = False
    requires_supervisor_approval: bool = False
    required_utilities: list[str] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    raw_tags: dict[str, str] = Field(default_factory=dict)


class CreateDevTeamPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1)
    task_description: str = Field(min_length=1)
    preferred_providers: list[Provider] = Field(
        default_factory=lambda: ["GEMINI", "CLAUDE", "CODEX"],
        min_length=1,
        max_length=4,
    )
    debate_mode: DebateMode = "MIXED"
    include_internal_dialogue: bool = True
    sprint_slots: int = Field(default=8, ge=5, le=20)
    session_id: str | None = None
    trace_id: str | None = None


class ResolveGlobalDirectivesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class GatherDefaultTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_description: str | None = None
    preferred_providers: list[Provider] = Field(
        default_factory=lambda: ["GEMINI", "CLAUDE", "CODEX"],
        min_length=1,
        max_length=4,
    )
    include_internal_dialogue: bool = True


class CreateDevTeamPreplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1)
    task_description: str = Field(min_length=1)
    horizon_cards: int = Field(default=6, ge=3, le=20)
    include_risk_matrix: bool = True
    session_id: str | None = None
    trace_id: str | None = None


class DevTeamPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str
    task_key: str
    session_id: str
    trace_id: str
    policy: TeamPolicy
    agents: list[AgentProfile]
    kanban_cards: list[KanbanCard]
    protocol_directives: GlobalProtocolDirectives = Field(default_factory=GlobalProtocolDirectives)
    planning_notes: list[str] = Field(default_factory=list)
    meta_autoprompt_template: MetaAutopromptTemplate
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BenchmarkDevTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1)
    task_description: str = Field(min_length=1)
    rounds: int = Field(default=8, ge=1, le=50)
    debate_mode: DebateMode = "MIXED"
    include_internal_dialogue: bool = True
    include_round_transcript: bool = False
    preferred_providers: list[Provider] = Field(
        default_factory=lambda: ["GEMINI", "CLAUDE", "CODEX"],
        min_length=1,
        max_length=4,
    )
    session_id: str | None = None
    trace_id: str | None = None


class BenchmarkRoundResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_index: int = Field(ge=1)
    baseline_quality_score: float = Field(ge=0.0, le=1.0)
    team_quality_score: float = Field(ge=0.0, le=1.0)
    score_delta: float
    baseline_token_estimate: int = Field(ge=1)
    team_token_estimate: int = Field(ge=1)
    token_overhead: int = Field(ge=0)
    debate_cycles: int = Field(ge=0)
    conflicts_resolved: int = Field(ge=0)
    final_decider: str


class DevTeamBenchmarkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_avg_score: float = Field(ge=0.0, le=1.0)
    team_avg_score: float = Field(ge=0.0, le=1.0)
    avg_score_delta: float
    relative_gain_pct: float
    avg_token_overhead: float
    score_per_1k_tokens_baseline: float
    score_per_1k_tokens_team: float
    decision_authority_enforced: bool
    rounds_with_conflict: int


class DevTeamBenchmarkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    team_id: str
    session_id: str
    trace_id: str
    protocol_directives: GlobalProtocolDirectives = Field(default_factory=GlobalProtocolDirectives)
    rounds: list[BenchmarkRoundResult]
    summary: DevTeamBenchmarkSummary
    round_transcript: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PreplanningCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    title: str
    objective: str
    owner_role: BaseRole
    priority: CardPriority
    rationale: str
    dependencies: list[str] = Field(default_factory=list)
    acceptance_checks: list[str] = Field(default_factory=list)


class PreplanningRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_id: str
    severity: ProtocolSeverity
    probability: Literal["LOW", "MEDIUM", "HIGH"]
    description: str
    mitigation: str
    trigger_signal: str


class ContextHandoffPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_template: str
    required_fields: list[str] = Field(default_factory=list)
    replay_anchor_policy: str
    continuity_checks: list[str] = Field(default_factory=list)


class DevTeamPreplanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preplan_id: str
    agent_id: str
    task_key: str
    session_id: str
    trace_id: str
    focus_tracks: list[str] = Field(default_factory=list)
    protocol_directives: GlobalProtocolDirectives = Field(default_factory=GlobalProtocolDirectives)
    horizon_cards: list[PreplanningCard] = Field(default_factory=list)
    risk_matrix: list[PreplanningRisk] = Field(default_factory=list)
    phase_checkpoints: list[str] = Field(default_factory=list)
    context_handoff_packet: ContextHandoffPacket
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
