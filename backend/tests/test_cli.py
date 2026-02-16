from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.cli import main


def _base_args(tmp_path: Path) -> list[str]:
    return [
        "--log-dir",
        str(tmp_path / "logs"),
        "--dataset-dir",
        str(tmp_path / "datasets"),
        "--scoring-profile-path",
        str(tmp_path / "config" / "autoprompt_scoring_profile.json"),
    ]


def _read_json_output(capsys) -> dict:  # noqa: ANN001
    out = capsys.readouterr().out.strip()
    assert out
    return json.loads(out)


def test_cli_metrics_set_show_reset(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)

    code = main(
        args
        + [
            "autoprompt",
            "metrics",
            "set",
            "--json-bonus",
            "0.33",
            "--must-bonus",
            "0.17",
            "--output-json",
        ]
    )
    assert code == 0
    set_payload = _read_json_output(capsys)
    assert set_payload["updated"] is True
    assert set_payload["scoring_weights"]["json_bonus"] == 0.33
    assert set_payload["scoring_weights"]["must_bonus"] == 0.17

    code = main(args + ["autoprompt", "metrics", "show", "--output-json"])
    assert code == 0
    show_payload = _read_json_output(capsys)
    assert show_payload["scoring_weights"]["json_bonus"] == 0.33
    assert show_payload["scoring_weights"]["must_bonus"] == 0.17

    code = main(args + ["autoprompt", "metrics", "reset", "--output-json"])
    assert code == 0
    reset_payload = _read_json_output(capsys)
    assert reset_payload["reset"] is True
    assert reset_payload["scoring_weights"]["json_bonus"] == 0.2
    assert reset_payload["scoring_weights"]["must_bonus"] == 0.15


def test_cli_autoprompt_run_and_logs_debug_access(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)
    session_id = "sess_cli_debug"

    code = main(
        args
        + [
            "autoprompt",
            "run",
            "--task-key",
            "cli_debug_task",
            "--prompt",
            "Return JSON output with MUST constraints.",
            "--session-id",
            session_id,
            "--trace-id",
            "trace_cli_debug",
            "--required-keyword",
            "JSON",
            "--output-json",
        ]
    )
    assert code == 0
    run_payload = _read_json_output(capsys)
    assert run_payload["status"] in {"SUCCEEDED", "FAILED"}
    assert run_payload["session_id"] == session_id

    code = main(args + ["logs", "sessions", "--output-json"])
    assert code == 0
    sessions_payload = _read_json_output(capsys)
    assert session_id in sessions_payload["session_ids"]

    code = main(args + ["logs", "summary", "--session-id", session_id, "--output-json"])
    assert code == 0
    summary_payload = _read_json_output(capsys)
    assert summary_payload["count"] > 0

    code = main(
        args
        + [
            "logs",
            "replay",
            "--session-id",
            session_id,
            "--limit",
            "50",
            "--output-json",
        ]
    )
    assert code == 0
    replay_payload = _read_json_output(capsys)
    assert replay_payload["ordered"] is True
    assert replay_payload["gap_free"] is True
    assert replay_payload["deterministic"] is True
    event_types = [row["event_type"] for row in replay_payload["events"]]
    assert "AUTOPROMPT_RUN_CREATED" in event_types

    code = main(
        args
        + [
            "logs",
            "analyze",
            "--session-id",
            session_id,
            "--bucket-seconds",
            "10",
            "--top-n",
            "5",
            "--output-json",
        ]
    )
    assert code == 0
    analysis_payload = _read_json_output(capsys)
    assert analysis_payload["session_id"] == session_id
    assert "health_score" in analysis_payload
    assert "pattern_mining" in analysis_payload

    code = main(args + ["team", "validate-default", "--output-json"])
    assert code == 0
    team_payload = _read_json_output(capsys)
    assert team_payload["default_process_active"] is True
    assert team_payload["role_counts"] == {"SUPERVISOR": 1, "LEAD": 2, "DEV": 4}

    code = main(
        args
        + [
            "team",
            "preplan",
            "--task-key",
            "phase2_forward",
            "--task-description",
            "Plan next phase with context handoff and logging hardening.",
            "--horizon-cards",
            "6",
            "--output-json",
        ]
    )
    assert code == 0
    preplan_payload = _read_json_output(capsys)
    assert preplan_payload["agent_id"] == "agent_preplanner_1"
    assert len(preplan_payload["horizon_cards"]) == 6
    assert "replay_anchor_event_id" in preplan_payload["context_handoff_packet"]["required_fields"]

    code = main(args + ["team", "gather-gitops", "--output-json"])
    assert code == 0
    gitops_team_payload = _read_json_output(capsys)
    assert gitops_team_payload["default_process_active"] is True
    assert gitops_team_payload["task_key"] == "git_automation_process"
    assert any(
        row["check"] == "gitops_focus_present" and row["passed"]
        for row in gitops_team_payload["validation"]
    )


