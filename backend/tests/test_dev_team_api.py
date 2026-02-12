from __future__ import annotations

from fastapi.testclient import TestClient


def _plan_payload() -> dict:
    return {
        "task_key": "multi_llm_workspace",
        "task_description": (
            "Build autoprompting, replayable logs, and context transition support "
            "with strong schema validation and stress testing. "
            "<critical>true</critical><agents_required>9</agents_required>"
            "<context_handoff>required</context_handoff>"
            "<utility>schema_linter, security_scan</utility>"
        ),
        "preferred_providers": ["GEMINI", "CLAUDE", "CODEX"],
        "debate_mode": "MIXED",
        "include_internal_dialogue": True,
        "sprint_slots": 8,
        "session_id": "sess_dev_team_plan",
        "trace_id": "trace_dev_team_plan",
    }


def test_dev_team_plan_has_1_plus_6_structure(client: TestClient) -> None:
    resp = client.post("/api/v1/autoprompt/dev-team/plan", json=_plan_payload())
    assert resp.status_code == 200
    body = resp.json()

    assert body["policy"]["workflow"] == "KANBAN"
    assert body["policy"]["decision_mode"] == "DEMOCRATIC_WITH_ESCALATION"
    assert body["policy"]["debate_mode"] == "SYNC"
    assert body["protocol_directives"]["severity"] == "CRITICAL"
    assert body["protocol_directives"]["agents_required"] == 9
    assert body["protocol_directives"]["context_handoff_required"] is True
    assert "SCHEMA_LINTER" in body["protocol_directives"]["required_utilities"]
    assert len(body["agents"]) == 9

    by_role = {"SUPERVISOR": 0, "LEAD": 0, "DEV": 0}
    for agent in body["agents"]:
        by_role[agent["base_role"]] += 1
        assert isinstance(agent["internal_meta_prompt"], str)
        assert len(agent["internal_meta_prompt"]) > 20

    assert by_role == {"SUPERVISOR": 1, "LEAD": 2, "DEV": 6}
    assert len(body["kanban_cards"]) >= 10
    assert any("Healthy disagreement" in rule for rule in body["policy"]["culture_rules"])


def test_dev_team_preplan_creates_forward_plan(client: TestClient) -> None:
    payload = {
        "task_key": "phase2_preplan",
        "task_description": (
            "Prepare next phase with logging hardening and context handoff. "
            "<cautious>true</cautious><context_handoff>required</context_handoff>"
        ),
        "horizon_cards": 7,
        "include_risk_matrix": True,
        "session_id": "sess_dev_team_preplan",
        "trace_id": "trace_dev_team_preplan",
    }
    resp = client.post("/api/v1/autoprompt/dev-team/preplan", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert body["agent_id"] == "agent_preplanner_1"
    assert body["task_key"] == "phase2_preplan"
    assert body["protocol_directives"]["severity"] == "CAUTIOUS"
    assert body["protocol_directives"]["context_handoff_required"] is True
    assert len(body["horizon_cards"]) == 7
    assert len(body["phase_checkpoints"]) >= 5
    assert len(body["risk_matrix"]) >= 1
    assert "replay_anchor_event_id" in body["context_handoff_packet"]["required_fields"]


def test_dev_team_benchmark_reports_gain_and_authority(client: TestClient) -> None:
    payload = {
        "task_key": "agent_debate",
        "task_description": (
            "Plan and implement robust autoprompting with kanban workflow, "
            "team debates, security checks, and benchmark reporting. "
            "<cautious>true</cautious><min_debate_cycles>3</min_debate_cycles>"
        ),
        "rounds": 6,
        "debate_mode": "SYNC",
        "include_internal_dialogue": True,
        "include_round_transcript": True,
        "preferred_providers": ["GEMINI", "CLAUDE", "CODEX"],
        "session_id": "sess_dev_team_bench",
        "trace_id": "trace_dev_team_bench",
    }
    resp = client.post("/api/v1/autoprompt/dev-team/benchmark", json=payload)
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["rounds"]) == 6
    assert body["protocol_directives"]["severity"] in {"CAUTIOUS", "CRITICAL"}
    assert body["protocol_directives"]["min_debate_cycles"] >= 3
    assert body["summary"]["team_avg_score"] >= body["summary"]["baseline_avg_score"]
    assert body["summary"]["avg_score_delta"] > 0
    assert body["summary"]["decision_authority_enforced"] is True
    assert body["summary"]["rounds_with_conflict"] >= 2
    assert len(body["round_transcript"]) > 0
    assert any("internal_dialogue" in row for row in body["round_transcript"] if "agent_id" in row)


def test_dev_team_benchmark_events_are_replayable(client: TestClient) -> None:
    session_id = "sess_dev_team_replay"
    payload = {
        "task_key": "replay_validation",
        "task_description": "Stress benchmark with logs and conflict resolution.",
        "rounds": 5,
        "debate_mode": "MIXED",
        "include_internal_dialogue": True,
        "include_round_transcript": False,
        "preferred_providers": ["GEMINI", "CLAUDE", "CODEX"],
        "session_id": session_id,
        "trace_id": "trace_dev_team_replay",
    }
    run_resp = client.post("/api/v1/autoprompt/dev-team/benchmark", json=payload)
    assert run_resp.status_code == 200

    replay_resp = client.get(f"/api/v1/logs/sessions/{session_id}/events", params={"limit": 100})
    assert replay_resp.status_code == 200
    replay = replay_resp.json()
    assert replay["ordered"] is True
    assert replay["gap_free"] is True
    assert replay["deterministic"] is True

    event_types = [event["event_type"] for event in replay["events"]]
    assert "DEV_TEAM_BENCHMARK_ROUND" in event_types
    assert "DEV_TEAM_BENCHMARK_COMPLETED" in event_types


def test_resolve_directives_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/autoprompt/dev-team/directives/resolve",
        json={
            "text": (
                "Task with controls <critical>true</critical>"
                "<agents_required>6</agents_required>"
                "<debate_mode>sync</debate_mode>"
                "<utility>schema_linter,context_guard</utility>"
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "CRITICAL"
    assert body["agents_required"] == 7
    assert body["debate_mode_override"] == "SYNC"
    assert "SCHEMA_LINTER" in body["required_utilities"]
    assert len(body["parse_warnings"]) >= 1


def test_gather_default_dev_team_is_active_and_validated(client: TestClient) -> None:
    resp = client.post("/api/v1/autoprompt/dev-team/default/gather", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_process_active"] is True
    assert body["role_counts"] == {"SUPERVISOR": 1, "LEAD": 2, "DEV": 4}
    assert body["agent_count"] == 7
    assert body["errors"] == []
    assert any(item["check"] == "team_shape_1_2_4" and item["passed"] for item in body["validation"])


def test_dev_team_preplan_events_are_replayable(client: TestClient) -> None:
    session_id = "sess_preplan_replay"
    run_resp = client.post(
        "/api/v1/autoprompt/dev-team/preplan",
        json={
            "task_key": "preplan_replay",
            "task_description": "Plan ahead for stress and logging replay checks.",
            "horizon_cards": 6,
            "include_risk_matrix": True,
            "session_id": session_id,
            "trace_id": "trace_preplan_replay",
        },
    )
    assert run_resp.status_code == 200

    replay_resp = client.get(f"/api/v1/logs/sessions/{session_id}/events", params={"limit": 50})
    assert replay_resp.status_code == 200
    replay = replay_resp.json()
    event_types = [row["event_type"] for row in replay["events"]]
    assert "DEV_TEAM_PREPLAN_CREATED" in event_types
