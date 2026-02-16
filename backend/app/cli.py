from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

@dataclass
class Runtime:
    event_store: Any
    registry: Any
    engine: Any
    scoring_profile_store: Any
    log_analytics: Any
    dev_team_orchestrator: Any
    gitops_advisor: Any


REQUIRED_DEPENDENCIES = [
    "fastapi",
    "uvicorn",
    "socketio",
    "pydantic",
    "pydantic_settings",
    "structlog",
    "orjson",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "redis",
    "httpx",
    "jsonschema",
]

_META_ITERATE_WEIGHTS_V1 = {
    "impact": 0.35,
    "automation_gain": 0.20,
    "operability": 0.15,
    "testability": 0.15,
    "risk_inverse": 0.15,
}

_DEFAULT_META_ITERATE_FEATURES_V1 = [
    {
        "feature": "gitops_ship_profiles",
        "impact": 9.5,
        "automation_gain": 9.2,
        "operability": 8.8,
        "testability": 8.7,
        "risk": 3.2,
    },
    {
        "feature": "repo_default_config_file",
        "impact": 8.9,
        "automation_gain": 8.5,
        "operability": 8.4,
        "testability": 8.1,
        "risk": 3.6,
    },
    {
        "feature": "gitops_doctor",
        "impact": 8.4,
        "automation_gain": 7.9,
        "operability": 9.1,
        "testability": 8.3,
        "risk": 2.8,
    },
    {
        "feature": "json_output_contract_v2",
        "impact": 7.8,
        "automation_gain": 7.2,
        "operability": 8.7,
        "testability": 8.6,
        "risk": 3.1,
    },
    {
        "feature": "dos_menu_shortcuts",
        "impact": 6.9,
        "automation_gain": 6.4,
        "operability": 7.5,
        "testability": 7.1,
        "risk": 2.4,
    },
]


def _dos_help_text() -> str:
    lines = [
        "",
        "COGNISPACE BACKEND CLI - DOS HELP",
        "=================================",
        "GENERAL",
        "  HELP",
        "  HEALTH",
        "  MENU",
        "  DEPS CHECK",
        "",
        "LOGS",
        "  LOGS SESSIONS [--RAW] [--LIMIT N] [--OUTPUT-JSON]",
        "  LOGS SUMMARY --SESSION-ID <id> [--RAW] [--OUTPUT-JSON]",
        "  LOGS REPLAY --SESSION-ID <id> [--SINCE <event_id>] [--LIMIT N] [--OFFSET N] [--RAW] [--OUTPUT-JSON]",
        "  LOGS ANALYZE --SESSION-ID <id> [--BUCKET-SECONDS N] [--TOP-N N] [--RAW] [--OUTPUT-JSON]",
        "  LOGS GLOBAL-ANALYSIS [--LIMIT-SESSIONS N] [--BUCKET-SECONDS N] [--TOP-N N] [--RAW] [--OUTPUT-JSON]",
        "",
        "AUTOPROMPT",
        "  AUTOPROMPT RUN --TASK-KEY <key> --PROMPT \"...\" [budget/constraints flags] [--OUTPUT-JSON]",
        "",
        "TEAM PROCESS",
        "  TEAM GATHER-DEFAULT [--TASK-DESCRIPTION \"...\"] [--NO-INTERNAL-DIALOGUE] [--OUTPUT-JSON]",
        "  TEAM GATHER-GITOPS [--TASK-DESCRIPTION \"...\"] [--NO-INTERNAL-DIALOGUE] [--OUTPUT-JSON]",
        "  TEAM VALIDATE-DEFAULT [--OUTPUT-JSON]",
        "  TEAM PREPLAN --TASK-KEY <key> --TASK-DESCRIPTION \"...\" [--HORIZON-CARDS N]",
        "               [--NO-RISK-MATRIX] [--SESSION-ID <id>] [--TRACE-ID <id>] [--OUTPUT-JSON]",
        "  TEAM LIVE --TASK-KEY <key> --TASK-DESCRIPTION \"...\" [--TURNS N] [--DEBATE-MODE SYNC|ASYNC|MIXED]",
        "            [--NO-COUNTERARGUMENTS] [--STREAM-DELAY-MS N] [--SESSION-ID <id>] [--TRACE-ID <id>]",
        "            [--OUTPUT-JSON]",
        "",
        "GITOPS",
        "  GITOPS SNAPSHOT [--OUTPUT-JSON]",
        "  GITOPS ADVISE --OBJECTIVE \"...\" [--CHANGES-SUMMARY \"...\"] [--RISK-LEVEL LOW|MEDIUM|HIGH]",
        "                [--COLLABORATION-MODE SOLO|TEAM] [--INCLUDE-BOOTSTRAP-PLAN]",
        "                [--REPO-NAME CogniSpace] [--REMOTE-URL <url>] [--OUTPUT-JSON]",
        "  GITOPS META-PLAN --OBJECTIVE \"...\" [--REPO-NAME CogniSpace] [--NO-HF-SCAN] [--OUTPUT-JSON]",
        "                   [--RISK-LEVEL LOW|MEDIUM|HIGH] [--META-SQUARED OFF|PATCH]",
        "  GITOPS HANDOFF --OBJECTIVE \"...\" [--EXECUTE] [--RISK-LEVEL LOW|MEDIUM|HIGH]",
        "                 [--META-SQUARED OFF|PATCH] [--NO-RUN-TESTS] [--TEST-COMMAND \"...\"]",
        "                 [--PATHSPEC <repo/path> --PATHSPEC <repo/path> ...]",
        "                 [--NO-PUSH-BRANCH] [--CREATE-PR] [--INCLUDE-BOOTSTRAP]",
        "                 [--BOOTSTRAP-REPO owner/name] [--RESOURCE-GROUP <rg>] [--LOCATION <loc>]",
        "                 [--ACR-NAME <acr>] [--CONTAINER-APP-ENVIRONMENT <name>]",
        "                 [--CONTAINER-APP-NAME <name>] [--STATIC-WEB-APP-NAME <name>]",
        "                 [--DEPLOY-DATABASE-URL <url>] [--TRIGGER-WORKFLOWS] [--OUTPUT-JSON]",
        "  GITOPS PR-OPEN [--BASE main] [--HEAD <branch>] [--REPO owner/name] [--TITLE \"...\"] [--BODY \"...\"] [--OUTPUT-JSON]",
        "  GITOPS SHIP --OBJECTIVE \"...\" --PATHSPEC <repo/path> [--PATHSPEC <repo/path> ...]",
        "              [--NO-RUN-TESTS] [--BASE main] [--HEAD <branch>] [--OUTPUT-JSON]",
        "  GITOPS SYNC-MAIN [--MAIN-BRANCH main] [--REMOTE origin] [--PRUNE] [--OUTPUT-JSON]",
        "  GITOPS META-ITERATE [--FEATURES-FILE path.json] [--STORE-PATH path.json] [--TOP-K N]",
        "                      [--AUTOPROMPT-RUN] [--AUTOPROMPT-EXECUTE]",
        "                      [--AUTOPROMPT-EXECUTE-PARALLEL N] [--AUTOPROMPT-EXECUTE-RETRIES N]",
        "                      [--AUTOPROMPT-EXECUTE-BACKOFF-MS N] [--OUTPUT-JSON]",
        "",
        "METRICS TUNING",
        "  AUTOPROMPT METRICS SHOW [--OUTPUT-JSON]",
        "  AUTOPROMPT METRICS SET [--BASE-SCORE F] [--JSON-BONUS F] [--MUST-BONUS F] [--LENGTH-DIVISOR N]",
        "                         [--LENGTH-MAX-BONUS F] [--TASK-RELEVANCE-MAX-BONUS F]",
        "                         [--KEYWORD-COVERAGE-MAX-BONUS F] [--FORBIDDEN-PATTERN-PENALTY F]",
        "                         [--OUTPUT-JSON]",
        "  AUTOPROMPT METRICS RESET [--OUTPUT-JSON]",
        "  AUTOPROMPT METRICS SCORE-PREVIEW --TASK-KEY <key> --PROMPT \"...\" [--OUTPUT-JSON]",
        "",
        "MENU MODE COMMANDS",
        "  HELP      Show this command list",
        "  WHERE     Show active directories/profile paths",
        "  CLS       Clear screen",
        "  EXIT      Leave menu",
        "",
    ]
    return "\n".join(lines)


def _missing_dependency_payload(exc: ModuleNotFoundError) -> dict[str, Any]:
    from app.services.autoprompt.correction_agent import CorrectionAgent

    missing_module = getattr(exc, "name", None) or str(exc).split("'")[-2]
    decision = CorrectionAgent().analyze_exception(
        error_type=type(exc).__name__,
        message=str(exc),
        context={"missing_module": missing_module},
    )
    return {
        "status": "error",
        "error_code": "MISSING_DEPENDENCY",
        "missing_module": missing_module,
        "message": (
            f"Missing Python dependency '{missing_module}'. "
            "Activate backend virtual environment and install dependencies."
        ),
        "fix": decision.corrective_steps,
        "correction_agent": decision.to_dict(),
    }