def test_cli_help_command_outputs_dos_help(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)
    code = main(args + ["help"])
    assert code == 0
    out = capsys.readouterr().out
    assert "COGNISPACE BACKEND CLI - DOS HELP" in out
    assert "AUTOPROMPT METRICS SHOW" in out
    assert "TEAM PREPLAN" in out
    assert "TEAM GATHER-GITOPS" in out
    assert "GITOPS ADVISE" in out
    assert "GITOPS META-PLAN" in out
    assert "GITOPS PR-OPEN" in out
    assert "GITOPS SHIP" in out
    assert "GITOPS SYNC-MAIN" in out


def test_cli_team_live_outputs_public_reasoning_transcript(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)

    code = main(
        args
        + [
            "team",
            "live",
            "--task-key",
            "phase_exec_demo",
            "--task-description",
            "Stream real-time public reasoning between supervisor leads and devs.",
            "--turns",
            "6",
            "--debate-mode",
            "MIXED",
            "--stream-delay-ms",
            "0",
            "--output-json",
        ]
    )
    assert code == 0
    payload = _read_json_output(capsys)
    assert payload["task_key"] == "phase_exec_demo"
    assert payload["total_messages"] == 6
    assert len(payload["attendance"]) >= 7
    assert len(payload["messages"]) == 6
    assert payload["messages"][-1]["message_type"] == "DECISION"
    assert payload["messages"][0]["outward_prose"]
    assert "public_reasoning" in payload["messages"][0]
    assert payload["private_chain_of_thought_exposed"] is False
    assert all(not row["private_chain_of_thought_exposed"] for row in payload["messages"])


def test_cli_menu_help_then_exit(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)
    commands = iter(["HELP", "EXIT"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))

    code = main(args + ["menu"])
    assert code == 0
    out = capsys.readouterr().out
    assert "COGNISPACE BACKEND CLI (DOS MENU)" in out
    assert "COGNISPACE BACKEND CLI - DOS HELP" in out


def test_cli_menu_accepts_uppercase_commands_and_options(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)
    commands = iter(["HEALTH --OUTPUT-JSON", "TEAM VALIDATE-DEFAULT --OUTPUT-JSON", "EXIT"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))

    code = main(args + ["menu"])
    assert code == 0
    out = capsys.readouterr().out
    assert "\"status\": \"ok\"" in out
    assert "\"component\": \"backend-cli\"" in out
    assert "\"default_process_active\": true" in out.lower()


def test_cli_deps_check_outputs_dependency_status(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)
    code = main(args + ["deps", "check", "--output-json"])
    payload = _read_json_output(capsys)
    assert code in {0, 2}
    assert payload["checked"] >= 1
    assert "checks" in payload
    assert any(item["module"] == "jsonschema" for item in payload["checks"])


