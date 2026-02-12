from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request

from app.core.logging import logger
from app.models.dev_team import (
    BenchmarkDevTeamRequest,
    CreateDevTeamPreplanRequest,
    CreateDevTeamPlanRequest,
    DevTeamBenchmarkResponse,
    DevTeamPreplanResponse,
    DevTeamPlanResponse,
    GatherDefaultTeamRequest,
    GlobalProtocolDirectives,
    ResolveGlobalDirectivesRequest,
)
from app.models.events import EventEnvelope
from app.services.autoprompt.dev_team import DevTeamOrchestrator
from app.services.logging.event_store import EventStore

router = APIRouter(prefix="/autoprompt/dev-team", tags=["dev-team"])


def _orchestrator(request: Request) -> DevTeamOrchestrator:
    return request.app.state.dev_team_orchestrator


def _event_store(request: Request) -> EventStore:
    return request.app.state.event_store


async def _safe_emit(request: Request, event_name: str, payload: dict[str, Any]) -> None:
    try:
        await request.app.state.sio.emit(event_name, payload)
    except Exception as exc:  # pragma: no cover - non-blocking and environment dependent
        logger.warning(
            "socket_emit_failed",
            event_name=event_name,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def _event(*, session_id: str, trace_id: str, event_type: str, payload: dict[str, Any]) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"evt_{uuid4().hex[:14]}",
        session_id=session_id,
        trace_id=trace_id,
        timestamp_utc=datetime.now(UTC),
        actor_id="backend",
        actor_role="SYSTEM",
        channel="AUTOPROMPT",
        event_type=event_type,
        payload=payload,
    )


@router.post("/plan", response_model=DevTeamPlanResponse)
async def create_dev_team_plan(
    payload: CreateDevTeamPlanRequest,
    request: Request,
) -> DevTeamPlanResponse:
    plan = _orchestrator(request).create_plan(payload)
    event = _event_store(request).append_event(
        _event(
            session_id=plan.session_id,
            trace_id=plan.trace_id,
            event_type="DEV_TEAM_PLAN_CREATED",
            payload={
                "team_id": plan.team_id,
                "task_key": plan.task_key,
                "agent_count": len(plan.agents),
                "debate_mode": plan.policy.debate_mode,
                "workflow": plan.policy.workflow,
                "protocol_directives": plan.protocol_directives.model_dump(mode="json"),
            },
        )
    )
    await _safe_emit(request, "DEV_TEAM_PLAN", {"team_id": plan.team_id, "task_key": plan.task_key})
    await _safe_emit(request, "LOG_EVENT", event.model_dump(mode="json"))
    return plan


@router.post("/preplan", response_model=DevTeamPreplanResponse)
async def create_dev_team_preplan(
    payload: CreateDevTeamPreplanRequest,
    request: Request,
) -> DevTeamPreplanResponse:
    preplan = _orchestrator(request).preplan(payload)
    event = _event_store(request).append_event(
        _event(
            session_id=preplan.session_id,
            trace_id=preplan.trace_id,
            event_type="DEV_TEAM_PREPLAN_CREATED",
            payload={
                "preplan_id": preplan.preplan_id,
                "task_key": preplan.task_key,
                "agent_id": preplan.agent_id,
                "focus_tracks": preplan.focus_tracks,
                "horizon_card_count": len(preplan.horizon_cards),
                "risk_count": len(preplan.risk_matrix),
                "severity": preplan.protocol_directives.severity,
            },
        )
    )
    await _safe_emit(
        request,
        "DEV_TEAM_PREPLAN",
        {
            "preplan_id": preplan.preplan_id,
            "task_key": preplan.task_key,
            "horizon_card_count": len(preplan.horizon_cards),
        },
    )
    await _safe_emit(request, "LOG_EVENT", event.model_dump(mode="json"))
    return preplan


@router.post("/benchmark", response_model=DevTeamBenchmarkResponse)
async def benchmark_dev_team(
    payload: BenchmarkDevTeamRequest,
    request: Request,
) -> DevTeamBenchmarkResponse:
    result = _orchestrator(request).benchmark(payload)
    event_store = _event_store(request)

    for row in result.rounds:
        round_event = event_store.append_event(
            _event(
                session_id=result.session_id,
                trace_id=result.trace_id,
                event_type="DEV_TEAM_BENCHMARK_ROUND",
                payload={
                    "benchmark_id": result.benchmark_id,
                    "round_index": row.round_index,
                    "baseline_quality_score": row.baseline_quality_score,
                    "team_quality_score": row.team_quality_score,
                    "score_delta": row.score_delta,
                    "token_overhead": row.token_overhead,
                    "final_decider": row.final_decider,
                    "severity": result.protocol_directives.severity,
                },
            )
        )
        await _safe_emit(
            request,
            "DEV_TEAM_BENCHMARK_ROUND",
            {
                "benchmark_id": result.benchmark_id,
                "round_index": row.round_index,
                "score_delta": row.score_delta,
                "token_overhead": row.token_overhead,
            },
        )
        await _safe_emit(request, "LOG_EVENT", round_event.model_dump(mode="json"))

    completed_event = event_store.append_event(
        _event(
            session_id=result.session_id,
            trace_id=result.trace_id,
            event_type="DEV_TEAM_BENCHMARK_COMPLETED",
            payload={
                "benchmark_id": result.benchmark_id,
                "team_id": result.team_id,
                "round_count": len(result.rounds),
                "summary": result.summary.model_dump(mode="json"),
                "protocol_directives": result.protocol_directives.model_dump(mode="json"),
            },
        )
    )
    await _safe_emit(
        request,
        "DEV_TEAM_BENCHMARK",
        {
            "benchmark_id": result.benchmark_id,
            "team_id": result.team_id,
            "summary": result.summary.model_dump(mode="json"),
        },
    )
    await _safe_emit(request, "LOG_EVENT", completed_event.model_dump(mode="json"))
    return result


@router.post("/directives/resolve", response_model=GlobalProtocolDirectives)
async def resolve_global_directives(
    payload: ResolveGlobalDirectivesRequest,
    request: Request,
) -> GlobalProtocolDirectives:
    directives = _orchestrator(request).resolve_directives(payload.text)
    return directives


@router.post("/default/gather")
async def gather_default_dev_team(
    payload: GatherDefaultTeamRequest,
    request: Request,
) -> dict:
    report = _orchestrator(request).gather_default_team(
        task_description=payload.task_description,
        preferred_providers=list(payload.preferred_providers),
        include_internal_dialogue=payload.include_internal_dialogue,
    )
    event = _event_store(request).append_event(
        _event(
            session_id=report["plan"]["session_id"],
            trace_id=report["plan"]["trace_id"],
            event_type="DEV_TEAM_DEFAULT_GATHERED",
            payload={
                "team_id": report["team_id"],
                "default_process_active": report["default_process_active"],
                "role_counts": report["role_counts"],
                "errors": report["errors"],
            },
        )
    )
    await _safe_emit(
        request,
        "DEV_TEAM_DEFAULT_GATHERED",
        {
            "team_id": report["team_id"],
            "default_process_active": report["default_process_active"],
        },
    )
    await _safe_emit(request, "LOG_EVENT", event.model_dump(mode="json"))
    return report
