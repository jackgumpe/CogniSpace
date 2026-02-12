from __future__ import annotations

from uuid import uuid4

from app.models.dev_team import (
    ContextHandoffPacket,
    CreateDevTeamPreplanRequest,
    DevTeamPreplanResponse,
    GlobalProtocolDirectives,
    PreplanningCard,
    PreplanningRisk,
)


class PreplanningAgent:
    """Builds a forward-looking implementation preplan for the dev team."""

    AGENT_ID = "agent_preplanner_1"

    _TRACK_KEYWORDS = (
        ("backend", ("api", "backend", "fastapi", "worker", "gateway")),
        ("frontend", ("frontend", "react", "electron", "ui")),
        ("contracts", ("schema", "contract", "json", "validation")),
        ("observability", ("log", "telemetry", "metrics", "trace", "replay")),
        ("context_handoff", ("context", "handoff", "window", "resume", "continuity")),
        ("quality", ("test", "quality", "stress", "benchmark")),
        ("security", ("security", "safety", "guard", "malicious", "redact")),
        ("dataset", ("dataset", "jsonic", "training", "export")),
    )

    def build(
        self,
        request: CreateDevTeamPreplanRequest,
        *,
        directives: GlobalProtocolDirectives,
    ) -> DevTeamPreplanResponse:
        focus_tracks = self._focus_tracks(request.task_key, request.task_description)
        horizon_cards = self._horizon_cards(
            task_key=request.task_key,
            focus_tracks=focus_tracks,
            directives=directives,
            horizon_cards=request.horizon_cards,
        )
        risk_matrix = self._risk_matrix(
            include_risk_matrix=request.include_risk_matrix,
            directives=directives,
            focus_tracks=focus_tracks,
        )
        checkpoints = self._phase_checkpoints(directives=directives, focus_tracks=focus_tracks)

        session_id = request.session_id or f"sess_preplan_{uuid4().hex[:10]}"
        trace_id = request.trace_id or f"trace_preplan_{uuid4().hex[:10]}"

        return DevTeamPreplanResponse(
            preplan_id=f"preplan_{uuid4().hex[:12]}",
            agent_id=self.AGENT_ID,
            task_key=request.task_key,
            session_id=session_id,
            trace_id=trace_id,
            focus_tracks=focus_tracks,
            protocol_directives=directives,
            horizon_cards=horizon_cards,
            risk_matrix=risk_matrix,
            phase_checkpoints=checkpoints,
            context_handoff_packet=self._context_handoff_packet(directives=directives),
        )

    def _focus_tracks(self, task_key: str, task_description: str) -> list[str]:
        text = f"{task_key} {task_description}".lower()
        tracks: list[str] = []
        for name, tokens in self._TRACK_KEYWORDS:
            if any(token in text for token in tokens):
                tracks.append(name)
        if not tracks:
            tracks = ["backend", "contracts", "quality"]
        return tracks[:6]

    @staticmethod
    def _horizon_cards(
        *,
        task_key: str,
        focus_tracks: list[str],
        directives: GlobalProtocolDirectives,
        horizon_cards: int,
    ) -> list[PreplanningCard]:
        templates: list[tuple[str, str, str, str, list[str], list[str]]] = [
            (
                "scope_baseline",
                "Lock hard constraints and non-negotiables",
                "SUPERVISOR",
                "P0",
                [],
                ["Hard scope is explicit and testable", "Out-of-scope list is complete"],
            ),
            (
                "contracts_first",
                "Freeze API and schema contracts before feature expansion",
                "LEAD",
                "P0",
                ["scope_baseline"],
                ["Schema validation passes for event + autoprompt contracts"],
            ),
            (
                "logging_plane",
                "Strengthen replayable logging and raw-data controls",
                "DEV",
                "P0",
                ["contracts_first"],
                ["Replay API remains ordered/gap-free/deterministic"],
            ),
            (
                "autoprompt_quality",
                "Tune critic/candidate/evaluator loop with clear budgets",
                "LEAD",
                "P1",
                ["contracts_first"],
                ["Budget caps trigger predictable termination reasons"],
            ),
            (
                "context_transition",
                "Define context handoff packet and resume protocol",
                "DEV",
                "P1",
                ["logging_plane"],
                ["Next-window continuation packet validates against schema"],
            ),
            (
                "stress_probes",
                "Run stress probes for silent failures and telemetry drift",
                "DEV",
                "P1",
                ["logging_plane", "autoprompt_quality"],
                ["Stress suite reports zero silent failures"],
            ),
            (
                "release_gate",
                "Execute gate checklist and authorize next phase",
                "SUPERVISOR",
                "P0",
                ["stress_probes"],
                ["Gate checklist has evidence-backed PASS/FAIL"],
            ),
        ]

        if directives.cautious_mode:
            templates.append(
                (
                    "rollback_drill",
                    "Run rollback and recovery rehearsal",
                    "LEAD",
                    "P0",
                    ["stress_probes"],
                    ["Rollback drill reaches clean recovery state"],
                )
            )
        if directives.context_handoff_required:
            templates.append(
                (
                    "handoff_validation",
                    "Validate context transfer across window boundaries",
                    "DEV",
                    "P0",
                    ["context_transition"],
                    ["Transfer packet includes replay anchor and decision state"],
                )
            )

        cards: list[PreplanningCard] = []
        for index, (card_key, title, role, priority, deps, checks) in enumerate(templates[:horizon_cards], start=1):
            track_hint = focus_tracks[min(index - 1, len(focus_tracks) - 1)]
            cards.append(
                PreplanningCard(
                    card_id=f"pre_{index:02d}_{card_key}",
                    title=title,
                    objective=f"{task_key}: {title} [{track_hint}]",
                    owner_role=role,  # type: ignore[arg-type]
                    priority=priority,  # type: ignore[arg-type]
                    rationale=(
                        f"Prioritize {track_hint} to reduce integration risk before implementation spread."
                    ),
                    dependencies=deps,
                    acceptance_checks=checks
                    + [
                        f"Protocol severity acknowledged: {directives.severity}",
                    ],
                )
            )
        return cards

    @staticmethod
    def _risk_matrix(
        *,
        include_risk_matrix: bool,
        directives: GlobalProtocolDirectives,
        focus_tracks: list[str],
    ) -> list[PreplanningRisk]:
        if not include_risk_matrix:
            return []

        severity = "CRITICAL" if directives.severity == "CRITICAL" else "CAUTIOUS"
        context_risk_prob = "HIGH" if "context_handoff" in focus_tracks else "MEDIUM"
        items = [
            PreplanningRisk(
                risk_id="risk_context_drift",
                severity=severity,  # type: ignore[arg-type]
                probability=context_risk_prob,  # type: ignore[arg-type]
                description="Context packet misses key decision history across window transitions.",
                mitigation="Require replay anchor + decision digest + unresolved risks in every handoff packet.",
                trigger_signal="handoff packet missing required fields or replay anchor not found",
            ),
            PreplanningRisk(
                risk_id="risk_silent_failures",
                severity="CAUTIOUS",
                probability="MEDIUM",
                description="Background failures do not surface in logs or quality reports.",
                mitigation="Add explicit failure probes and verify non-zero anomaly counts under fault injection.",
                trigger_signal="stress run completes with contradictory metrics and no error events",
            ),
            PreplanningRisk(
                risk_id="risk_budget_regression",
                severity="CAUTIOUS",
                probability="MEDIUM",
                description="Autoprompt runs exceed cost/token/time budgets under load.",
                mitigation="Enforce hard stop checks per iteration and test all termination reasons.",
                trigger_signal="budget usage exceeds thresholds without FAILED/STOPPED status",
            ),
        ]
        return items

    @staticmethod
    def _phase_checkpoints(
        *,
        directives: GlobalProtocolDirectives,
        focus_tracks: list[str],
    ) -> list[str]:
        checkpoints = [
            "Checkpoint A: contracts and event schemas frozen with validator evidence.",
            "Checkpoint B: replay logging verified for deterministic paging and since-event anchors.",
            "Checkpoint C: autoprompt budgets validated under fault and stress probes.",
            "Checkpoint D: context transition packet validated for next-window continuity.",
            "Checkpoint E: release gate decision logged with explicit PASS/FAIL evidence.",
        ]
        if directives.severity == "CRITICAL":
            checkpoints.append("Checkpoint F: supervisor approval recorded before deployment.")
        if "frontend" in focus_tracks:
            checkpoints.append("Checkpoint UI: history viewer reads replay endpoints without data-loss.")
        return checkpoints

    @staticmethod
    def _context_handoff_packet(*, directives: GlobalProtocolDirectives) -> ContextHandoffPacket:
        base_fields = [
            "session_id",
            "trace_id",
            "replay_anchor_event_id",
            "decision_digest",
            "active_kanban_cards",
            "open_risks",
            "next_actions",
        ]
        if directives.required_utilities:
            base_fields.append("required_utilities")
        return ContextHandoffPacket(
            summary_template=(
                "Summarize completed decisions, unresolved risks, active cards, and exact replay anchor."
            ),
            required_fields=base_fields,
            replay_anchor_policy="Anchor must reference an existing event_id in deterministic replay stream.",
            continuity_checks=[
                "Handoff includes unresolved blockers and owner roles.",
                "Next action list references concrete card ids.",
                "Decision digest includes final authority actor.",
            ],
        )
