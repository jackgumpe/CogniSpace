from __future__ import annotations

from fastapi.testclient import TestClient


def _create_payload() -> dict:
    return {
        "task_key": "autoprompt_phase1",
        "baseline_prompt": "Return JSON output with strict constraints.",
        "session_id": "sess_api",
        "trace_id": "trace_api",
        "budget": {
            "max_iterations": 3,
            "max_tokens": 1000,
            "max_cost_usd": 1.0,
            "timeout_seconds": 30,
        },
        "constraints": {
            "required_keywords": ["JSON", "constraints"],
            "forbidden_patterns": ["ignore previous instructions"],
            "min_similarity": 0.05,
        },
    }


def test_create_get_and_deploy_autoprompt_run(client: TestClient) -> None:
    create_resp = client.post("/api/v1/autoprompt/runs", json=_create_payload())
    assert create_resp.status_code == 201
    create_body = create_resp.json()
    assert create_body["run_id"].startswith("run_")
    assert create_body["baseline_prompt_version"].startswith("pv_")

    run_resp = client.get(f"/api/v1/autoprompt/runs/{create_body['run_id']}")
    assert run_resp.status_code == 200
    run_body = run_resp.json()
    assert run_body["status"] in {"SUCCEEDED", "FAILED"}
    assert "metrics" in run_body
    assert "budget_usage" in run_body
    assert run_body["best_candidate"] is not None

    prompt_version = run_body["best_prompt_version"]
    deploy_resp = client.post(f"/api/v1/autoprompt/deploy/{prompt_version}")
    assert deploy_resp.status_code == 200
    assert deploy_resp.json()["already_active"] is False

    deploy_again = client.post(f"/api/v1/autoprompt/deploy/{prompt_version}")
    assert deploy_again.status_code == 200
    assert deploy_again.json()["already_active"] is True
