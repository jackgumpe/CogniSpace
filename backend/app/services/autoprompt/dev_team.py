from __future__ import annotations

from datetime import UTC, datetime
from itertools import cycle
from statistics import fmean
from uuid import uuid4

from app.models.dev_team import (
    AgentProfile,
    BenchmarkDevTeamRequest,
    BenchmarkRoundResult,
    CreateDevTeamPreplanRequest,
    CreateDevTeamPlanRequest,
    DevTeamBenchmarkResponse,
    DevTeamPreplanResponse,
    DevTeamBenchmarkSummary,
    DevTeamPlanResponse,
    GlobalProtocolDirectives,
    KanbanCard,
    MetaAutopromptTemplate,
    TeamPolicy,
)
from app.services.autoprompt.global_tags import GlobalTagProtocol
from app.services.autoprompt.preplanning_agent import PreplanningAgent


class DevTeamOrchestrator:
    """Deterministic 1+6 team planner and benchmark simulator."""

    _DEFAULT_PROCESS_TASK_KEY = "default_development_process"
    _DEFAULT_PROCESS_DESCRIPTION = (
        "Default engineering process controller. "
        "All implementation work starts with 1 supervisor, 2 leads, and 4 developers "
        "using Kanban workflow, healthy debate, and final authority by leads/supervisor."
    )

    _DEFAULT_DEV_SPECIALTIES = [
        "backend_implementation",
        "frontend_integration",
        "qa_validation",
        "ops_observability",
    ]

    def __init__(
        self,
        tag_protocol: GlobalTagProtocol | None = None,
        preplanning_agent: PreplanningAgent | None = None,
    ) -> None:
        self._tag_protocol = tag_protocol or GlobalTagProtocol()
        self._preplanning_agent = preplanning_agent or PreplanningAgent()

    def create_plan(self, request: CreateDevTeamPlanRequest) -> DevTeamPlanResponse:
        team_id = f"team_{uuid4().hex[:12]}"
        session_id = request.session_id or f"sess_team_{uuid4().hex[:10]}"
        trace_id = request.trace_id or f"trace_team_{uuid4().hex[:10]}"
        focus = self._extract_focus_labels(request.task_key, request.task_description)
        directives = self._tag_protocol.parse(request.task_description)
        effective_mode = directives.debate_mode_override or request.debate_mode

        policy = TeamPolicy(
            debate_mode=effective_mode,
            culture_rules=[
                "Plan collaboratively in weekly Kanban cadence.",
                "Healthy disagreement is mandatory when risk or ambiguity exists.",
                "Decisions are democratic by default; unresolved conflicts escalate to leads and supervisor.",
                "Supervisor or leads issue final decision for blocked or split votes.",
            ]
            + self._culture_rules_from_directives(directives),
        )
        meta_template = self._build_meta_template()
        agents = self._build_agents(
            focus=focus,
            providers=request.preferred_providers,
            include_internal_dialogue=request.include_internal_dialogue,
            meta_template=meta_template,
            agents_required=directives.agents_required,
        )
        kanban_cards = self._build_kanban_cards(
            sprint_slots=request.sprint_slots,
            task_key=request.task_key,
            agents=agents,
            focus=focus,
            directives=directives,
        )

        planning_notes = [
            f"Focus areas selected: {', '.join(focus)}.",
            "Role assignment is dynamic and can rotate per card while preserving authority hierarchy.",
            "All cards include acceptance checks to support measurable debate resolution.",
            "Meta-autoprompt loop is attached to every agent reply as internal dialogue.",
            f"Global directives resolved: severity={directives.severity}, agents_required={directives.agents_required}.",
        ]
        planning_notes.extend(directives.parse_warnings)

        return DevTeamPlanResponse(
            team_id=team_id,
            task_key=request.task_key,
            session_id=session_id,
            trace_id=trace_id,
            policy=policy,
            agents=agents,
            kanban_cards=kanban_cards,
            protocol_directives=directives,
            planning_notes=planning_notes,
            meta_autoprompt_template=meta_template,
        )

    def benchmark(self, request: BenchmarkDevTeamRequest) -> DevTeamBenchmarkResponse:
        plan = self.create_plan(
            CreateDevTeamPlanRequest(
                task_key=request.task_key,
                task_description=request.task_description,
                preferred_providers=request.preferred_providers,
                debate_mode=request.debate_mode,
                include_internal_dialogue=request.include_internal_dialogue,
                sprint_slots=8,
                session_id=request.session_id,
                trace_id=request.trace_id,
            )
        )
        benchmark_id = f"bench_{uuid4().hex[:12]}"

        rounds: list[BenchmarkRoundResult] = []
        transcript: list[dict] = []
        for idx in range(1, request.rounds + 1):
            baseline_tokens = self._baseline_token_estimate(request.task_description)
            baseline_score = self._baseline_score(
                task_key=request.task_key,
                task_description=request.task_description,
                round_index=idx,
            )
            directives = plan.protocol_directives
            debate_cycles = max(
                directives.min_debate_cycles,
                self._debate_cycles(mode=plan.policy.debate_mode, round_index=idx),
            )
            conflicts = 1 if idx % 3 == 0 else 0
            if directives.severity == "CRITICAL" and idx % 2 == 0:
                conflicts = max(conflicts, 1)
            team_tokens = self._team_token_estimate(
                baseline_tokens=baseline_tokens,
                agent_count=len(plan.agents),
                debate_cycles=debate_cycles,
                include_internal_dialogue=request.include_internal_dialogue,
                directives=directives,
            )
            final_decider = "SUPERVISOR" if conflicts > 0 else "LEAD"
            team_score = self._team_score(
                baseline_score=baseline_score,
                debate_cycles=debate_cycles,
                include_internal_dialogue=request.include_internal_dialogue,
                conflicts=conflicts,
                token_overhead=max(0, team_tokens - baseline_tokens),
                directives=directives,
            )

            round_result = BenchmarkRoundResult(
                round_index=idx,
                baseline_quality_score=baseline_score,
                team_quality_score=team_score,
                score_delta=round(team_score - baseline_score, 6),
                baseline_token_estimate=baseline_tokens,
                team_token_estimate=team_tokens,
                token_overhead=max(0, team_tokens - baseline_tokens),
                debate_cycles=debate_cycles,
                conflicts_resolved=conflicts,
                final_decider=final_decider,
            )
            rounds.append(round_result)

            if request.include_round_transcript:
                transcript.extend(
                    self._build_round_transcript(
                        plan=plan,
                        round_result=round_result,
                        include_internal_dialogue=request.include_internal_dialogue,
                    )
                )

        summary = self._build_summary(rounds)
        return DevTeamBenchmarkResponse(
            benchmark_id=benchmark_id,
            team_id=plan.team_id,
            session_id=plan.session_id,
            trace_id=plan.trace_id,
            protocol_directives=plan.protocol_directives,
            rounds=rounds,
            summary=summary,
            round_transcript=transcript,
            created_at=datetime.now(UTC),
        )

    def resolve_directives(self, text: str) -> GlobalProtocolDirectives:
        return self._tag_protocol.parse(text)

    def preplan(self, request: CreateDevTeamPreplanRequest) -> DevTeamPreplanResponse:
        directives = self._tag_protocol.parse(request.task_description)
        return self._preplanning_agent.build(request=request, directives=directives)

    def gather_default_team(
        self,
        *,
        task_description: str | None = None,
        preferred_providers: list[str] | None = None,
        include_internal_dialogue: bool = True,
    ) -> dict:
        plan = self.create_plan(
            CreateDevTeamPlanRequest(
                task_key=self._DEFAULT_PROCESS_TASK_KEY,
                task_description=task_description or self._DEFAULT_PROCESS_DESCRIPTION,
                preferred_providers=preferred_providers or ["GEMINI", "CLAUDE", "CODEX"],
                debate_mode="MIXED",
                include_internal_dialogue=include_internal_dialogue,
                sprint_slots=8,
            )
        )
        checks = self._validate_default_process(plan)
        failed = [row["check"] for row in checks if not row["passed"]]
        return {
            "default_process_active": len(failed) == 0,
            "team_id": plan.team_id,
            "task_key": plan.task_key,
            "policy": plan.policy.model_dump(mode="json"),
            "role_counts": {
                "SUPERVISOR": sum(1 for agent in plan.agents if agent.base_role == "SUPERVISOR"),
                "LEAD": sum(1 for agent in plan.agents if agent.base_role == "LEAD"),
                "DEV": sum(1 for agent in plan.agents if agent.base_role == "DEV"),
            },
            "agent_count": len(plan.agents),
            "validation": checks,
            "errors": failed,
            "plan": plan.model_dump(mode="json"),
        }

    def _validate_default_process(self, plan: DevTeamPlanResponse) -> list[dict]:
        role_counts = {
            "SUPERVISOR": sum(1 for agent in plan.agents if agent.base_role == "SUPERVISOR"),
            "LEAD": sum(1 for agent in plan.agents if agent.base_role == "LEAD"),
            "DEV": sum(1 for agent in plan.agents if agent.base_role == "DEV"),
        }
        checks = [
            {
                "check": "team_shape_1_2_4",
                "passed": role_counts == {"SUPERVISOR": 1, "LEAD": 2, "DEV": 4},
                "details": f"role_counts={role_counts}",
            },
            {
                "check": "workflow_is_kanban",
                "passed": plan.policy.workflow == "KANBAN",
                "details": f"workflow={plan.policy.workflow}",
            },
            {
                "check": "decision_mode_enforced",
                "passed": plan.policy.decision_mode == "DEMOCRATIC_WITH_ESCALATION",
                "details": f"decision_mode={plan.policy.decision_mode}",
            },
            {
                "check": "final_authority_contains_supervisor_and_lead",
                "passed": {"SUPERVISOR", "LEAD"}.issubset(set(plan.policy.final_authority)),
                "details": f"final_authority={plan.policy.final_authority}",
            },
            {
                "check": "kanban_cards_present",
                "passed": len(plan.kanban_cards) >= 8,
                "details": f"kanban_cards={len(plan.kanban_cards)}",
            },
        ]
        return checks

    @staticmethod
    def _extract_focus_labels(task_key: str, task_description: str) -> list[str]:
        text = f"{task_key} {task_description}".lower()
        labels: list[str] = []
        if any(token in text for token in ("api", "backend", "fastapi")):
            labels.append("backend")
        if any(token in text for token in ("ui", "frontend", "react", "electron")):
            labels.append("frontend")
        if any(token in text for token in ("log", "observability", "trace")):
            labels.append("observability")
        if any(token in text for token in ("security", "guard", "safety", "drift")):
            labels.append("safety")
        if any(token in text for token in ("test", "quality", "benchmark", "stress")):
            labels.append("quality")
        if any(token in text for token in ("schema", "contract", "json")):
            labels.append("contracts")
        if not labels:
            labels = ["backend", "quality", "contracts"]
        return labels[:6]

    @staticmethod
    def _build_meta_template() -> MetaAutopromptTemplate:
        return MetaAutopromptTemplate(
            meta_loop=[
                "INTENT_CHECK: Why did I phrase my proposal this way?",
                "INTERPRETATION_CHECK: What could other agents reasonably mean?",
                "RISK_CHECK: What failure mode would make this decision wrong?",
                "EVIDENCE_CHECK: Which logs/tests/constraints support my claim?",
                "REVISION_STEP: Update proposal to remove ambiguity before final output.",
            ],
            response_format=[
                "hypothesis",
                "evidence",
                "counterargument",
                "decision_proposal",
                "acceptance_checks",
            ],
            anti_drift_rules=[
                "Never drop hard constraints.",
                "Never override security boundaries for speed.",
                "If uncertainty > threshold, escalate to lead/supervisor.",
            ],
        )

    def _build_agents(
        self,
        *,
        focus: list[str],
        providers: list[str],
        include_internal_dialogue: bool,
        meta_template: MetaAutopromptTemplate,
        agents_required: int,
    ) -> list[AgentProfile]:
        provider_cycle = cycle(providers)
        lead_focus = (focus + ["architecture", "delivery"])[:2]
        dev_count = max(4, agents_required - 3)
        dev_focus = (focus[2:] + self._DEFAULT_DEV_SPECIALTIES) * 10
        dev_focus = dev_focus[:dev_count]

        agents: list[AgentProfile] = [
            AgentProfile(
                agent_id="agent_supervisor_1",
                provider=next(provider_cycle),  # type: ignore[arg-type]
                base_role="SUPERVISOR",
                dynamic_role="Project Supervisor",
                authority_rank=3,
                specialties=["program_management", "risk_triage", "arbitration"],
                internal_meta_prompt=self._render_meta_prompt(
                    role="SUPERVISOR",
                    focus="arbitration_and_planning",
                    include_internal_dialogue=include_internal_dialogue,
                    meta_template=meta_template,
                ),
            ),
            AgentProfile(
                agent_id="agent_lead_1",
                provider=next(provider_cycle),  # type: ignore[arg-type]
                base_role="LEAD",
                dynamic_role=f"Lead {lead_focus[0].title()}",
                authority_rank=2,
                specialties=[lead_focus[0], "architecture", "scope_control"],
                internal_meta_prompt=self._render_meta_prompt(
                    role="LEAD",
                    focus=lead_focus[0],
                    include_internal_dialogue=include_internal_dialogue,
                    meta_template=meta_template,
                ),
            ),
            AgentProfile(
                agent_id="agent_lead_2",
                provider=next(provider_cycle),  # type: ignore[arg-type]
                base_role="LEAD",
                dynamic_role=f"Lead {lead_focus[1].title()}",
                authority_rank=2,
                specialties=[lead_focus[1], "delivery", "quality_gates"],
                internal_meta_prompt=self._render_meta_prompt(
                    role="LEAD",
                    focus=lead_focus[1],
                    include_internal_dialogue=include_internal_dialogue,
                    meta_template=meta_template,
                ),
            ),
        ]

        for idx in range(dev_count):
            specialty = dev_focus[idx] if idx < len(dev_focus) else self._DEFAULT_DEV_SPECIALTIES[idx]
            agents.append(
                AgentProfile(
                    agent_id=f"agent_dev_{idx + 1}",
                    provider=next(provider_cycle),  # type: ignore[arg-type]
                    base_role="DEV",
                    dynamic_role=f"Developer {specialty.title().replace('_', ' ')}",
                    authority_rank=1,
                    specialties=[specialty, "implementation"],
                    internal_meta_prompt=self._render_meta_prompt(
                        role="DEV",
                        focus=specialty,
                        include_internal_dialogue=include_internal_dialogue,
                        meta_template=meta_template,
                    ),
                )
            )
        return agents

    @staticmethod
    def _render_meta_prompt(
        *,
        role: str,
        focus: str,
        include_internal_dialogue: bool,
        meta_template: MetaAutopromptTemplate,
    ) -> str:
        if not include_internal_dialogue:
            return (
                f"Role={role}; Focus={focus}; Output concise proposal + acceptance checks. "
                "Escalate unresolved conflict to lead/supervisor."
            )
        loop = " | ".join(meta_template.meta_loop)
        response_shape = ", ".join(meta_template.response_format)
        return (
            f"Role={role}; Focus={focus}. Internal Meta Loop: {loop}. "
            f"Reply format keys: {response_shape}. "
            "Before final answer, run revision step and explicitly state unresolved risk."
        )

    @staticmethod
    def _build_kanban_cards(
        *,
        sprint_slots: int,
        task_key: str,
        agents: list[AgentProfile],
        focus: list[str],
        directives: GlobalProtocolDirectives,
    ) -> list[KanbanCard]:
        lead_ids = [agent.agent_id for agent in agents if agent.base_role == "LEAD"]
        dev_ids = [agent.agent_id for agent in agents if agent.base_role == "DEV"]
        supervisor_id = next(agent.agent_id for agent in agents if agent.base_role == "SUPERVISOR")

        templates = [
            ("scope_alignment", "Align scope and hard constraints", supervisor_id, True),
            ("system_design", "Propose architecture and interfaces", lead_ids[0], True),
            ("contract_checks", "Define and validate schema contracts", lead_ids[1], True),
            ("impl_slice_1", "Implement first vertical slice", dev_ids[0], False),
            ("impl_slice_2", "Implement second vertical slice", dev_ids[1], False),
            ("quality_suite", "Add tests and failure probes", dev_ids[2], True),
            ("observability", "Add replay logs and metrics", dev_ids[3], False),
            ("release_gate", "Run gate checklist and finalize release decision", supervisor_id, True),
        ]
        if directives.cautious_mode:
            templates.append(
                ("risk_review", "Perform cautious risk review and rollback rehearsal", supervisor_id, True)
            )
        if directives.context_handoff_required:
            templates.append(
                ("handoff_packet", "Build and validate context handoff packet", lead_ids[0], True)
            )

        mandatory_extra = int(directives.cautious_mode) + int(directives.context_handoff_required)
        effective_slots = max(sprint_slots, 8 + mandatory_extra)
        cards: list[KanbanCard] = []
        for idx in range(min(effective_slots, len(templates))):
            key, title, owner, debate_required = templates[idx]
            cards.append(
                KanbanCard(
                    card_id=f"card_{idx + 1:02d}_{key}",
                    title=title,
                    objective=f"{task_key}: {title} with measurable completion checks.",
                    owner_agent_id=owner,
                    column="TODO",
                    acceptance_checks=[
                        "Output includes explicit constraints.",
                        "Evidence links to tests or logs.",
                        f"Focus alignment: {', '.join(focus[:3])}",
                        f"Protocol severity respected: {directives.severity}",
                    ],
                    debate_required=debate_required,
                )
            )
        return cards

    @staticmethod
    def _baseline_token_estimate(task_description: str) -> int:
        words = len(task_description.split())
        return max(160, words + 140)

    @staticmethod
    def _team_token_estimate(
        *,
        baseline_tokens: int,
        agent_count: int,
        debate_cycles: int,
        include_internal_dialogue: bool,
        directives: GlobalProtocolDirectives,
    ) -> int:
        meta_cost = 80 if include_internal_dialogue else 20
        directive_cost = 0
        if directives.cautious_mode:
            directive_cost += 40
        if directives.context_handoff_required:
            directive_cost += 35
        if directives.required_utilities:
            directive_cost += min(120, 10 * len(directives.required_utilities))
        return baseline_tokens + (agent_count * 70) + (debate_cycles * 40) + meta_cost + directive_cost

    @staticmethod
    def _debate_cycles(*, mode: str, round_index: int) -> int:
        if mode == "ASYNC":
            return 1 + (1 if round_index % 4 == 0 else 0)
        if mode == "SYNC":
            return 2 + (1 if round_index % 3 == 0 else 0)
        return 2 + (1 if round_index % 2 == 0 else 0)

    @staticmethod
    def _baseline_score(*, task_key: str, task_description: str, round_index: int) -> float:
        text = f"{task_key} {task_description}".lower()
        score = 0.36
        for token, gain in (
            ("api", 0.07),
            ("schema", 0.05),
            ("test", 0.08),
            ("logging", 0.07),
            ("security", 0.06),
            ("prompt", 0.05),
            ("context", 0.04),
        ):
            if token in text:
                score += gain
        score += min(len(text.split()) / 500.0, 0.1)
        score += ((round_index % 4) - 1.5) * 0.005
        return round(max(0.0, min(score, 0.88)), 6)

    @staticmethod
    def _team_score(
        *,
        baseline_score: float,
        debate_cycles: int,
        include_internal_dialogue: bool,
        conflicts: int,
        token_overhead: int,
        directives: GlobalProtocolDirectives,
    ) -> float:
        gain = 0.05
        gain += min(debate_cycles * 0.012, 0.05)
        if include_internal_dialogue:
            gain += 0.04
        if conflicts > 0:
            gain += 0.015
        if directives.cautious_mode:
            gain += 0.01
        if directives.context_handoff_required:
            gain += 0.008
        penalty = min(token_overhead / 60000.0, 0.03)
        score = baseline_score + gain - penalty
        return round(max(0.0, min(score, 0.97)), 6)

    @staticmethod
    def _culture_rules_from_directives(directives: GlobalProtocolDirectives) -> list[str]:
        rules: list[str] = []
        if directives.severity == "CRITICAL":
            rules.append("CRITICAL mode: supervisor approval required before release.")
            rules.append("CRITICAL mode: use synchronous debate and explicit rollback plan.")
        elif directives.severity == "CAUTIOUS":
            rules.append("CAUTIOUS mode: require risk review before moving cards to REVIEW.")
        if directives.context_handoff_required:
            rules.append("Context handoff packet is mandatory before DONE.")
        if directives.required_utilities:
            utility_text = ", ".join(directives.required_utilities)
            rules.append(f"Required utilities: {utility_text}.")
        return rules

    @staticmethod
    def _build_summary(rounds: list[BenchmarkRoundResult]) -> DevTeamBenchmarkSummary:
        baseline_avg = fmean(row.baseline_quality_score for row in rounds)
        team_avg = fmean(row.team_quality_score for row in rounds)
        avg_delta = team_avg - baseline_avg
        baseline_tokens_avg = fmean(row.baseline_token_estimate for row in rounds)
        team_tokens_avg = fmean(row.team_token_estimate for row in rounds)
        baseline_score_per_1k = baseline_avg / max(baseline_tokens_avg / 1000.0, 0.001)
        team_score_per_1k = team_avg / max(team_tokens_avg / 1000.0, 0.001)
        rounds_with_conflict = sum(1 for row in rounds if row.conflicts_resolved > 0)
        authority_enforced = all(row.final_decider in {"LEAD", "SUPERVISOR"} for row in rounds)

        return DevTeamBenchmarkSummary(
            baseline_avg_score=round(baseline_avg, 6),
            team_avg_score=round(team_avg, 6),
            avg_score_delta=round(avg_delta, 6),
            relative_gain_pct=round((avg_delta / max(baseline_avg, 0.001)) * 100.0, 4),
            avg_token_overhead=round(fmean(row.token_overhead for row in rounds), 4),
            score_per_1k_tokens_baseline=round(baseline_score_per_1k, 6),
            score_per_1k_tokens_team=round(team_score_per_1k, 6),
            decision_authority_enforced=authority_enforced,
            rounds_with_conflict=rounds_with_conflict,
        )

    @staticmethod
    def _build_round_transcript(
        *,
        plan: DevTeamPlanResponse,
        round_result: BenchmarkRoundResult,
        include_internal_dialogue: bool,
    ) -> list[dict]:
        transcript: list[dict] = []
        for agent in plan.agents:
            snippet = {
                "round_index": round_result.round_index,
                "agent_id": agent.agent_id,
                "base_role": agent.base_role,
                "dynamic_role": agent.dynamic_role,
                "message": (
                    f"Proposal for round {round_result.round_index}: "
                    f"advance card using {agent.specialties[0]} evidence."
                ),
            }
            if include_internal_dialogue:
                snippet["internal_dialogue"] = (
                    "Intent check complete; interpretation reviewed; risk updated; "
                    "proposal revised before vote."
                )
            transcript.append(snippet)

        transcript.append(
            {
                "round_index": round_result.round_index,
                "decision": f"Final decision by {round_result.final_decider}",
                "debate_cycles": round_result.debate_cycles,
                "conflicts_resolved": round_result.conflicts_resolved,
            }
        )
        return transcript
