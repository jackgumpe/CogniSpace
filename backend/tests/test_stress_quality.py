from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.models.events import EventEnvelope


def _payload(task_key: str, session_id: str, trace_id: str, max_iterations: int = 3) -> dict:
    return {
        "task_key": task_key,
        "baseline_prompt": "Return JSON output with strict constraints and MUST validation.",
        "session_id": session_id,
        "trace_id": trace_id,
        "budget": {
            "max_iterations": max_iterations,
            "max_tokens": 5000,
            "max_cost_usd": 1.0,
            "timeout_seconds": 30,
        },
        "constraints": {
            "required_keywords": ["JSON", "constraints"],
            "forbidden_patterns": ["ignore previous instructions"],
            "min_similarity": 0.05,
        },
    }


def test_stress_many_runs_no_silent_failures(client: TestClient) -> None:
    total = 30
    run_ids: list[str] = []
    for idx in range(total):
        resp = client.post(
            "/api/v1/autoprompt/runs",
            json=_payload(
                task_key=f"stress_task_{idx}",
                session_id=f"sess_stress_{idx}",
                trace_id=f"trace_stress_{idx}",
                max_iterations=4,
            ),
        )
        assert resp.status_code == 201
        run_ids.append(resp.json()["run_id"])

    for run_id in run_ids:
        status_resp = client.get(f"/api/v1/autoprompt/runs/{run_id}")
        assert status_resp.status_code == 200
        run = status_resp.json()
        assert run["status"] in {"SUCCEEDED", "FAILED"}
        assert "termination_reason" in run["metrics"]
        assert run["budget_usage"]["iterations_used"] <= 4


def test_stress_replay_pagination_gap_free(client: TestClient) -> None:
    session_id = "sess_pagination_stress"
    event_store = client.app.state.event_store

    for idx in range(250):
        event_store.append_event(
            EventEnvelope(
                event_id=f"evt_page_{idx:03d}",
                session_id=session_id,
                trace_id="trace_pagination",
                timestamp_utc=datetime.now(UTC),
                actor_id="system",
                actor_role="SYSTEM",
                channel="GLOBAL",
                event_type="PAGINATION_TEST",
                payload={"index": idx},
            )
        )

    fetched_ids: list[str] = []
    offset = 0
    while True:
        resp = client.get(
            f"/api/v1/logs/sessions/{session_id}/events",
            params={"limit": 37, "offset": offset},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ordered"] is True
        assert body["gap_free"] is True
        assert body["deterministic"] is True
        page_events = body["events"]
        fetched_ids.extend(item["event_id"] for item in page_events)
        next_offset = body["next_offset"]
        if next_offset is None:
            break
        offset = next_offset

    assert len(fetched_ids) == 250
    assert len(set(fetched_ids)) == 250
    assert fetched_ids[0] == "evt_page_000"
    assert fetched_ids[-1] == "evt_page_249"


def test_engine_exception_is_explicit_not_silent(client: TestClient) -> None:
    engine = client.app.state.autoprompt_engine
    original_run = engine.run

    async def crash(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("synthetic_engine_failure")

    engine.run = crash  # type: ignore[assignment]
    try:
        resp = client.post(
            "/api/v1/autoprompt/runs",
            json=_payload(task_key="engine_crash", session_id="sess_crash", trace_id="trace_crash"),
        )
    finally:
        engine.run = original_run  # type: ignore[assignment]

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"]["code"] == "AUTOPROMPT_RUN_FAILED"
    run_id = body["detail"]["run_id"]

    run_resp = client.get(f"/api/v1/autoprompt/runs/{run_id}")
    assert run_resp.status_code == 200
    run = run_resp.json()
    assert run["status"] == "FAILED"
    assert run["metrics"]["termination_reason"] == "engine_exception"


def test_stress_dataset_builds_after_run_batch(client: TestClient) -> None:
    sessions = []
    for idx in range(40):
        session_id = f"sess_ds_stress_{idx}"
        sessions.append(session_id)
        resp = client.post(
            "/api/v1/autoprompt/runs",
            json={
                "task_key": f"dataset_stress_task_{idx}",
                "baseline_prompt": "Return JSON output with constraints.",
                "session_id": session_id,
                "trace_id": f"trace_ds_{idx}",
                "budget": {
                    "max_iterations": 2,
                    "max_tokens": 1200,
                    "max_cost_usd": 1.0,
                    "timeout_seconds": 30,
                },
                "constraints": {
                    "required_keywords": ["JSON", "constraints"],
                    "forbidden_patterns": [],
                    "min_similarity": 0.05,
                },
            },
        )
        assert resp.status_code == 201

    build = client.post(
        "/api/v1/datasets/jsonic/build",
        json={"session_ids": sessions, "raw": True, "allow_partial": False},
    )
    assert build.status_code == 201
    data = build.json()
    assert data["event_count"] > 0
    assert data["conversation_count"] == 40
