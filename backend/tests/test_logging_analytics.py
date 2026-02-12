from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.events import EventEnvelope


def _seed_pattern_session(client: TestClient, *, session_id: str, base_idx: int = 0) -> None:
    store = client.app.state.event_store
    base_ts = datetime.now(UTC)
    events = [
        ("PATTERN_A", "Plan options and evaluate tradeoff risk.", 50),
        ("PATTERN_B", "Team disagree and challenge proposal with conflict notes.", 80),
        ("PATTERN_A", "Plan revised with context summary and memory handoff.", 60),
        ("PATTERN_B", "Counterargument and compromise discussion.", 95),
        ("DECISION", "Final decision approved and selected.", 70),
        ("DEPLOY", "Deploy approved artifact.", 1200),
    ]
    for idx, (event_type, text, latency_ms) in enumerate(events):
        event = EventEnvelope(
            event_id=f"evt_analytics_{base_idx}_{idx}",
            session_id=session_id,
            trace_id=f"trace_{session_id}",
            timestamp_utc=base_ts + timedelta(seconds=idx),
            actor_id=f"agent_{idx % 3}",
            actor_role="SYSTEM",
            channel="AUTOPROMPT",
            event_type=event_type,
            payload={"message": text},
            latency_ms=latency_ms,
            token_in=10 + idx,
            token_out=20 + idx,
            cost_usd=0.00001 * (idx + 1),
        )
        store.append_event(event)


def test_session_analysis_returns_patterns_and_anomalies(client: TestClient) -> None:
    session_id = "sess_analysis_1"
    _seed_pattern_session(client, session_id=session_id, base_idx=1)

    resp = client.get(
        f"/api/v1/logs/sessions/{session_id}/analysis",
        params={"bucket_seconds": 2, "top_n": 5},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["session_id"] == session_id
    assert body["event_count"] == 6
    assert body["health_score"] <= 100
    assert any(row["key"] == "PATTERN_A > PATTERN_B" for row in body["pattern_mining"]["top_motifs_bigram"])
    assert "reliability_hits" in body["signals"]
    assert len(body["recommendations"]) >= 1
    assert any(item["code"] == "HIGH_P95_LATENCY" for item in body["anomalies"])


def test_global_analysis_detects_recurring_patterns(client: TestClient) -> None:
    _seed_pattern_session(client, session_id="sess_analysis_2", base_idx=2)
    _seed_pattern_session(client, session_id="sess_analysis_3", base_idx=3)

    resp = client.get("/api/v1/logs/analytics/global", params={"limit_sessions": 10, "top_n": 5})
    assert resp.status_code == 200
    body = resp.json()

    assert body["session_count"] >= 2
    assert body["total_events"] >= 12
    recurring_types = {row["key"] for row in body["recurring_event_types"]}
    assert "PATTERN_A" in recurring_types
    recurring_motifs = {row["key"] for row in body["recurring_motifs_bigram"]}
    assert "PATTERN_A > PATTERN_B" in recurring_motifs


def test_analysis_raw_disabled_returns_403(client: TestClient) -> None:
    session_id = "sess_analysis_raw"
    _seed_pattern_session(client, session_id=session_id, base_idx=4)
    client.app.state.event_store._allow_raw_logs = False

    resp = client.get(
        f"/api/v1/logs/sessions/{session_id}/analysis",
        params={"raw": "true"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "RAW_LOGS_DISABLED"
