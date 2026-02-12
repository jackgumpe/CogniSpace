from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.services.logging.analytics import ConversationAnalytics
from app.services.logging.event_store import EventStore

router = APIRouter(prefix="/logs", tags=["logs"])


def _event_store(request: Request) -> EventStore:
    return request.app.state.event_store


def _analytics(request: Request) -> ConversationAnalytics:
    return request.app.state.log_analytics


@router.get("/sessions/{session_id}")
async def get_session_summary(
    session_id: str,
    request: Request,
    raw: bool = Query(default=False),
) -> dict:
    store = _event_store(request)
    if raw and not store.raw_logs_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "RAW_LOGS_DISABLED", "raw": raw},
        )
    summary = store.get_session_summary(session_id=session_id, raw=raw)
    summary["raw"] = raw
    return summary


@router.get("/sessions/{session_id}/events")
async def replay_session_events(
    session_id: str,
    request: Request,
    since: str | None = Query(default=None, alias="since"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    raw: bool = Query(default=False),
) -> dict:
    store = _event_store(request)
    if raw and not store.raw_logs_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "RAW_LOGS_DISABLED", "raw": raw},
        )
    try:
        page = store.replay_session_events(
            session_id=session_id,
            since_event_id=since,
            limit=limit,
            offset=offset,
            raw=raw,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SINCE_EVENT_NOT_FOUND", "since_event_id": since},
        ) from exc

    page["ordered"] = True
    page["gap_free"] = True
    page["deterministic"] = True
    page["raw"] = raw
    return page


@router.get("/sessions/{session_id}/analysis")
async def analyze_session_events(
    session_id: str,
    request: Request,
    raw: bool = Query(default=False),
    bucket_seconds: int = Query(default=60, ge=1, le=3600),
    top_n: int = Query(default=10, ge=1, le=100),
) -> dict:
    store = _event_store(request)
    if raw and not store.raw_logs_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "RAW_LOGS_DISABLED", "raw": raw},
        )
    events = store.read_session_events(session_id=session_id, raw=raw)
    analysis = _analytics(request).analyze_session(
        session_id=session_id,
        events=events,
        bucket_seconds=bucket_seconds,
        top_n=top_n,
    )
    analysis["raw"] = raw
    return analysis


@router.get("/analytics/global")
async def analyze_global_sessions(
    request: Request,
    raw: bool = Query(default=False),
    limit_sessions: int = Query(default=50, ge=1, le=1000),
    bucket_seconds: int = Query(default=60, ge=1, le=3600),
    top_n: int = Query(default=10, ge=1, le=100),
) -> dict:
    store = _event_store(request)
    if raw and not store.raw_logs_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "RAW_LOGS_DISABLED", "raw": raw},
        )

    session_ids = store.list_session_ids(raw=raw)
    selected_ids = session_ids[-limit_sessions:]
    session_events = {
        session_id: store.read_session_events(session_id=session_id, raw=raw)
        for session_id in selected_ids
    }
    analysis = _analytics(request).analyze_global(
        session_events=session_events,
        bucket_seconds=bucket_seconds,
        top_n=top_n,
    )
    analysis["raw"] = raw
    analysis["selected_session_ids"] = selected_ids
    return analysis