def test_cli_gitops_snapshot_and_advise(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    args = _base_args(tmp_path)

    code = main(args + ["gitops", "snapshot", "--output-json"])
    assert code == 0
    snapshot_payload = _read_json_output(capsys)
    assert "status" in snapshot_payload
    assert "repo_root" in snapshot_payload
    assert "changed_paths" in snapshot_payload

    code = main(
        args
        + [
            "gitops",
            "advise",
            "--objective",
            "prepare commit strategy for logging hardening",
            "--changes-summary",
            "added replay checks and preplanning agent",
            "--risk-level",
            "MEDIUM",
            "--collaboration-mode",
            "TEAM",
            "--output-json",
        ]
    )
    assert code == 0
    advise_payload = _read_json_output(capsys)
    assert advise_payload["objective"] == "prepare commit strategy for logging hardening"
    assert "agent_recommendations" in advise_payload
    assert len(advise_payload["agent_recommendations"]) == 3
    assert "suggested_commit_message" in advise_payload

    code = main(
        args
        + [
            "gitops",
            "meta-plan",
            "--objective",
            "build perpetual git meta planning system for automation",
            "--repo-name",
            "CogniSpace",
            "--risk-level",
            "HIGH",
            "--meta-squared",
            "PATCH",
            "--output-json",
        ]
    )
    assert code == 0
    meta_payload = _read_json_output(capsys)
    assert meta_payload["objective"] == "build perpetual git meta planning system for automation"
    assert len(meta_payload["specialist_team"]) >= 4
    assert len(meta_payload["meta_metrics"]) >= 5
    assert meta_payload["meta_squared"]["enabled"] is True
    assert meta_payload["meta_squared"]["mode"] == "PATCH"
    assert meta_payload["meta_squared"]["triggered"] is True
    assert "risk_level_high" in meta_payload["meta_squared"]["trigger_reasons"]

    code = main(
        args
        + [
            "gitops",
            "meta-plan",
            "--objective",
            "build git planning with meta squared off",
            "--meta-squared",
            "OFF",
            "--output-json",
        ]
    )
    assert code == 0
    meta_off_payload = _read_json_output(capsys)
    assert meta_off_payload["meta_squared"]["enabled"] is False
    assert meta_off_payload["meta_squared"]["mode"] == "OFF"

    code = main(
        args
        + [
            "gitops",
            "handoff",
            "--objective",
            "finalize git automation handoff",
            "--repo-name",
            "CogniSpace",
            "--risk-level",
            "HIGH",
            "--meta-squared",
            "PATCH",
            "--no-run-tests",
            "--pathspec",
            "backend/app/cli.py",
            "--no-push-branch",
            "--output-json",
        ]
    )
    assert code == 0
    handoff_payload = _read_json_output(capsys)
    assert handoff_payload["status"] == "DRY_RUN"
    assert handoff_payload["dry_run"] is True
    assert handoff_payload["pathspec"] == ["backend/app/cli.py"]
    assert handoff_payload["summary"]["steps_planned"] >= 1
    assert any(step["step_id"] == "create_feature_branch" for step in handoff_payload["steps"])


def test_cli_missing_dependency_returns_actionable_error(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)

    def _raise_missing(_args):  # noqa: ANN001
        raise ModuleNotFoundError("No module named 'jsonschema'")

    monkeypatch.setattr(cli_module, "_create_runtime", _raise_missing)

    code = main(args + ["autoprompt", "metrics", "show", "--output-json"])
    assert code == 2
    payload = _read_json_output(capsys)
    assert payload["error_code"] == "MISSING_DEPENDENCY"
    assert payload["missing_module"] == "jsonschema"
    assert any("pip install -e .[dev]" in step for step in payload["fix"])
    assert payload["correction_agent"]["action_code"] == "DEPENDENCY_REPAIR"
    assert payload["correction_agent"]["should_autoprompt"] is True


def test_cli_gitops_pr_open_returns_existing_without_runtime(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)

    def _fake_find_gh() -> str:
        return "gh"

    def _fake_run_process(command, *, cwd=None):  # noqa: ANN001, ARG001
        if command[:3] == ["gh", "pr", "list"]:
            return cli_module.subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout='[{"number": 2, "url": "https://github.com/jackgumpe/CogniSpace/pull/2"}]',
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cli_module, "_find_gh_executable", _fake_find_gh)
    monkeypatch.setattr(cli_module, "_run_process", _fake_run_process)

    code = main(
        args
        + [
            "gitops",
            "pr-open",
            "--head",
            "feature/pathspec-safe-handoff-20260215",
            "--output-json",
        ]
    )
    assert code == 0
    payload = _read_json_output(capsys)
    assert payload["status"] == "exists"
    assert payload["url"].endswith("/pull/2")


def test_cli_gitops_pr_open_auth_required_is_actionable(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)

    def _fake_find_gh() -> str:
        return "gh"

    def _fake_run_process(command, *, cwd=None):  # noqa: ANN001, ARG001
        if command[:3] == ["gh", "pr", "list"]:
            return cli_module.subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="[]",
                stderr="",
            )
        if command[:3] == ["gh", "pr", "create"]:
            return cli_module.subprocess.CompletedProcess(
                args=command,
                returncode=1,
                stdout="",
                stderr="To get started with GitHub CLI, please run: gh auth login",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cli_module, "_find_gh_executable", _fake_find_gh)
    monkeypatch.setattr(cli_module, "_run_process", _fake_run_process)

    code = main(
        args
        + [
            "gitops",
            "pr-open",
            "--head",
            "feature/pathspec-safe-handoff-20260215",
            "--output-json",
        ]
    )
    assert code == 2
    payload = _read_json_output(capsys)
    assert payload["error_code"] == "GH_AUTH_REQUIRED"
    assert any("auth login" in row for row in payload["fix"])