def _create_runtime(args: argparse.Namespace) -> Runtime:
    from app.main import create_application

    app, _, _ = create_application(
        log_dir=args.log_dir,
        dataset_dir=args.dataset_dir,
        scoring_profile_path=args.scoring_profile_path,
        database_url=args.database_url,
    )
    return Runtime(
        event_store=app.state.event_store,
        registry=app.state.prompt_registry,
        engine=app.state.autoprompt_engine,
        scoring_profile_store=app.state.scoring_profile_store,
        log_analytics=app.state.log_analytics,
        dev_team_orchestrator=app.state.dev_team_orchestrator,
        gitops_advisor=app.state.gitops_advisor,
    )


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        import json

        print(json.dumps(payload, indent=2))
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


def _event(
    *,
    session_id: str,
    trace_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> Any:
    from app.models.events import EventEnvelope

    return EventEnvelope(
        event_id=f"evt_{uuid4().hex[:14]}",
        session_id=session_id,
        trace_id=trace_id,
        timestamp_utc=datetime.now(UTC),
        actor_id="backend-cli",
        actor_role="SYSTEM",
        channel="AUTOPROMPT",
        event_type=event_type,
        payload=payload,
    )


def _run_health(args: argparse.Namespace, runtime: Runtime) -> int:
    del runtime
    _emit(
        {
            "status": "ok",
            "component": "backend-cli",
            "timestamp_utc": datetime.now(UTC).isoformat(),
        },
        as_json=args.output_json,
    )
    return 0


def _run_help(args: argparse.Namespace, runtime: Runtime) -> int:
    del args, runtime
    print(_dos_help_text())
    return 0


def _run_deps_check(args: argparse.Namespace, runtime: Runtime) -> int:
    del runtime
    checks = [
        {"module": module, "installed": importlib.util.find_spec(module) is not None}
        for module in REQUIRED_DEPENDENCIES
    ]
    missing = [row["module"] for row in checks if not row["installed"]]
    payload = {
        "status": "ok" if not missing else "error",
        "checked": len(checks),
        "missing_count": len(missing),
        "checks": checks,
        "missing_modules": missing,
        "fix": [
            "cd C:\\Dev\\llm-workspace\\backend",
            ".\\.venv\\Scripts\\Activate.ps1",
            "pip install -e .[dev]",
        ]
        if missing
        else [],
    }
    _emit(payload, as_json=args.output_json)
    return 0 if not missing else 2


def _run_logs_sessions(args: argparse.Namespace, runtime: Runtime) -> int:
    session_ids = runtime.event_store.list_session_ids(raw=args.raw)
    payload = {
        "count": len(session_ids),
        "raw": args.raw,
        "session_ids": session_ids[: args.limit] if args.limit is not None else session_ids,
    }
    _emit(payload, as_json=args.output_json)
    return 0


def _run_logs_summary(args: argparse.Namespace, runtime: Runtime) -> int:
    summary = runtime.event_store.get_session_summary(session_id=args.session_id, raw=args.raw)
    summary["raw"] = args.raw
    _emit(summary, as_json=args.output_json)
    return 0


def _run_logs_replay(args: argparse.Namespace, runtime: Runtime) -> int:
    page = runtime.event_store.replay_session_events(
        session_id=args.session_id,
        since_event_id=args.since,
        limit=args.limit,
        offset=args.offset,
        raw=args.raw,
    )
    page["ordered"] = True
    page["gap_free"] = True
    page["deterministic"] = True
    page["raw"] = args.raw
    _emit(page, as_json=args.output_json)
    return 0


def _run_logs_analyze(args: argparse.Namespace, runtime: Runtime) -> int:
    events = runtime.event_store.read_session_events(session_id=args.session_id, raw=args.raw)
    result = runtime.log_analytics.analyze_session(
        session_id=args.session_id,
        events=events,
        bucket_seconds=args.bucket_seconds,
        top_n=args.top_n,
    )
    result["raw"] = args.raw
    _emit(result, as_json=args.output_json)
    return 0


def _run_logs_global_analysis(args: argparse.Namespace, runtime: Runtime) -> int:
    session_ids = runtime.event_store.list_session_ids(raw=args.raw)
    selected_ids = session_ids[-args.limit_sessions :]
    session_events = {
        session_id: runtime.event_store.read_session_events(session_id=session_id, raw=args.raw)
        for session_id in selected_ids
    }
    result = runtime.log_analytics.analyze_global(
        session_events=session_events,
        bucket_seconds=args.bucket_seconds,
        top_n=args.top_n,
    )
    result["raw"] = args.raw
    result["selected_session_ids"] = selected_ids
    _emit(result, as_json=args.output_json)
    return 0


def _execute_autoprompt_job(
    runtime: Runtime,
    *,
    task_key: str,
    prompt: str,
    session_id: str | None,
    trace_id: str | None,
    max_iterations: int,
    max_tokens: int,
    max_cost_usd: float,
    timeout_seconds: int,
    required_keywords: list[str],
    forbidden_patterns: list[str],
    min_similarity: float,
) -> dict[str, Any]:
    from app.models.autoprompt import BudgetConfig, CreateAutopromptRunRequest, DriftConstraints

    constraints = DriftConstraints(
        required_keywords=required_keywords,
        forbidden_patterns=forbidden_patterns,
        min_similarity=min_similarity,
    )
    payload = CreateAutopromptRunRequest(
        task_key=task_key,
        baseline_prompt=prompt,
        session_id=session_id,
        trace_id=trace_id,
        budget=BudgetConfig(
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            max_cost_usd=max_cost_usd,
            timeout_seconds=timeout_seconds,
        ),
        constraints=constraints,
    )
    run = runtime.registry.create_run(payload)
    runtime.event_store.append_event(
        _event(
            session_id=run.session_id,
            trace_id=run.trace_id,
            event_type="AUTOPROMPT_RUN_CREATED",
            payload={
                "run_id": run.run_id,
                "task_key": run.task_key,
                "budget": run.budget.model_dump(mode="json"),
            },
        )
    )

    async def on_status(status_payload: dict[str, Any]) -> None:
        runtime.event_store.append_event(
            _event(
                session_id=run.session_id,
                trace_id=run.trace_id,
                event_type="AUTOPROMPT_RUN_STATUS",
                payload=status_payload,
            )
        )

    async def on_candidate(candidate_payload) -> None:
        runtime.event_store.append_event(
            _event(
                session_id=run.session_id,
                trace_id=run.trace_id,
                event_type="AUTOPROMPT_CANDIDATE",
                payload=candidate_payload.model_dump(mode="json"),
            )
        )

    finished = asyncio.run(runtime.engine.run(run.run_id, on_status=on_status, on_candidate=on_candidate))
    result = {
        "run_id": finished.run_id,
        "task_key": finished.task_key,
        "status": finished.status,
        "session_id": finished.session_id,
        "trace_id": finished.trace_id,
        "best_prompt_version": finished.best_prompt_version,
        "metrics": finished.metrics,
        "budget_usage": finished.budget_usage.model_dump(mode="json"),
        "best_candidate": (
            finished.best_candidate.model_dump(mode="json") if finished.best_candidate is not None else None
        ),
    }
    return result


def _run_autoprompt_run(args: argparse.Namespace, runtime: Runtime) -> int:
    result = _execute_autoprompt_job(
        runtime,
        task_key=args.task_key,
        prompt=args.prompt,
        session_id=args.session_id,
        trace_id=args.trace_id,
        max_iterations=args.max_iterations,
        max_tokens=args.max_tokens,
        max_cost_usd=args.max_cost_usd,
        timeout_seconds=args.timeout_seconds,
        required_keywords=args.required_keyword or [],
        forbidden_patterns=args.forbidden_pattern or [],
        min_similarity=args.min_similarity,
    )
    _emit(result, as_json=args.output_json)
    return 0


def _run_team_gather_default(args: argparse.Namespace, runtime: Runtime) -> int:
    report = runtime.dev_team_orchestrator.gather_default_team(
        task_description=args.task_description,
        preferred_providers=["GEMINI", "CLAUDE", "CODEX"],
        include_internal_dialogue=not args.no_internal_dialogue,
    )
    _emit(report, as_json=args.output_json)
    return 0 if report.get("default_process_active", False) else 2


def _run_team_gather_gitops(args: argparse.Namespace, runtime: Runtime) -> int:
    report = runtime.dev_team_orchestrator.gather_gitops_team(
        task_description=args.task_description,
        preferred_providers=["GEMINI", "CLAUDE", "CODEX"],
        include_internal_dialogue=not args.no_internal_dialogue,
    )
    _emit(report, as_json=args.output_json)
    return 0 if report.get("default_process_active", False) else 2


def _run_team_validate_default(args: argparse.Namespace, runtime: Runtime) -> int:
    report = runtime.dev_team_orchestrator.gather_default_team()
    payload = {
        "default_process_active": report["default_process_active"],
        "team_id": report["team_id"],
        "role_counts": report["role_counts"],
        "validation": report["validation"],
        "errors": report["errors"],
    }
    _emit(payload, as_json=args.output_json)
    return 0 if payload["default_process_active"] else 2


def _run_team_preplan(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.dev_team import CreateDevTeamPreplanRequest

    request = CreateDevTeamPreplanRequest(
        task_key=args.task_key,
        task_description=args.task_description,
        horizon_cards=args.horizon_cards,
        include_risk_matrix=not args.no_risk_matrix,
        session_id=args.session_id,
        trace_id=args.trace_id,
    )
    result = runtime.dev_team_orchestrator.preplan(request)
    _emit(result.model_dump(mode="json"), as_json=args.output_json)
    return 0


def _run_team_live(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.dev_team import StartLiveDevTeamRunRequest

    request = StartLiveDevTeamRunRequest(
        task_key=args.task_key,
        task_description=args.task_description,
        turns=args.turns,
        debate_mode=args.debate_mode,
        include_counterarguments=not args.no_counterarguments,
        stream_delay_ms=args.stream_delay_ms,
        session_id=args.session_id,
        trace_id=args.trace_id,
    )
    result = runtime.dev_team_orchestrator.start_live_run(request)
    payload = result.model_dump(mode="json")

    if args.output_json:
        _emit(payload, as_json=True)
        return 0

    print(f"RUN_ID: {payload['run_id']}")
    print(f"TEAM_ID: {payload['team_id']}")
    print(f"SESSION_ID: {payload['session_id']}")
    print(f"ATTENDANCE_COUNT: {len(payload['attendance'])}")
    for row in payload["attendance"]:
        print(
            f"  PING {row['agent_role']}:{row['agent_id']} status={row['status']} "
            f"latency_ms={row['ping_ms']}"
        )
    print(f"MESSAGE_COUNT: {payload['total_messages']}")
    for row in payload["messages"]:
        print(
            f"[{row['sequence']:02d}] {row['agent_id']} {row['message_type']}: "
            f"{row.get('outward_prose', row['text'])} (confidence={row['confidence']})"
        )
        frame = row.get("public_reasoning", {})
        if frame:
            print(f"    claim: {frame.get('claim', '-')}")
            print(f"    risk: {frame.get('risk', '-')}")
            print(f"    next: {frame.get('next_step', '-')}")
    return 0


def _run_metrics_show(args: argparse.Namespace, runtime: Runtime) -> int:
    weights = runtime.engine.get_scoring_weights()
    payload = {
        "scoring_weights": weights.model_dump(mode="json"),
        "profile_path": str(runtime.scoring_profile_store.profile_path),
    }
    _emit(payload, as_json=args.output_json)
    return 0


def _run_metrics_set(args: argparse.Namespace, runtime: Runtime) -> int:
    current = runtime.engine.get_scoring_weights().model_dump(mode="json")
    updates = {
        "base_score": args.base_score,
        "json_bonus": args.json_bonus,
        "must_bonus": args.must_bonus,
        "length_divisor": args.length_divisor,
        "length_max_bonus": args.length_max_bonus,
        "task_relevance_max_bonus": args.task_relevance_max_bonus,
        "keyword_coverage_max_bonus": args.keyword_coverage_max_bonus,
        "forbidden_pattern_penalty": args.forbidden_pattern_penalty,
    }
    for key, value in updates.items():
        if value is not None:
            current[key] = value

    weights_cls = type(runtime.engine.get_scoring_weights())
    weights = weights_cls.model_validate(current)
    runtime.engine.set_scoring_weights(weights)
    runtime.scoring_profile_store.save(weights)
    _emit(
        {
            "updated": True,
            "scoring_weights": weights.model_dump(mode="json"),
            "profile_path": str(runtime.scoring_profile_store.profile_path),
        },
        as_json=args.output_json,
    )
    return 0


def _run_metrics_reset(args: argparse.Namespace, runtime: Runtime) -> int:
    weights = runtime.engine.reset_scoring_weights()
    runtime.scoring_profile_store.save(weights)
    _emit(
        {
            "reset": True,
            "scoring_weights": weights.model_dump(mode="json"),
            "profile_path": str(runtime.scoring_profile_store.profile_path),
        },
        as_json=args.output_json,
    )
    return 0


def _run_metrics_score_preview(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.autoprompt import DriftConstraints

    constraints = DriftConstraints(
        required_keywords=args.required_keyword or [],
        forbidden_patterns=args.forbidden_pattern or [],
        min_similarity=args.min_similarity,
    )
    score = runtime.engine.score_prompt(
        task_key=args.task_key,
        prompt_text=args.prompt,
        constraints=constraints,
    )
    _emit(
        {
            "task_key": args.task_key,
            "score": score,
            "scoring_weights": runtime.engine.get_scoring_weights().model_dump(mode="json"),
        },
        as_json=args.output_json,
    )
    return 0


def _run_gitops_snapshot(args: argparse.Namespace, runtime: Runtime) -> int:
    payload = runtime.gitops_advisor.snapshot().model_dump(mode="json")
    _emit(payload, as_json=args.output_json)
    return 0


def _run_gitops_advise(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.gitops import GitAdviceRequest

    request = GitAdviceRequest(
        objective=args.objective,
        changes_summary=args.changes_summary,
        risk_level=args.risk_level,
        collaboration_mode=args.collaboration_mode,
        include_bootstrap_plan=args.include_bootstrap_plan,
        repo_name=args.repo_name,
        remote_url=args.remote_url,
    )
    payload = runtime.gitops_advisor.advise(request).model_dump(mode="json")
    _emit(payload, as_json=args.output_json)
    return 0


def _run_gitops_meta_plan(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.gitops import GitMetaPlanRequest

    request = GitMetaPlanRequest(
        objective=args.objective,
        repo_name=args.repo_name,
        risk_level=args.risk_level,
        include_hf_scan=not args.no_hf_scan,
        meta_squared_mode=args.meta_squared,
    )
    payload = runtime.gitops_advisor.meta_plan(request).model_dump(mode="json")
    _emit(payload, as_json=args.output_json)
    return 0


def _run_gitops_handoff(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.gitops import GitBootstrapConfig, GitHandoffRequest

    include_bootstrap = bool(
        args.include_bootstrap
        or args.bootstrap_repo
        or args.resource_group
        or args.acr_name
        or args.trigger_workflows
    )
    bootstrap = None
    if include_bootstrap:
        bootstrap = GitBootstrapConfig(
            repo=args.bootstrap_repo,
            resource_group=args.resource_group,
            location=args.location,
            acr_name=args.acr_name,
            container_app_environment=args.container_app_environment,
            container_app_name=args.container_app_name,
            static_web_app_name=args.static_web_app_name,
            database_url=args.deploy_database_url,
        )
    request = GitHandoffRequest(
        objective=args.objective,
        repo_name=args.repo_name,
        risk_level=args.risk_level,
        meta_squared_mode=args.meta_squared,
        dry_run=not args.execute,
        run_tests=not args.no_run_tests,
        test_command=args.test_command,
        pathspec=args.pathspec or [],
        push_branch=not args.no_push_branch,
        create_pr=args.create_pr,
        include_bootstrap=include_bootstrap,
        trigger_workflows=args.trigger_workflows,
        bootstrap=bootstrap,
    )
    result = runtime.gitops_advisor.handoff(request)
    payload = result.model_dump(mode="json")
    _emit(payload, as_json=args.output_json)
    return 0 if result.status in {"DRY_RUN", "SUCCEEDED"} else 2


def _find_gh_executable() -> str | None:
    gh_path = shutil.which("gh")
    if gh_path:
        return gh_path

    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "GitHub CLI", "gh.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "GitHub CLI", "gh.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Programs", "GitHub CLI", "gh.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _run_process(command: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _default_meta_iterate_store_path() -> str:
    repo_root_proc = _run_process(["git", "rev-parse", "--show-toplevel"])
    repo_root = (repo_root_proc.stdout or "").strip() if repo_root_proc.returncode == 0 else os.getcwd()
    return os.path.join(repo_root, ".cogni", "meta_iterations.json")


def _normalize_meta_iterate_features(raw_payload: Any) -> tuple[list[dict[str, float | str]], list[str]]:
    payload = raw_payload
    if isinstance(payload, dict):
        if isinstance(payload.get("features"), list):
            payload = payload["features"]
        elif isinstance(payload.get("feature_metrics"), list):
            payload = payload["feature_metrics"]
    if not isinstance(payload, list):
        return [], ["Feature payload must be a JSON array."]

    errors: list[str] = []
    normalized: list[dict[str, float | str]] = []
    seen: set[str] = set()
    required_numeric = ["impact", "automation_gain", "operability", "testability", "risk"]
    for idx, row in enumerate(payload):
        if not isinstance(row, dict):
            errors.append(f"Feature at index {idx} must be an object.")
            continue
        feature = str(row.get("feature", "")).strip()
        if not feature:
            errors.append(f"Feature at index {idx} is missing 'feature'.")
            continue
        if feature in seen:
            errors.append(f"Duplicate feature '{feature}'.")
            continue
        seen.add(feature)

        parsed: dict[str, float | str] = {"feature": feature}
        for key in required_numeric:
            raw_value = row.get(key)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                errors.append(f"Feature '{feature}' has invalid numeric value for '{key}'.")
                continue
            if value < 0 or value > 10:
                errors.append(f"Feature '{feature}' field '{key}' must be between 0 and 10.")
                continue
            parsed[key] = round(value, 4)
        if all(key in parsed for key in required_numeric):
            normalized.append(parsed)

    return normalized, errors


def _meta_iterate_score(feature: dict[str, float | str]) -> float:
    impact = float(feature["impact"])
    automation_gain = float(feature["automation_gain"])
    operability = float(feature["operability"])
    testability = float(feature["testability"])
    risk_inverse = 10.0 - float(feature["risk"])
    score = (
        _META_ITERATE_WEIGHTS_V1["impact"] * impact
        + _META_ITERATE_WEIGHTS_V1["automation_gain"] * automation_gain
        + _META_ITERATE_WEIGHTS_V1["operability"] * operability
        + _META_ITERATE_WEIGHTS_V1["testability"] * testability
        + _META_ITERATE_WEIGHTS_V1["risk_inverse"] * risk_inverse
    )
    return round(score, 4)


def _meta_iterate_ranking_stability(previous_order: list[str], current_order: list[str]) -> float:
    if not previous_order:
        return 1.0
    prev_idx = {name: i for i, name in enumerate(previous_order)}
    common = [name for name in current_order if name in prev_idx]
    if not common:
        return 0.0
    displacement = sum(abs(prev_idx[name] - idx) for idx, name in enumerate(common))
    max_disp = max(1, len(previous_order) * len(common))
    coverage = len(common) / max(len(previous_order), len(current_order), 1)
    stability = max(0.0, 1.0 - (displacement / max_disp))
    return round(stability * coverage, 4)


def _meta_iterate_task_key(feature_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", feature_name.lower()).strip("_")
    return f"gitops_meta_{cleaned}" if cleaned else "gitops_meta_feature"


def _meta_iterate_prompt_for_feature(
    *,
    feature_name: str,
    iteration: str,
    previous_iteration: str,
    score: float,
    threshold: float,
) -> str:
    lines = [
        "You are a Senior Backend Engineer implementing a prioritized GitOps automation feature.",
        f"Feature: {feature_name}",
        f"Iteration context: {iteration} (previous={previous_iteration})",
        f"Metric score: {score:.4f} (selection threshold={threshold:.2f})",
        "Required outputs:",
        "1. Implementation diff scoped to this feature.",
        "2. Unit tests and mock-based tests for new behavior.",
        "3. Migration/ops notes and rollback steps.",
        "4. Metric delta report vs previous iteration.",
        "Constraints: keep changes deterministic, testable, and pathspec-safe.",
    ]
    return "\n".join(lines)


def _meta_iterate_autoprompt_command(task_key: str, prompt: str, feature_name: str) -> str:
    escaped_prompt = prompt.replace('"', '\\"')
    escaped_feature = feature_name.replace('"', '\\"')
    return (
        f'python -m app.cli autoprompt run --task-key "{task_key}" '
        f'--prompt "{escaped_prompt}" '
        '--required-keyword "tests" '
        '--required-keyword "rollback" '
        f'--required-keyword "{escaped_feature}" '
        '--min-similarity 0.25 --output-json'
    )


def _run_gitops_meta_iterate(args: argparse.Namespace, runtime: Runtime) -> int:
    exit_code = 0

    if args.features_file:
        try:
            with open(args.features_file, "r", encoding="utf-8") as fh:
                raw_features = json.loads(fh.read())
        except OSError as exc:
            _emit(
                {
                    "status": "error",
                    "error_code": "META_ITERATE_FEATURE_FILE_READ_FAILED",
                    "message": f"Could not read features file: {args.features_file}",
                    "details": str(exc),
                },
                as_json=args.output_json,
            )
            return 2
        except json.JSONDecodeError as exc:
            _emit(
                {
                    "status": "error",
                    "error_code": "META_ITERATE_FEATURE_FILE_INVALID_JSON",
                    "message": f"Features file is not valid JSON: {args.features_file}",
                    "details": str(exc),
                },
                as_json=args.output_json,
            )
            return 2
    else:
        raw_features = _DEFAULT_META_ITERATE_FEATURES_V1

    features, feature_errors = _normalize_meta_iterate_features(raw_features)
    if feature_errors:
        _emit(
            {
                "status": "error",
                "error_code": "META_ITERATE_INVALID_FEATURES",
                "message": "Feature metrics payload failed validation.",
                "errors": feature_errors,
            },
            as_json=args.output_json,
        )
        return 2

    store_path = args.store_path or _default_meta_iterate_store_path()
    history: list[dict[str, Any]] = []
    if not args.reset_store and os.path.exists(store_path):
        try:
            with open(store_path, "r", encoding="utf-8") as fh:
                blob = json.loads(fh.read())
            if isinstance(blob, dict) and isinstance(blob.get("history"), list):
                history = blob["history"]
            elif isinstance(blob, list):
                history = blob
        except (OSError, json.JSONDecodeError):
            history = []

    previous_record = history[-1] if history else None
    previous_iteration = str(previous_record.get("iteration", "v0")) if isinstance(previous_record, dict) else "v0"
    previous_scores = {}
    previous_order: list[str] = []
    if isinstance(previous_record, dict):
        prev_rows = previous_record.get("feature_metrics", [])
        if isinstance(prev_rows, list):
            for row in prev_rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("feature", "")).strip()
                if not name:
                    continue
                try:
                    previous_scores[name] = float(row.get("score_v1"))
                except (TypeError, ValueError):
                    continue
                previous_order.append(name)

    scored_rows: list[dict[str, Any]] = []
    for row in features:
        name = str(row["feature"])
        score = _meta_iterate_score(row)
        prev_score = previous_scores.get(name)
        delta = None if prev_score is None else round(score - prev_score, 4)
        delta_label = "NEW" if delta is None else f"{delta:+.2f}"
        scored_rows.append(
            {
                "feature": name,
                "impact": float(row["impact"]),
                "automation_gain": float(row["automation_gain"]),
                "operability": float(row["operability"]),
                "testability": float(row["testability"]),
                "risk": float(row["risk"]),
                "score_v1": score,
                "delta_vs_previous": delta,
                "delta_label": delta_label,
            }
        )
    scored_rows.sort(key=lambda item: item["score_v1"], reverse=True)

    current_order = [row["feature"] for row in scored_rows]
    common_deltas = [abs(row["delta_vs_previous"]) for row in scored_rows if row["delta_vs_previous"] is not None]
    average_score_delta = round(sum(common_deltas) / len(common_deltas), 4) if common_deltas else 0.0
    ranking_stability = _meta_iterate_ranking_stability(previous_order, current_order)
    if average_score_delta >= 1.0 or ranking_stability < 0.3:
        drift_flag = "HIGH"
    elif average_score_delta >= 0.5 or ranking_stability < 0.6:
        drift_flag = "MEDIUM"
    else:
        drift_flag = "LOW"

    average_risk = round(sum(row["risk"] for row in scored_rows) / max(len(scored_rows), 1), 4)
    top_score = scored_rows[0]["score_v1"] if scored_rows else 0.0
    second_score = scored_rows[1]["score_v1"] if len(scored_rows) > 1 else top_score
    top_gap = max(0.0, top_score - second_score)
    selection_confidence = _clamp(
        0.55 + min(top_gap / 4.0, 0.2) + (0.15 * ranking_stability) - (0.10 * (average_risk / 10.0)),
        0.0,
        0.99,
    )
    rework_risk_projection = _clamp(
        (0.45 * (average_risk / 10.0)) + (0.35 * (1.0 - ranking_stability)) + (0.20 * min(average_score_delta / 2.0, 1.0)),
        0.0,
        1.0,
    )

    threshold = 8.2
    if drift_flag == "HIGH":
        threshold += 0.3
    elif drift_flag == "MEDIUM":
        threshold += 0.1
    elif ranking_stability > 0.8:
        threshold -= 0.1
    threshold = round(threshold, 2)

    selected = [row for row in scored_rows if row["score_v1"] >= threshold]
    if not selected:
        selected = scored_rows[: max(args.top_k, 1)]
    selected = selected[: max(args.top_k, 1)]
    backlog = [f"{idx}) {row['feature']}" for idx, row in enumerate(selected, start=1)]

    average_automation = round(
        sum(row["automation_gain"] for row in scored_rows) / max(len(scored_rows), 1),
        4,
    )
    tuning_actions: list[str] = []
    if average_automation < 8.0:
        tuning_actions.append("Increase automation_gain weight by +0.05 in the next iteration candidate and compare outcomes.")
    if ranking_stability < 0.6:
        tuning_actions.append("Freeze top-3 backlog items for one cycle to reduce planning churn.")
    if rework_risk_projection > 0.35:
        tuning_actions.append("Raise selection threshold by +0.1 and require rollback notes in generated implementation prompts.")
    if average_score_delta < 0.25 and ranking_stability > 0.8:
        tuning_actions.append("Inject one unconventional feature candidate next cycle to avoid local optima.")
    tuning_actions.append(f"Apply score gate >= {threshold:.2f} for sprint inclusion.")

    iteration_number = len(history) + 1
    payload = {
        "iteration": f"v{iteration_number}",
        "previous_iteration": previous_iteration,
        "scoring_formula_v1": "score = 0.35*impact + 0.20*automation_gain + 0.15*operability + 0.15*testability + 0.15*(10-risk)",
        "weights_v1": _META_ITERATE_WEIGHTS_V1,
        "feature_metrics": scored_rows,
        "meta_metrics": {
            "ranking_stability": round(ranking_stability, 4),
            "average_score_delta": average_score_delta,
            "drift_flag": drift_flag,
            "selection_confidence": round(selection_confidence, 4),
            "rework_risk_projection": round(rework_risk_projection, 4),
        },
        "selection_threshold": threshold,
        "tuning_actions": tuning_actions,
        "autoprompted_backlog": backlog,
        "autoprompt_packet": {
            "system_goal": "maximize automation throughput while minimizing operational risk",
            "required_outputs": [
                "implementation diff",
                "tests",
                "migration notes",
                "rollback steps",
                "metric delta report vs previous iteration",
            ],
        },
        "store_path": store_path,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    if args.autoprompt_run or args.autoprompt_execute:
        command_rows: list[dict[str, str]] = []
        for row in selected:
            feature_name = str(row["feature"])
            task_key = _meta_iterate_task_key(feature_name)
            prompt_text = _meta_iterate_prompt_for_feature(
                feature_name=feature_name,
                iteration=str(payload["iteration"]),
                previous_iteration=str(payload["previous_iteration"]),
                score=float(row["score_v1"]),
                threshold=float(payload["selection_threshold"]),
            )
            command_rows.append(
                {
                    "feature": feature_name,
                    "task_key": task_key,
                    "prompt": prompt_text,
                    "command": _meta_iterate_autoprompt_command(task_key, prompt_text, feature_name),
                }
            )

        payload["autoprompt_run_plan"] = {
            "mode": "emit_commands",
            "generated_commands": len(command_rows),
            "commands": command_rows,
        }

    if args.autoprompt_execute:
        execute_runtime = runtime
        if execute_runtime is None:
            try:
                execute_runtime = _create_runtime(args)
            except ModuleNotFoundError as exc:
                _emit(_missing_dependency_payload(exc), as_json=args.output_json)
                return 2
        if execute_runtime is None:
            _emit(
                {
                    "status": "error",
                    "error_code": "RUNTIME_UNAVAILABLE",
                    "message": "Runtime is not initialized. Run 'deps check' and install missing packages.",
                },
                as_json=args.output_json,
            )
            return 2

        command_rows = payload.get("autoprompt_run_plan", {}).get("commands", [])
        execution_rows: list[dict[str, Any]] = []
        execution_session_id = f"sess_meta_iterate_exec_{uuid4().hex[:10]}"
        parallel_requested = max(1, int(args.autoprompt_execute_parallel))
        parallel_used = min(parallel_requested, max(len(command_rows), 1))
        max_retries = max(0, int(args.autoprompt_execute_retries))
        backoff_seconds = max(0.0, float(args.autoprompt_execute_backoff_ms) / 1000.0)

        def _run_one(
            row_index: int,
            row_payload: dict[str, Any],
            *,
            row_runtime: Runtime,
        ) -> tuple[int, dict[str, Any]]:
            feature_name = str(row_payload.get("feature", "feature"))
            task_key = str(row_payload.get("task_key", _meta_iterate_task_key(feature_name)))
            prompt_text = str(row_payload.get("prompt", ""))
            row_session_id = f"{execution_session_id}_{row_index + 1}"
            attempt_logs: list[dict[str, Any]] = []
            last_error: str | None = None

            for attempt in range(1, max_retries + 2):
                trace_id = f"trace_meta_iterate_exec_{uuid4().hex[:10]}"
                started = time.monotonic()
                try:
                    run_result = _execute_autoprompt_job(
                        row_runtime,
                        task_key=task_key,
                        prompt=prompt_text,
                        session_id=row_session_id,
                        trace_id=trace_id,
                        max_iterations=args.execute_max_iterations,
                        max_tokens=args.execute_max_tokens,
                        max_cost_usd=args.execute_max_cost_usd,
                        timeout_seconds=args.execute_timeout_seconds,
                        required_keywords=["tests", "rollback", feature_name],
                        forbidden_patterns=[],
                        min_similarity=args.execute_min_similarity,
                    )
                    duration_ms = round((time.monotonic() - started) * 1000.0, 3)
                    attempt_logs.append(
                        {
                            "attempt": attempt,
                            "status": "SUCCEEDED",
                            "run_id": run_result.get("run_id"),
                            "duration_ms": duration_ms,
                        }
                    )
                    return (
                        row_index,
                        {
                            "feature": feature_name,
                            "task_key": task_key,
                            "session_id": row_session_id,
                            "run_id": run_result.get("run_id"),
                            "status": run_result.get("status"),
                            "best_prompt_version": run_result.get("best_prompt_version"),
                            "metrics": run_result.get("metrics"),
                            "budget_usage": run_result.get("budget_usage"),
                            "attempts_used": attempt,
                            "retry_count": attempt - 1,
                            "attempt_logs": attempt_logs,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    duration_ms = round((time.monotonic() - started) * 1000.0, 3)
                    last_error = str(exc)
                    attempt_logs.append(
                        {
                            "attempt": attempt,
                            "status": "ERROR",
                            "error": last_error,
                            "duration_ms": duration_ms,
                        }
                    )
                    if attempt <= max_retries and backoff_seconds > 0:
                        time.sleep(backoff_seconds * (2 ** (attempt - 1)))

            return (
                row_index,
                {
                    "feature": feature_name,
                    "task_key": task_key,
                    "session_id": row_session_id,
                    "status": "ERROR",
                    "error": last_error or "unknown execution error",
                    "attempts_used": max_retries + 1,
                    "retry_count": max_retries,
                    "attempt_logs": attempt_logs,
                },
            )

        if parallel_used == 1:
            for idx, row in enumerate(command_rows):
                _, result_row = _run_one(idx, row, row_runtime=execute_runtime)
                execution_rows.append(result_row)
        else:
            indexed_results: list[tuple[int, dict[str, Any]]] = []
            with ThreadPoolExecutor(max_workers=parallel_used) as pool:
                future_map = {
                    pool.submit(_run_one, idx, row, row_runtime=_create_runtime(args)): idx
                    for idx, row in enumerate(command_rows)
                }
                for future in as_completed(future_map):
                    indexed_results.append(future.result())
            indexed_results.sort(key=lambda item: item[0])
            execution_rows = [row for _, row in indexed_results]

        succeeded_runs = sum(1 for row in execution_rows if row.get("status") == "SUCCEEDED")
        failed_runs = len(execution_rows) - succeeded_runs
        total_retry_count = sum(int(row.get("retry_count", 0)) for row in execution_rows)
        payload["autoprompt_execution"] = {
            "mode": "execute_runs",
            "execution_session_id": execution_session_id,
            "executed_runs": len(execution_rows),
            "succeeded_runs": succeeded_runs,
            "failed_runs": failed_runs,
            "parallelism_requested": parallel_requested,
            "parallelism_used": parallel_used,
            "max_retries": max_retries,
            "backoff_ms": int(args.autoprompt_execute_backoff_ms),
            "total_retry_count": total_retry_count,
            "runs": execution_rows,
        }
        if failed_runs > 0:
            exit_code = 2

    history.append(payload)
    try:
        parent_dir = os.path.dirname(store_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(store_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"version": "meta_iterate.v1", "history": history}, indent=2))
    except OSError as exc:
        _emit(
            {
                "status": "error",
                "error_code": "META_ITERATE_STORE_WRITE_FAILED",
                "message": f"Could not persist iteration history to: {store_path}",
                "details": str(exc),
                "iteration_payload": payload,
            },
            as_json=args.output_json,
        )
        return 2

    _emit(payload, as_json=args.output_json)
    return exit_code


def _gitops_pr_open_result(
    *,
    base: str,
    head: str | None,
    repo: str | None,
    title: str | None,
    body: str | None,
    draft: bool,
) -> tuple[int, dict[str, Any]]:
    gh_exe = _find_gh_executable()
    if not gh_exe:
        return (
            2,
            {
                "status": "error",
                "error_code": "GH_NOT_FOUND",
                "message": "GitHub CLI was not found on PATH.",
                "fix": [
                    "Install GitHub CLI: https://cli.github.com/",
                    "Or add C:\\Program Files\\GitHub CLI to PATH.",
                ],
            },
        )

    head_branch = (head or "").strip()
    if not head_branch:
        branch_proc = _run_process(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if branch_proc.returncode != 0:
            return (
                2,
                {
                    "status": "error",
                    "error_code": "GIT_BRANCH_DETECT_FAILED",
                    "message": "Could not detect current git branch.",
                    "stderr": branch_proc.stderr.strip() or None,
                },
            )
        head_branch = branch_proc.stdout.strip()

    list_command = [
        gh_exe,
        "pr",
        "list",
        "--state",
        "open",
        "--base",
        base,
        "--head",
        head_branch,
        "--json",
        "number,url",
        "--limit",
        "1",
    ]
    if repo:
        list_command.extend(["--repo", repo])

    existing_proc = _run_process(list_command)
    if existing_proc.returncode == 0:
        try:
            existing = json.loads(existing_proc.stdout or "[]")
        except json.JSONDecodeError:
            existing = []
        if isinstance(existing, list) and existing:
            row = existing[0] if isinstance(existing[0], dict) else {}
            return (
                0,
                {
                    "status": "exists",
                    "base": base,
                    "head": head_branch,
                    "url": row.get("url"),
                    "number": row.get("number"),
                    "repo": repo,
                },
            )

    create_command = [
        gh_exe,
        "pr",
        "create",
        "--base",
        base,
        "--head",
        head_branch,
    ]
    if repo:
        create_command.extend(["--repo", repo])
    if draft:
        create_command.append("--draft")
    if title or body:
        create_command.extend(["--title", title or f"PR: {head_branch}"])
        create_command.extend(["--body", body or "Automated PR via cogni-backend gitops pr-open."])
    else:
        create_command.append("--fill")

    create_proc = _run_process(create_command)
    combined = f"{create_proc.stdout}\n{create_proc.stderr}".strip()
    url_match = re.search(r"https://github\.com/\S+/pull/\d+", combined)
    pr_url = url_match.group(0) if url_match else None

    if create_proc.returncode != 0:
        lowered = combined.lower()
        if "gh auth login" in lowered or "gh_token" in lowered or "authentication" in lowered:
            return (
                2,
                {
                    "status": "error",
                    "error_code": "GH_AUTH_REQUIRED",
                    "message": "GitHub CLI is not authenticated.",
                    "fix": [
                        '& "C:\\Program Files\\GitHub CLI\\gh.exe" auth login --hostname github.com --git-protocol https --web',
                        "or set GH_TOKEN for this session before running pr-open.",
                    ],
                    "stderr": create_proc.stderr.strip() or None,
                },
            )
        if "already exists" in lowered and pr_url:
            return (
                0,
                {
                    "status": "exists",
                    "base": base,
                    "head": head_branch,
                    "url": pr_url,
                    "repo": repo,
                },
            )

        return (
            2,
            {
                "status": "error",
                "error_code": "PR_CREATE_FAILED",
                "message": "Failed to create pull request.",
                "stderr": create_proc.stderr.strip() or None,
                "stdout": create_proc.stdout.strip() or None,
            },
        )

    return (
        0,
        {
            "status": "created",
            "base": base,
            "head": head_branch,
            "url": pr_url or create_proc.stdout.strip() or None,
            "repo": repo,
            "draft": draft,
        },
    )


def _run_gitops_pr_open(args: argparse.Namespace, runtime: Runtime) -> int:
    del runtime

    code, payload = _gitops_pr_open_result(
        base=args.base,
        head=args.head,
        repo=args.repo,
        title=args.title,
        body=args.body,
        draft=args.draft,
    )
    _emit(payload, as_json=args.output_json)
    return code


def _run_gitops_ship(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.gitops import GitBootstrapConfig, GitHandoffRequest

    include_bootstrap = bool(
        args.include_bootstrap
        or args.bootstrap_repo
        or args.resource_group
        or args.acr_name
        or args.trigger_workflows
    )
    bootstrap = None
    if include_bootstrap:
        bootstrap = GitBootstrapConfig(
            repo=args.bootstrap_repo,
            resource_group=args.resource_group,
            location=args.location,
            acr_name=args.acr_name,
            container_app_environment=args.container_app_environment,
            container_app_name=args.container_app_name,
            static_web_app_name=args.static_web_app_name,
            database_url=args.deploy_database_url,
        )

    handoff_request = GitHandoffRequest(
        objective=args.objective,
        repo_name=args.repo_name,
        risk_level=args.risk_level,
        meta_squared_mode=args.meta_squared,
        dry_run=False,
        run_tests=not args.no_run_tests,
        test_command=args.test_command,
        pathspec=args.pathspec or [],
        push_branch=not args.no_push_branch,
        create_pr=False,
        include_bootstrap=include_bootstrap,
        trigger_workflows=args.trigger_workflows,
        bootstrap=bootstrap,
    )
    handoff_result = runtime.gitops_advisor.handoff(handoff_request)
    handoff_payload = handoff_result.model_dump(mode="json")
    if handoff_result.status != "SUCCEEDED":
        _emit(
            {
                "status": "error",
                "error_code": "SHIP_HANDOFF_FAILED",
                "message": "Ship aborted because handoff execution failed.",
                "handoff": handoff_payload,
            },
            as_json=args.output_json,
        )
        return 2

    pr_code, pr_payload = _gitops_pr_open_result(
        base=args.base,
        head=args.head or handoff_result.branch_name,
        repo=args.repo,
        title=args.title,
        body=args.body,
        draft=args.draft,
    )
    payload = {
        "status": "succeeded" if pr_code == 0 else "partial_failure",
        "handoff": handoff_payload,
        "pr": pr_payload,
    }
    _emit(payload, as_json=args.output_json)
    return 0 if pr_code == 0 else 2


def _run_gitops_sync_main(args: argparse.Namespace, runtime: Runtime) -> int:
    del runtime

    def _step(step_id: str, description: str, command: list[str]) -> dict[str, Any]:
        proc = _run_process(command)
        return {
            "step_id": step_id,
            "description": description,
            "command": " ".join(command),
            "status": "SUCCEEDED" if proc.returncode == 0 else "FAILED",
            "return_code": proc.returncode,
            "stdout": (proc.stdout or "").strip() or None,
            "stderr": (proc.stderr or "").strip() or None,
        }

    branch_before_proc = _run_process(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_before_proc.returncode != 0:
        _emit(
            {
                "status": "error",
                "error_code": "GIT_BRANCH_DETECT_FAILED",
                "message": "Could not detect current branch before sync.",
                "stderr": (branch_before_proc.stderr or "").strip() or None,
            },
            as_json=args.output_json,
        )
        return 2
    branch_before = (branch_before_proc.stdout or "").strip()

    steps: list[dict[str, Any]] = []
    steps.append(
        _step(
            "fetch_remote",
            "Fetch latest refs from configured remote.",
            ["git", "fetch", args.remote],
        )
    )
    if steps[-1]["status"] == "FAILED":
        _emit(
            {
                "status": "error",
                "error_code": "SYNC_FETCH_FAILED",
                "current_branch_before": branch_before,
                "steps": steps,
            },
            as_json=args.output_json,
        )
        return 2

    steps.append(
        _step(
            "checkout_main",
            "Switch to main branch target.",
            ["git", "checkout", args.main_branch],
        )
    )
    if steps[-1]["status"] == "FAILED":
        _emit(
            {
                "status": "error",
                "error_code": "SYNC_CHECKOUT_FAILED",
                "current_branch_before": branch_before,
                "steps": steps,
            },
            as_json=args.output_json,
        )
        return 2

    steps.append(
        _step(
            "pull_ff_only",
            "Fast-forward pull latest main branch state.",
            ["git", "pull", "--ff-only", args.remote, args.main_branch],
        )
    )
    if steps[-1]["status"] == "FAILED":
        _emit(
            {
                "status": "error",
                "error_code": "SYNC_PULL_FAILED",
                "current_branch_before": branch_before,
                "steps": steps,
            },
            as_json=args.output_json,
        )
        return 2

    if args.prune:
        steps.append(
            _step(
                "prune_remote",
                "Prune stale remote-tracking branches.",
                ["git", "remote", "prune", args.remote],
            )
        )

    branch_after_proc = _run_process(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch_after = (branch_after_proc.stdout or "").strip() if branch_after_proc.returncode == 0 else None
    payload = {
        "status": "succeeded",
        "current_branch_before": branch_before,
        "current_branch_after": branch_after,
        "main_branch": args.main_branch,
        "remote": args.remote,
        "steps": steps,
        "summary": {
            "steps_total": len(steps),
            "steps_succeeded": sum(1 for step in steps if step["status"] == "SUCCEEDED"),
            "steps_failed": sum(1 for step in steps if step["status"] == "FAILED"),
        },
    }
    _emit(payload, as_json=args.output_json)
    return 0


def _normalize_menu_tokens(parts: list[str]) -> list[str]:
    if not parts:
        return parts

    normalized = parts[:]
    normalized[0] = normalized[0].lower()

    # Lower only command path segments and option keys, not values.
    if len(normalized) >= 2 and normalized[0] in {"logs", "autoprompt", "deps", "team", "gitops"}:
        normalized[1] = normalized[1].lower()
    if len(normalized) >= 3 and normalized[0] == "autoprompt" and normalized[1] == "metrics":
        normalized[2] = normalized[2].lower()

    for idx, token in enumerate(normalized):
        if token.startswith("--"):
            key, eq, value = token.partition("=")
            normalized[idx] = f"{key.lower()}{eq}{value}"
    return normalized


def _run_menu(
    args: argparse.Namespace,
    runtime: Runtime | None,
    parser: argparse.ArgumentParser,
    init_error: dict[str, Any] | None = None,
) -> int:
    del parser
    print("")
    print("COGNISPACE BACKEND CLI (DOS MENU)")
    print("Type HELP for commands. Type EXIT to quit.")
    if init_error is not None:
        print("RUNTIME_INIT_WARNING:", init_error["message"])
        print("Type DEPS CHECK for diagnostics.")
    print("")
    local_parser = _build_parser()

    while True:
        try:
            line = input("COGNISPACE> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if not line:
            continue

        upper = line.upper()
        if upper in {"HELP", "?"}:
            print(_dos_help_text())
            continue
        if upper == "DEPS CHECK":
            deps_args = local_parser.parse_args(["deps", "check"])
            _execute_handler(deps_args, runtime, local_parser, init_error=init_error)
            continue
        if upper == "WHERE":
            if runtime is None:
                print("RUNTIME_UNAVAILABLE. Type DEPS CHECK.")
            else:
                print(f"LOG_DIR: {runtime.event_store.base_dir}")
                print(f"LOG_BACKEND: {getattr(runtime.event_store, 'backend_name', 'unknown')}")
                if getattr(runtime.event_store, "database_url", None):
                    print(f"DATABASE_URL: {runtime.event_store.database_url}")
                print(f"SCORING_PROFILE: {runtime.scoring_profile_store.profile_path}")
            continue
        if upper in {"CLS", "CLEAR"}:
            print("\n" * 60)
            continue
        if upper in {"EXIT", "QUIT"}:
            return 0

        try:
            parts = shlex.split(line, posix=True)
        except ValueError as exc:
            print(f"PARSE_ERROR: {exc}")
            continue
        if not parts:
            continue
        if parts[0].lower() == "cogni-backend":
            parts = parts[1:]
            if not parts:
                continue
        if parts[0].lower() == "help":
            print(_dos_help_text())
            continue
        parts = _normalize_menu_tokens(parts)
        try:
            parsed = local_parser.parse_args(parts)
        except SystemExit:
            print("INVALID_COMMAND. Type HELP.")
            continue
        if parsed.command == "menu":
            print("ALREADY_IN_MENU. Type HELP.")
            continue
        _execute_handler(parsed, runtime, local_parser, init_error=init_error)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cogni-backend")
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--dataset-dir", default=None)
    parser.add_argument("--scoring-profile-path", default=None)
    parser.add_argument("--database-url", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health")
    health.add_argument("--output-json", action="store_true")
    health.set_defaults(handler=_run_health, requires_runtime=False)

    help_cmd = subparsers.add_parser("help")
    help_cmd.add_argument("--output-json", action="store_true")
    help_cmd.set_defaults(handler=_run_help, requires_runtime=False)

    menu = subparsers.add_parser("menu")
    menu.set_defaults(handler=_run_menu, requires_runtime=False)

    deps = subparsers.add_parser("deps")
    deps_sub = deps.add_subparsers(dest="deps_command", required=True)
    deps_check = deps_sub.add_parser("check")
    deps_check.add_argument("--output-json", action="store_true")
    deps_check.set_defaults(handler=_run_deps_check, requires_runtime=False)

    logs = subparsers.add_parser("logs")
    logs_sub = logs.add_subparsers(dest="logs_command", required=True)

    logs_sessions = logs_sub.add_parser("sessions")
    logs_sessions.add_argument("--raw", action="store_true")
    logs_sessions.add_argument("--limit", type=int, default=None)
    logs_sessions.add_argument("--output-json", action="store_true")
    logs_sessions.set_defaults(handler=_run_logs_sessions, requires_runtime=True)

    logs_summary = logs_sub.add_parser("summary")
    logs_summary.add_argument("--session-id", required=True)
    logs_summary.add_argument("--raw", action="store_true")
    logs_summary.add_argument("--output-json", action="store_true")
    logs_summary.set_defaults(handler=_run_logs_summary, requires_runtime=True)

    logs_replay = logs_sub.add_parser("replay")
    logs_replay.add_argument("--session-id", required=True)
    logs_replay.add_argument("--since", default=None)
    logs_replay.add_argument("--limit", type=int, default=100)
    logs_replay.add_argument("--offset", type=int, default=0)
    logs_replay.add_argument("--raw", action="store_true")
    logs_replay.add_argument("--output-json", action="store_true")
    logs_replay.set_defaults(handler=_run_logs_replay, requires_runtime=True)

    logs_analyze = logs_sub.add_parser("analyze")
    logs_analyze.add_argument("--session-id", required=True)
    logs_analyze.add_argument("--bucket-seconds", type=int, default=60)
    logs_analyze.add_argument("--top-n", type=int, default=10)
    logs_analyze.add_argument("--raw", action="store_true")
    logs_analyze.add_argument("--output-json", action="store_true")
    logs_analyze.set_defaults(handler=_run_logs_analyze, requires_runtime=True)

    logs_global = logs_sub.add_parser("global-analysis")
    logs_global.add_argument("--limit-sessions", type=int, default=50)
    logs_global.add_argument("--bucket-seconds", type=int, default=60)
    logs_global.add_argument("--top-n", type=int, default=10)
    logs_global.add_argument("--raw", action="store_true")
    logs_global.add_argument("--output-json", action="store_true")
    logs_global.set_defaults(handler=_run_logs_global_analysis, requires_runtime=True)

    autoprompt = subparsers.add_parser("autoprompt")
    autoprompt_sub = autoprompt.add_subparsers(dest="autoprompt_command", required=True)

    autoprompt_run = autoprompt_sub.add_parser("run")
    autoprompt_run.add_argument("--task-key", required=True)
    autoprompt_run.add_argument("--prompt", required=True)
    autoprompt_run.add_argument("--session-id", default=None)
    autoprompt_run.add_argument("--trace-id", default=None)
    autoprompt_run.add_argument("--max-iterations", type=int, default=3)
    autoprompt_run.add_argument("--max-tokens", type=int, default=5000)
    autoprompt_run.add_argument("--max-cost-usd", type=float, default=1.0)
    autoprompt_run.add_argument("--timeout-seconds", type=int, default=30)
    autoprompt_run.add_argument("--required-keyword", action="append")
    autoprompt_run.add_argument("--forbidden-pattern", action="append")
    autoprompt_run.add_argument("--min-similarity", type=float, default=0.1)
    autoprompt_run.add_argument("--output-json", action="store_true")
    autoprompt_run.set_defaults(handler=_run_autoprompt_run, requires_runtime=True)

    team = subparsers.add_parser("team")
    team_sub = team.add_subparsers(dest="team_command", required=True)

    team_gather = team_sub.add_parser("gather-default")
    team_gather.add_argument("--task-description", default=None)
    team_gather.add_argument("--no-internal-dialogue", action="store_true")
    team_gather.add_argument("--output-json", action="store_true")
    team_gather.set_defaults(handler=_run_team_gather_default, requires_runtime=True)

    team_gather_gitops = team_sub.add_parser("gather-gitops")
    team_gather_gitops.add_argument("--task-description", default=None)
    team_gather_gitops.add_argument("--no-internal-dialogue", action="store_true")
    team_gather_gitops.add_argument("--output-json", action="store_true")
    team_gather_gitops.set_defaults(handler=_run_team_gather_gitops, requires_runtime=True)

    team_validate = team_sub.add_parser("validate-default")
    team_validate.add_argument("--output-json", action="store_true")
    team_validate.set_defaults(handler=_run_team_validate_default, requires_runtime=True)

    team_preplan = team_sub.add_parser("preplan")
    team_preplan.add_argument("--task-key", required=True)
    team_preplan.add_argument("--task-description", required=True)
    team_preplan.add_argument("--horizon-cards", type=int, default=6)
    team_preplan.add_argument("--no-risk-matrix", action="store_true")
    team_preplan.add_argument("--session-id", default=None)
    team_preplan.add_argument("--trace-id", default=None)
    team_preplan.add_argument("--output-json", action="store_true")
    team_preplan.set_defaults(handler=_run_team_preplan, requires_runtime=True)

    team_live = team_sub.add_parser("live")
    team_live.add_argument("--task-key", required=True)
    team_live.add_argument("--task-description", required=True)
    team_live.add_argument("--turns", type=int, default=10)
    team_live.add_argument("--debate-mode", choices=["SYNC", "ASYNC", "MIXED"], default="MIXED")
    team_live.add_argument("--no-counterarguments", action="store_true")
    team_live.add_argument("--stream-delay-ms", type=int, default=40)
    team_live.add_argument("--session-id", default=None)
    team_live.add_argument("--trace-id", default=None)
    team_live.add_argument("--output-json", action="store_true")
    team_live.set_defaults(handler=_run_team_live, requires_runtime=True)

    metrics = autoprompt_sub.add_parser("metrics")
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)

    metrics_show = metrics_sub.add_parser("show")
    metrics_show.add_argument("--output-json", action="store_true")
    metrics_show.set_defaults(handler=_run_metrics_show, requires_runtime=True)

    metrics_set = metrics_sub.add_parser("set")
    metrics_set.add_argument("--base-score", type=float, default=None)
    metrics_set.add_argument("--json-bonus", type=float, default=None)
    metrics_set.add_argument("--must-bonus", type=float, default=None)
    metrics_set.add_argument("--length-divisor", type=int, default=None)
    metrics_set.add_argument("--length-max-bonus", type=float, default=None)
    metrics_set.add_argument("--task-relevance-max-bonus", type=float, default=None)
    metrics_set.add_argument("--keyword-coverage-max-bonus", type=float, default=None)
    metrics_set.add_argument("--forbidden-pattern-penalty", type=float, default=None)
    metrics_set.add_argument("--output-json", action="store_true")
    metrics_set.set_defaults(handler=_run_metrics_set, requires_runtime=True)

    metrics_reset = metrics_sub.add_parser("reset")
    metrics_reset.add_argument("--output-json", action="store_true")
    metrics_reset.set_defaults(handler=_run_metrics_reset, requires_runtime=True)

    metrics_score_preview = metrics_sub.add_parser("score-preview")
    metrics_score_preview.add_argument("--task-key", required=True)
    metrics_score_preview.add_argument("--prompt", required=True)
    metrics_score_preview.add_argument("--required-keyword", action="append")
    metrics_score_preview.add_argument("--forbidden-pattern", action="append")
    metrics_score_preview.add_argument("--min-similarity", type=float, default=0.1)
    metrics_score_preview.add_argument("--output-json", action="store_true")
    metrics_score_preview.set_defaults(handler=_run_metrics_score_preview, requires_runtime=True)

    gitops = subparsers.add_parser("gitops")
    gitops_sub = gitops.add_subparsers(dest="gitops_command", required=True)

    gitops_snapshot = gitops_sub.add_parser("snapshot")
    gitops_snapshot.add_argument("--output-json", action="store_true")
    gitops_snapshot.set_defaults(handler=_run_gitops_snapshot, requires_runtime=True)

    gitops_advise = gitops_sub.add_parser("advise")
    gitops_advise.add_argument("--objective", required=True)
    gitops_advise.add_argument("--changes-summary", default=None)
    gitops_advise.add_argument("--risk-level", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
    gitops_advise.add_argument("--collaboration-mode", choices=["SOLO", "TEAM"], default="TEAM")
    gitops_advise.add_argument("--include-bootstrap-plan", action="store_true")
    gitops_advise.add_argument("--repo-name", default="CogniSpace")
    gitops_advise.add_argument("--remote-url", default=None)
    gitops_advise.add_argument("--output-json", action="store_true")
    gitops_advise.set_defaults(handler=_run_gitops_advise, requires_runtime=True)

    gitops_meta_plan = gitops_sub.add_parser("meta-plan")
    gitops_meta_plan.add_argument("--objective", required=True)
    gitops_meta_plan.add_argument("--repo-name", default="CogniSpace")
    gitops_meta_plan.add_argument("--risk-level", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
    gitops_meta_plan.add_argument("--meta-squared", choices=["OFF", "PATCH"], default="PATCH")
    gitops_meta_plan.add_argument("--no-hf-scan", action="store_true")
    gitops_meta_plan.add_argument("--output-json", action="store_true")
    gitops_meta_plan.set_defaults(handler=_run_gitops_meta_plan, requires_runtime=True)

    gitops_handoff = gitops_sub.add_parser("handoff")
    gitops_handoff.add_argument("--objective", required=True)
    gitops_handoff.add_argument("--repo-name", default="CogniSpace")
    gitops_handoff.add_argument("--risk-level", choices=["LOW", "MEDIUM", "HIGH"], default="HIGH")
    gitops_handoff.add_argument("--meta-squared", choices=["OFF", "PATCH"], default="PATCH")
    gitops_handoff.add_argument("--execute", action="store_true")
    gitops_handoff.add_argument("--no-run-tests", action="store_true")
    gitops_handoff.add_argument(
        "--test-command",
        default="python -m pytest tests/test_gitops_api.py tests/test_gitops_mocking.py tests/test_cli.py -q",
    )
    gitops_handoff.add_argument("--pathspec", action="append", default=[])
    gitops_handoff.add_argument("--no-push-branch", action="store_true")
    gitops_handoff.add_argument("--create-pr", action="store_true")
    gitops_handoff.add_argument("--include-bootstrap", action="store_true")
    gitops_handoff.add_argument("--bootstrap-repo", default=None)
    gitops_handoff.add_argument("--resource-group", default=None)
    gitops_handoff.add_argument("--location", default="eastus")
    gitops_handoff.add_argument("--acr-name", default=None)
    gitops_handoff.add_argument("--container-app-environment", default="cae-cognispace-dev")
    gitops_handoff.add_argument("--container-app-name", default="ca-cognispace-backend")
    gitops_handoff.add_argument("--static-web-app-name", default="swa-cognispace-frontend")
    gitops_handoff.add_argument("--deploy-database-url", default="sqlite+pysqlite:////tmp/cognispace.db")
    gitops_handoff.add_argument("--trigger-workflows", action="store_true")
    gitops_handoff.add_argument("--output-json", action="store_true")
    gitops_handoff.set_defaults(handler=_run_gitops_handoff, requires_runtime=True)

    gitops_pr_open = gitops_sub.add_parser("pr-open")
    gitops_pr_open.add_argument("--base", default="main")
    gitops_pr_open.add_argument("--head", default=None)
    gitops_pr_open.add_argument("--repo", default=None)
    gitops_pr_open.add_argument("--title", default=None)
    gitops_pr_open.add_argument("--body", default=None)
    gitops_pr_open.add_argument("--draft", action="store_true")
    gitops_pr_open.add_argument("--output-json", action="store_true")
    gitops_pr_open.set_defaults(handler=_run_gitops_pr_open, requires_runtime=False)

    gitops_ship = gitops_sub.add_parser("ship")
    gitops_ship.add_argument("--objective", required=True)
    gitops_ship.add_argument("--repo-name", default="CogniSpace")
    gitops_ship.add_argument("--risk-level", choices=["LOW", "MEDIUM", "HIGH"], default="HIGH")
    gitops_ship.add_argument("--meta-squared", choices=["OFF", "PATCH"], default="PATCH")
    gitops_ship.add_argument("--pathspec", action="append", required=True)
    gitops_ship.add_argument("--no-run-tests", action="store_true")
    gitops_ship.add_argument(
        "--test-command",
        default="python -m pytest tests/test_gitops_api.py tests/test_gitops_mocking.py tests/test_cli.py -q",
    )
    gitops_ship.add_argument("--no-push-branch", action="store_true")
    gitops_ship.add_argument("--include-bootstrap", action="store_true")
    gitops_ship.add_argument("--bootstrap-repo", default=None)
    gitops_ship.add_argument("--resource-group", default=None)
    gitops_ship.add_argument("--location", default="eastus")
    gitops_ship.add_argument("--acr-name", default=None)
    gitops_ship.add_argument("--container-app-environment", default="cae-cognispace-dev")
    gitops_ship.add_argument("--container-app-name", default="ca-cognispace-backend")
    gitops_ship.add_argument("--static-web-app-name", default="swa-cognispace-frontend")
    gitops_ship.add_argument("--deploy-database-url", default="sqlite+pysqlite:////tmp/cognispace.db")
    gitops_ship.add_argument("--trigger-workflows", action="store_true")
    gitops_ship.add_argument("--base", default="main")
    gitops_ship.add_argument("--head", default=None)
    gitops_ship.add_argument("--repo", default=None)
    gitops_ship.add_argument("--title", default=None)
    gitops_ship.add_argument("--body", default=None)
    gitops_ship.add_argument("--draft", action="store_true")
    gitops_ship.add_argument("--output-json", action="store_true")
    gitops_ship.set_defaults(handler=_run_gitops_ship, requires_runtime=True)

    gitops_sync_main = gitops_sub.add_parser("sync-main")
    gitops_sync_main.add_argument("--main-branch", default="main")
    gitops_sync_main.add_argument("--remote", default="origin")
    gitops_sync_main.add_argument("--prune", action="store_true")
    gitops_sync_main.add_argument("--output-json", action="store_true")
    gitops_sync_main.set_defaults(handler=_run_gitops_sync_main, requires_runtime=False)

    gitops_meta_iterate = gitops_sub.add_parser("meta-iterate")
    gitops_meta_iterate.add_argument("--features-file", default=None)
    gitops_meta_iterate.add_argument("--store-path", default=None)
    gitops_meta_iterate.add_argument("--top-k", type=int, default=3)
    gitops_meta_iterate.add_argument("--reset-store", action="store_true")
    gitops_meta_iterate.add_argument("--autoprompt-run", action="store_true")
    gitops_meta_iterate.add_argument("--autoprompt-execute", action="store_true")
    gitops_meta_iterate.add_argument("--autoprompt-execute-parallel", type=int, default=1)
    gitops_meta_iterate.add_argument("--autoprompt-execute-retries", type=int, default=1)
    gitops_meta_iterate.add_argument("--autoprompt-execute-backoff-ms", type=int, default=250)
    gitops_meta_iterate.add_argument("--execute-max-iterations", type=int, default=3)
    gitops_meta_iterate.add_argument("--execute-max-tokens", type=int, default=5000)
    gitops_meta_iterate.add_argument("--execute-max-cost-usd", type=float, default=1.0)
    gitops_meta_iterate.add_argument("--execute-timeout-seconds", type=int, default=30)
    gitops_meta_iterate.add_argument("--execute-min-similarity", type=float, default=0.25)
    gitops_meta_iterate.add_argument("--output-json", action="store_true")
    gitops_meta_iterate.set_defaults(handler=_run_gitops_meta_iterate, requires_runtime=False)

    return parser


def _execute_handler(
    args: argparse.Namespace,
    runtime: Runtime | None,
    parser: argparse.ArgumentParser,
    *,
    init_error: dict[str, Any] | None = None,
) -> int:
    handler = args.handler
    requires_runtime = bool(getattr(args, "requires_runtime", True))

    if requires_runtime and runtime is None:
        payload = init_error or {
            "status": "error",
            "error_code": "RUNTIME_UNAVAILABLE",
            "message": "Runtime is not initialized. Run 'deps check' and install missing packages.",
        }
        _emit(payload, as_json=bool(getattr(args, "output_json", False)))
        return 2

    if handler is _run_menu:
        return int(handler(args, runtime, parser, init_error=init_error))
    return int(handler(args, runtime))


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    runtime: Runtime | None = None
    init_error: dict[str, Any] | None = None

    command = getattr(args, "command", "")
    requires_runtime = bool(getattr(args, "requires_runtime", True))
    should_try_runtime = requires_runtime or command == "menu"

    if should_try_runtime:
        try:
            runtime = _create_runtime(args)
        except ModuleNotFoundError as exc:
            init_error = _missing_dependency_payload(exc)

    return _execute_handler(args, runtime, parser, init_error=init_error)


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
