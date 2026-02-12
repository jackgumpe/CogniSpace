from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.models.events import EventEnvelope


def _seed_events(client: TestClient, session_id: str) -> None:
    event_store = client.app.state.event_store
    for idx in range(3):
        event = EventEnvelope(
            event_id=f"evt_seed_{idx}",
            session_id=session_id,
            trace_id=f"trace_{session_id}",
            timestamp_utc=datetime.now(UTC),
            actor_id="tester",
            actor_role="SYSTEM",
            channel="LOCAL",
            event_type="TEST_EVENT",
            payload={"step": idx, "api_key": "sk-super-secret-value"},
        )
        event_store.append_event(event)


def test_session_summary_and_replay_since_event(client: TestClient) -> None:
    session_id = "sess_replay"
    _seed_events(client, session_id=session_id)

    summary_resp = client.get(f"/api/v1/logs/sessions/{session_id}")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["count"] == 3
    assert "tester" in summary["actors"]
    assert "LOCAL" in summary["channels"]

    first_page = client.get(
        f"/api/v1/logs/sessions/{session_id}/events",
        params={"limit": 2, "offset": 0},
    )
    assert first_page.status_code == 200
    body = first_page.json()
    assert body["ordered"] is True
    assert body["gap_free"] is True
    assert body["deterministic"] is True
    assert len(body["events"]) == 2
    assert body["events"][0]["payload"]["api_key"] == "[REDACTED]"
    assert isinstance(body["events"][0]["payload"]["step"], int)

    since_event_id = body["events"][0]["event_id"]
    replay_resp = client.get(
        f"/api/v1/logs/sessions/{session_id}/events",
        params={"since": since_event_id, "limit": 10, "offset": 0},
    )
    assert replay_resp.status_code == 200
    replay = replay_resp.json()
    assert replay["total_after_since"] == 2
    assert [item["event_id"] for item in replay["events"]] == ["evt_seed_1", "evt_seed_2"]

    raw_page = client.get(
        f"/api/v1/logs/sessions/{session_id}/events",
        params={"raw": "true", "limit": 2, "offset": 0},
    )
    assert raw_page.status_code == 200
    raw_body = raw_page.json()
    assert raw_body["raw"] is True
    assert raw_body["events"][0]["payload"]["api_key"] == "sk-super-secret-value"


def test_replay_unknown_since_returns_404(client: TestClient) -> None:
    _seed_events(client, session_id="sess_missing_anchor")
    resp = client.get(
        "/api/v1/logs/sessions/sess_missing_anchor/events",
        params={"since": "not_exists"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "SINCE_EVENT_NOT_FOUND"


def test_raw_replay_disabled_returns_403(client: TestClient) -> None:
    client.app.state.event_store._allow_raw_logs = False
    resp = client.get(
        "/api/v1/logs/sessions/sess_replay/events",
        params={"raw": "true"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "RAW_LOGS_DISABLED"
