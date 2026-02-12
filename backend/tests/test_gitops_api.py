from __future__ import annotations

from fastapi.testclient import TestClient


def test_gitops_snapshot_returns_repo_state(client: TestClient) -> None:
    resp = client.get("/api/v1/gitops/snapshot")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] in {"OK", "UNAVAILABLE"}
    assert "repo_root" in body
    assert "current_branch" in body
    assert "warnings" in body


def test_gitops_advise_returns_agent_recommendations_and_logs_event(client: TestClient) -> None:
    payload = {
        "objective": "set commit and branch strategy for context-handoff improvements",
        "changes_summary": "added preplanning agent and gitops commands",
        "risk_level": "MEDIUM",
        "collaboration_mode": "TEAM",
        "include_bootstrap_plan": True,
        "repo_name": "CogniSpace",
    }
    resp = client.post("/api/v1/gitops/advise", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert body["objective"] == payload["objective"]
    assert len(body["agent_recommendations"]) == 3
    assert body["suggested_commit_message"]
    assert "Objective:" in body["suggested_pr_comment"]
    assert len(body["consolidated_actions"]) >= 1

    session_id = body["session_id"]
    replay_resp = client.get(f"/api/v1/logs/sessions/{session_id}/events", params={"limit": 50})
    assert replay_resp.status_code == 200
    replay = replay_resp.json()
    event_types = [row["event_type"] for row in replay["events"]]
    assert "GITOPS_ADVICE_CREATED" in event_types
