from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status

from app.core.logging import logger
from app.models.autoprompt import (
    CreateAutopromptRunRequest,
    CreateRunResponse,
    DeployPromptResponse,
    RunStatusResponse,
)
from app.models.events import EventEnvelope
from app.services.autoprompt.engine import AutopromptEngine
from app.services.autoprompt.registry import PromptRegistry
from app.services.logging.event_store import EventStore

router = APIRouter(prefix="/autoprompt", tags=["autoprompt"])


def _registry(request: Request) -> PromptRegistry:
    return request.app.state.prompt_registry


def _engine(request: Request) -> AutopromptEngine:
    return request.app.state.autoprompt_engine


def _event_store(request: Request) -> EventStore:
    return request.app.state.event_store


async def _safe_emit(request: Request, event_name: str, payload: dict[str, Any]) -> None:
    try:
        await request.app.state.sio.emit(event_name, payload)
    except Exception as exc:  # pragma: no cover - exercised through fault injection tests
        logger.warning(
            "socket_emit_failed",
            event_name=event_name,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def _build_system_event(
    *,
    session_id: str,
    trace_id: str,
    event_type: str,
    channel: str,
    payload: dict,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=f"evt_{uuid4().hex[:14]}",
        session_id=session_id,
        trace_id=trace_id,
        timestamp_utc=datetime.now(UTC),
        actor_id="backend",
        actor_role="SYSTEM",
        channel=channel,
        event_type=event_type,
        payload=payload,
    )


@router.post("/runs", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(payload: CreateAutopromptRunRequest, request: Request) -> CreateRunResponse:
    registry = _registry(request)
    engine = _engine(request)
    event_store = _event_store(request)

    run = registry.create_run(payload)
    created_event = _build_system_event(
        session_id=run.session_id,
        trace_id=run.trace_id,
        event_type="AUTOPROMPT_RUN_CREATED",
        channel="AUTOPROMPT",
        payload={
            "run_id": run.run_id,
            "task_key": run.task_key,
            "status": run.status,
            "budget": run.budget.model_dump(mode="json"),
            "baseline_prompt": run.baseline_prompt,
        },
    )
    stored_created_event = event_store.append_event(created_event)
    await _safe_emit(request, "LOG_EVENT", stored_created_event.model_dump(mode="json"))

    async def on_status(status_payload: dict) -> None:
        await _safe_emit(request, "AUTOPROMPT_RUN_STATUS", status_payload)
        status_event = _build_system_event(
            session_id=run.session_id,
            trace_id=run.trace_id,
            event_type="AUTOPROMPT_RUN_STATUS",
            channel="AUTOPROMPT",
            payload=status_payload,
        )
        stored_status = event_store.append_event(status_event)
        await _safe_emit(request, "LOG_EVENT", stored_status.model_dump(mode="json"))

    async def on_candidate(candidate_payload) -> None:
        candidate_dict = candidate_payload.model_dump(mode="json")
        await _safe_emit(request, "AUTOPROMPT_CANDIDATE", candidate_dict)
        candidate_event = _build_system_event(
            session_id=run.session_id,
            trace_id=run.trace_id,
            event_type="AUTOPROMPT_CANDIDATE",
            channel="AUTOPROMPT",
            payload=candidate_dict,
        )
        stored_candidate = event_store.append_event(candidate_event)
        await _safe_emit(request, "LOG_EVENT", stored_candidate.model_dump(mode="json"))

    try:
        finished = await engine.run(run.run_id, on_status=on_status, on_candidate=on_candidate)
    except Exception as exc:
        failed_run = registry.require_run(run.run_id)
        failed_run.status = "FAILED"
        failed_run.updated_at = datetime.now(UTC)
        failed_run.budget_usage.finished_at = failed_run.updated_at
        failed_run.metrics = {
            "termination_reason": "engine_exception",
            "error_type": type(exc).__name__,
        }
        registry.save_run(failed_run)

        failure_payload = {
            "run_id": failed_run.run_id,
            "status": "FAILED",
            "error_code": "AUTOPROMPT_RUN_FAILED",
        }
        failure_event = _build_system_event(
            session_id=failed_run.session_id,
            trace_id=failed_run.trace_id,
            event_type="AUTOPROMPT_RUN_STATUS",
            channel="AUTOPROMPT",
            payload=failure_payload,
        )
        stored_failure = event_store.append_event(failure_event)
        await _safe_emit(request, "AUTOPROMPT_RUN_STATUS", failure_payload)
        await _safe_emit(request, "LOG_EVENT", stored_failure.model_dump(mode="json"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "AUTOPROMPT_RUN_FAILED", "run_id": failed_run.run_id},
        ) from exc

    return CreateRunResponse(
        run_id=finished.run_id,
        status=finished.status,
        baseline_prompt_version=finished.baseline_prompt_version,
    )


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
async def get_run(run_id: str, request: Request) -> RunStatusResponse:
    run = _registry(request).get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "run_id": run_id},
        )

    return RunStatusResponse(
        run_id=run.run_id,
        task_key=run.task_key,
        status=run.status,
        baseline_prompt_version=run.baseline_prompt_version,
        best_prompt_version=run.best_prompt_version,
        best_candidate=run.best_candidate,
        metrics=run.metrics,
        budget_usage=run.budget_usage,
    )


@router.post("/deploy/{prompt_version}", response_model=DeployPromptResponse)
async def deploy_prompt(prompt_version: str, request: Request) -> DeployPromptResponse:
    registry = _registry(request)
    event_store = _event_store(request)
    try:
        task_key, already_active = registry.deploy_prompt(prompt_version)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROMPT_VERSION_NOT_FOUND", "prompt_version": prompt_version},
        ) from exc

    payload = {
        "task_key": task_key,
        "prompt_version": prompt_version,
        "already_active": already_active,
    }
    await _safe_emit(request, "AUTOPROMPT_DEPLOYED", payload)

    deploy_event = _build_system_event(
        session_id=f"deploy_{task_key}",
        trace_id=f"deploy_{prompt_version}",
        event_type="AUTOPROMPT_DEPLOYED",
        channel="AUTOPROMPT",
        payload=payload,
    )
    stored_deploy = event_store.append_event(deploy_event)
    await _safe_emit(request, "LOG_EVENT", stored_deploy.model_dump(mode="json"))
    return DeployPromptResponse(**payload)