def test_cli_gitops_ship_success(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)

    class _FakeHandoffResult:
        status = "SUCCEEDED"
        branch_name = "feature/ship-auto"

        def model_dump(self, mode="json"):  # noqa: ANN001
            return {
                "status": "SUCCEEDED",
                "branch_name": self.branch_name,
                "summary": {"steps_failed": 0},
            }

    class _FakeAdvisor:
        def handoff(self, request):  # noqa: ANN001
            assert request.pathspec == ["backend/app/cli.py"]
            assert request.dry_run is False
            return _FakeHandoffResult()

    monkeypatch.setattr(
        cli_module,
        "_create_runtime",
        lambda _args: SimpleNamespace(gitops_advisor=_FakeAdvisor()),
    )
    monkeypatch.setattr(
        cli_module,
        "_gitops_pr_open_result",
        lambda **kwargs: (0, {"status": "created", "url": "https://github.com/jackgumpe/CogniSpace/pull/999"}),
    )

    code = main(
        args
        + [
            "gitops",
            "ship",
            "--objective",
            "ship command smoke",
            "--pathspec",
            "backend/app/cli.py",
            "--no-run-tests",
            "--output-json",
        ]
    )
    assert code == 0
    payload = _read_json_output(capsys)
    assert payload["status"] == "succeeded"
    assert payload["handoff"]["status"] == "SUCCEEDED"
    assert payload["pr"]["status"] == "created"


def test_cli_gitops_ship_stops_when_handoff_fails(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)

    class _FakeHandoffResult:
        status = "FAILED"
        branch_name = "feature/ship-auto"

        def model_dump(self, mode="json"):  # noqa: ANN001
            return {
                "status": "FAILED",
                "branch_name": self.branch_name,
                "summary": {"steps_failed": 1},
            }

    class _FakeAdvisor:
        def handoff(self, request):  # noqa: ANN001, ARG002
            return _FakeHandoffResult()

    monkeypatch.setattr(
        cli_module,
        "_create_runtime",
        lambda _args: SimpleNamespace(gitops_advisor=_FakeAdvisor()),
    )
    monkeypatch.setattr(
        cli_module,
        "_gitops_pr_open_result",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("pr-open should not run when handoff fails")),
    )

    code = main(
        args
        + [
            "gitops",
            "ship",
            "--objective",
            "ship command failing handoff",
            "--pathspec",
            "backend/app/cli.py",
            "--no-run-tests",
            "--output-json",
        ]
    )
    assert code == 2
    payload = _read_json_output(capsys)
    assert payload["error_code"] == "SHIP_HANDOFF_FAILED"
    assert payload["handoff"]["status"] == "FAILED"


def test_cli_gitops_sync_main_success(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)
    calls: list[list[str]] = []

    def _fake_run_process(command, *, cwd=None):  # noqa: ANN001, ARG001
        calls.append(command)
        if command == ["git", "rev-parse", "--abbrev-ref", "HEAD"] and len(calls) == 1:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="feature/work\n", stderr="")
        if command[:2] == ["git", "fetch"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        if command[:2] == ["git", "checkout"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="Switched to branch 'main'\n", stderr="")
        if command[:3] == ["git", "pull", "--ff-only"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="Already up to date.\n", stderr="")
        if command[:3] == ["git", "remote", "prune"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        if command == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="main\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cli_module, "_run_process", _fake_run_process)

    code = main(args + ["gitops", "sync-main", "--prune", "--output-json"])
    assert code == 0
    payload = _read_json_output(capsys)
    assert payload["status"] == "succeeded"
    assert payload["current_branch_before"] == "feature/work"
    assert payload["current_branch_after"] == "main"
    assert payload["summary"]["steps_failed"] == 0


def test_cli_gitops_sync_main_fetch_failure(tmp_path: Path, capsys, monkeypatch) -> None:  # noqa: ANN001
    from app import cli as cli_module

    args = _base_args(tmp_path)

    def _fake_run_process(command, *, cwd=None):  # noqa: ANN001, ARG001
        if command == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=0, stdout="feature/work\n", stderr="")
        if command[:2] == ["git", "fetch"]:
            return cli_module.subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="network error")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cli_module, "_run_process", _fake_run_process)

    code = main(args + ["gitops", "sync-main", "--output-json"])
    assert code == 2
    payload = _read_json_output(capsys)
    assert payload["error_code"] == "SYNC_FETCH_FAILED"
    assert payload["steps"][-1]["status"] == "FAILED"
