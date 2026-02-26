from __future__ import annotations

from fastapi.testclient import TestClient


def test_gitops_snapshot_returns_repo_state(client: TestClient) -> None:
    resp = client.get("/api/v1/gitops/snapshot")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] in {"OK", "UNAVAILABLE"}
    assert "repo_root" in body
    assert "current_branch" in body
    assert "changed_paths" in body
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


def test_gitops_meta_plan_returns_metrics_and_logs_event(client: TestClient) -> None:
    payload = {
        "objective": "stand up autonomous git automation with perpetual meta planning",
        "repo_name": "CogniSpace",
        "risk_level": "HIGH",
        "include_hf_scan": True,
        "meta_squared_mode": "PATCH",
    }
    resp = client.post("/api/v1/gitops/meta-plan", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert body["objective"] == payload["objective"]
    assert len(body["specialist_team"]) >= 4
    assert len(body["meta_metrics"]) >= 5
    metric_ids = {row["metric_id"] for row in body["meta_metrics"]}
    assert "planning_drift_rate" in metric_ids
    assert "code_style_entropy" in metric_ids
    assert "update_loop" in body
    assert len(body["update_loop"]) >= 3
    assert body["meta_squared"]["enabled"] is True
    assert body["meta_squared"]["mode"] == "PATCH"
    assert body["meta_squared"]["triggered"] is True
    assert "risk_level_high" in body["meta_squared"]["trigger_reasons"]
    assert body["meta_squared"]["metric_quality_score"] >= 0.0
    assert body["meta_squared"]["decision_alignment_score"] >= 0.0

    session_id = body["session_id"]
    replay_resp = client.get(f"/api/v1/logs/sessions/{session_id}/events", params={"limit": 50})
    assert replay_resp.status_code == 200
    replay = replay_resp.json()
    event_types = [row["event_type"] for row in replay["events"]]
    assert "GITOPS_META_PLAN_CREATED" in event_types


def test_gitops_meta_plan_can_disable_meta_squared(client: TestClient) -> None:
    payload = {
        "objective": "build git automation plan with meta squared disabled",
        "repo_name": "CogniSpace",
        "risk_level": "LOW",
        "meta_squared_mode": "OFF",
    }
    resp = client.post("/api/v1/gitops/meta-plan", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta_squared"]["mode"] == "OFF"
    assert body["meta_squared"]["enabled"] is False
    assert body["meta_squared"]["triggered"] is False


def test_gitops_handoff_dry_run_logs_event(client: TestClient) -> None:
    payload = {
        "objective": "fully automate handoff pipeline",
        "dry_run": True,
        "run_tests": False,
        "pathspec": ["backend/app/cli.py"],
        "push_branch": False,
        "create_pr": False,
        "include_bootstrap": False,
        "trigger_workflows": False,
    }
    resp = client.post("/api/v1/gitops/handoff", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DRY_RUN"
    assert body["pathspec"] == ["backend/app/cli.py"]
    assert "steps" in body
    assert len(body["steps"]) >= 4

    session_id = body["session_id"]
    replay_resp = client.get(f"/api/v1/logs/sessions/{session_id}/events", params={"limit": 100})
    assert replay_resp.status_code == 200
    replay = replay_resp.json()
    event_types = [row["event_type"] for row in replay["events"]]
    assert "GITOPS_HANDOFF_COMPLETED" in event_types
