from __future__ import annotations

from fastapi.testclient import TestClient


def test_dev_team_stress_no_silent_failures(client: TestClient) -> None:
    total = 40
    gains: list[float] = []
    for idx in range(total):
        resp = client.post(
            "/api/v1/autoprompt/dev-team/benchmark",
            json={
                "task_key": f"dev_team_stress_{idx}",
                "task_description": (
                    "Run collaborative kanban planning with debate and meta prompting "
                    "for backend logging and schema checks."
                ),
                "rounds": 3,
                "debate_mode": "MIXED",
                "include_internal_dialogue": True,
                "include_round_transcript": False,
                "preferred_providers": ["GEMINI", "CLAUDE", "CODEX"],
                "session_id": f"sess_dev_team_stress_{idx}",
                "trace_id": f"trace_dev_team_stress_{idx}",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        gains.append(body["summary"]["avg_score_delta"])
        assert body["summary"]["decision_authority_enforced"] is True

    assert len(gains) == total
    assert min(gains) > 0
