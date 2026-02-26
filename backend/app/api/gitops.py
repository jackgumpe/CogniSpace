from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Request

from app.core.logging import logger
from app.models.events import EventEnvelope
from app.models.gitops import (
    GitAdviceRequest,
    GitAdviceResponse,
    GitHandoffRequest,
    GitHandoffResponse,
    GitMetaPlanRequest,
    GitMetaPlanResponse,
    GitRepoSnapshot,
)
from app.services.autoprompt.gitops import GitOpsAdvisor
from app.services.logging.event_store import EventStore

router = APIRouter(prefix="/gitops", tags=["gitops"])


def _advisor(request: Request) -> GitOpsAdvisor:
    return request.app.state.gitops_advisor


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


@router.get("/snapshot", response_model=GitRepoSnapshot)
async def get_git_snapshot(request: Request) -> GitRepoSnapshot:
    return _advisor(request).snapshot()


@router.post("/advise", response_model=GitAdviceResponse)
async def advise_git_workflow(
    payload: GitAdviceRequest,
    request: Request,
) -> GitAdviceResponse:
    advice = _advisor(request).advise(payload)
    event = _event_store(request).append_event(
        _event(
            session_id=advice.session_id,
            trace_id=advice.trace_id,
            event_type="GITOPS_ADVICE_CREATED",
            payload={
                "advice_id": advice.advice_id,
                "objective": advice.objective,
                "should_fork": advice.should_fork,
                "should_prune": advice.should_prune,
                "actions": advice.consolidated_actions,
                "repo_snapshot": advice.repo_snapshot.model_dump(mode="json"),
            },
        )
    )
    await _safe_emit(
        request,
        "GITOPS_ADVICE",
        {
            "advice_id": advice.advice_id,
            "should_fork": advice.should_fork,
            "should_prune": advice.should_prune,
        },
    )
    await _safe_emit(request, "LOG_EVENT", event.model_dump(mode="json"))
    return advice


@router.post("/meta-plan", response_model=GitMetaPlanResponse)
async def build_git_meta_plan(
    payload: GitMetaPlanRequest,
    request: Request,
) -> GitMetaPlanResponse:
    plan = _advisor(request).meta_plan(payload)
    event = _event_store(request).append_event(
        _event(
            session_id=plan.session_id,
            trace_id=plan.trace_id,
            event_type="GITOPS_META_PLAN_CREATED",
            payload={
                "plan_id": plan.plan_id,
                "objective": plan.objective,
                "metric_count": len(plan.meta_metrics),
                "specialist_count": len(plan.specialist_team),
                "repo_snapshot": plan.repo_snapshot.model_dump(mode="json"),
            },
        )
    )
    await _safe_emit(
        request,
        "GITOPS_META_PLAN",
        {
            "plan_id": plan.plan_id,
            "metric_count": len(plan.meta_metrics),
        },
    )
    await _safe_emit(request, "LOG_EVENT", event.model_dump(mode="json"))
    return plan


@router.post("/handoff", response_model=GitHandoffResponse)
async def run_git_handoff(
    payload: GitHandoffRequest,
    request: Request,
) -> GitHandoffResponse:
    result = _advisor(request).handoff(payload)
    event = _event_store(request).append_event(
        _event(
            session_id=result.session_id,
            trace_id=result.trace_id,
            event_type="GITOPS_HANDOFF_COMPLETED",
            payload={
                "handoff_id": result.handoff_id,
                "objective": result.objective,
                "status": result.status,
                "dry_run": result.dry_run,
                "pathspec": result.pathspec,
                "summary": result.summary,
                "branch_name": result.branch_name,
            },
        )
    )
    await _safe_emit(
        request,
        "GITOPS_HANDOFF",
        {
            "handoff_id": result.handoff_id,
            "status": result.status,
            "dry_run": result.dry_run,
            "pathspec_count": len(result.pathspec),
            "steps_total": result.summary.get("steps_total", 0),
            "steps_failed": result.summary.get("steps_failed", 0),
        },
    )
    await _safe_emit(request, "LOG_EVENT", event.model_dump(mode="json"))
    return result
