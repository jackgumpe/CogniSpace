from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.models.events import EventEnvelope


def _seed_session(client: TestClient, session_id: str) -> None:
    store = client.app.state.event_store
    events = [
        EventEnvelope(
            event_id=f"evt_{session_id}_1",
            session_id=session_id,
            trace_id=f"trace_{session_id}",
            timestamp_utc=datetime.now(UTC),
            actor_id="user",
            actor_role="USER",
            channel="LOCAL",
            event_type="USER_PROMPT",
            payload={"text": "write code", "api_key": "sk-secret-123456789"},
        ),
        EventEnvelope(
            event_id=f"evt_{session_id}_2",
            session_id=session_id,
            trace_id=f"trace_{session_id}",
            timestamp_utc=datetime.now(UTC),
            actor_id="codex",
            actor_role="DEV",
            channel="AUTOPROMPT",
            event_type="NEXUS_EVENT",
            payload={"content": "done", "token": "abc"},
        ),
    ]
    for event in events:
        store.append_event(event)


def test_build_dataset_raw_preview_download_and_deploy(client: TestClient, tmp_path: Path) -> None:
    session_id = "sess_dataset_raw"
    _seed_session(client, session_id=session_id)

    build_resp = client.post(
        "/api/v1/datasets/jsonic/build",
        json={
            "session_ids": [session_id],
            "raw": True,
            "allow_partial": False,
        },
    )
    assert build_resp.status_code == 201
    dataset = build_resp.json()
    dataset_id = dataset["dataset_id"]
    assert dataset["raw"] is True
    assert dataset["event_count"] == 2
    assert dataset["conversation_count"] == 1

    get_resp = client.get(f"/api/v1/datasets/jsonic/{dataset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["dataset_id"] == dataset_id

    preview_resp = client.get(
        f"/api/v1/datasets/jsonic/{dataset_id}/preview",
        params={"artifact": "events", "limit": 5},
    )
    assert preview_resp.status_code == 200
    rows = preview_resp.json()["rows"]
    assert len(rows) == 2
    assert rows[0]["payload"]["api_key"] == "sk-secret-123456789"

    download_resp = client.get(
        f"/api/v1/datasets/jsonic/{dataset_id}/download",
        params={"artifact": "manifest"},
    )
    assert download_resp.status_code == 200
    assert "jsonic_" in download_resp.text

    target = tmp_path / "deploy_target"
    deploy_resp = client.post(
        f"/api/v1/datasets/jsonic/{dataset_id}/deploy",
        json={"target_dir": str(target)},
    )
    assert deploy_resp.status_code == 200
    deployed_files = deploy_resp.json()["copied_files"]
    assert len(deployed_files) == 3
    for file_path in deployed_files:
        assert Path(file_path).exists()


def test_build_dataset_sanitized_mode_redacts_payload(client: TestClient) -> None:
    session_id = "sess_dataset_sanitized"
    _seed_session(client, session_id=session_id)

    build_resp = client.post(
        "/api/v1/datasets/jsonic/build",
        json={
            "session_ids": [session_id],
            "raw": False,
            "allow_partial": False,
        },
    )
    assert build_resp.status_code == 201
    dataset_id = build_resp.json()["dataset_id"]
    assert build_resp.json()["raw"] is False

    preview_resp = client.get(
        f"/api/v1/datasets/jsonic/{dataset_id}/preview",
        params={"artifact": "events", "limit": 5},
    )
    assert preview_resp.status_code == 200
    rows = preview_resp.json()["rows"]
    assert rows[0]["payload"]["api_key"] == "[REDACTED]"


def test_build_dataset_missing_sessions_returns_structured_error(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/datasets/jsonic/build",
        json={"session_ids": ["does_not_exist"], "raw": False},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "SESSIONS_NOT_FOUND"


def test_raw_dataset_build_disabled_returns_403(client: TestClient) -> None:
    builder = client.app.state.jsonic_dataset_builder
    builder._allow_raw_dataset_build = False
    _seed_session(client, session_id="sess_raw_disabled")

    resp = client.post(
        "/api/v1/datasets/jsonic/build",
        json={"session_ids": ["sess_raw_disabled"], "raw": True},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "RAW_DATASET_BUILD_DISABLED"
