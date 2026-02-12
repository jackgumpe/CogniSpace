from __future__ import annotations

from collections.abc import Iterator

from fastapi.testclient import TestClient


def _run_with_budget(client: TestClient, budget: dict, baseline_prompt: str = "Return JSON output.") -> dict:
    payload = {
        "task_key": "budget_test",
        "baseline_prompt": baseline_prompt,
        "session_id": "sess_budget",
        "trace_id": "trace_budget",
        "budget": budget,
        "constraints": {"required_keywords": ["JSON"], "forbidden_patterns": [], "min_similarity": 0.05},
    }
    create_resp = client.post("/api/v1/autoprompt/runs", json=payload)
    assert create_resp.status_code == 201
    run_id = create_resp.json()["run_id"]
    run_resp = client.get(f"/api/v1/autoprompt/runs/{run_id}")
    assert run_resp.status_code == 200
    return run_resp.json()


def test_iteration_cap_enforced(client: TestClient) -> None:
    run = _run_with_budget(
        client,
        budget={
            "max_iterations": 1,
            "max_tokens": 5000,
            "max_cost_usd": 1.0,
            "timeout_seconds": 30,
        },
    )
    assert run["metrics"]["termination_reason"] in {"iteration_cap", "plateau"}
    assert run["budget_usage"]["iterations_used"] <= 1


def test_token_cap_enforced(client: TestClient) -> None:
    long_prompt = " ".join(["JSON"] * 100)
    run = _run_with_budget(
        client,
        budget={
            "max_iterations": 3,
            "max_tokens": 10,
            "max_cost_usd": 1.0,
            "timeout_seconds": 30,
        },
        baseline_prompt=long_prompt,
    )
    assert run["metrics"]["termination_reason"] == "token_cap"


def test_cost_cap_enforced(client: TestClient) -> None:
    run = _run_with_budget(
        client,
        budget={
            "max_iterations": 3,
            "max_tokens": 5000,
            "max_cost_usd": 0.0,
            "timeout_seconds": 30,
        },
        baseline_prompt="JSON " * 1000,
    )
    assert run["metrics"]["termination_reason"] == "cost_cap"


def test_timeout_cap_enforced(client: TestClient) -> None:
    engine = client.app.state.autoprompt_engine
    original_time_source = engine._time_source
    ticks: Iterator[float] = iter([0.0, 2.0, 2.0, 2.0])
    engine._time_source = lambda: next(ticks, 2.0)
    try:
        run = _run_with_budget(
            client,
            budget={
                "max_iterations": 10,
                "max_tokens": 5000,
                "max_cost_usd": 1.0,
                "timeout_seconds": 1,
            },
            baseline_prompt="Return JSON output with deterministic checks.",
        )
    finally:
        engine._time_source = original_time_source

    assert run["metrics"]["termination_reason"] == "timeout"
    assert run["budget_usage"]["timed_out"] is True
