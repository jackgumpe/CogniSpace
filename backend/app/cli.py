from __future__ import annotations

import argparse
import asyncio
import importlib.util
import shlex
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


def _run_autoprompt_run(args: argparse.Namespace, runtime: Runtime) -> int:
    from app.models.autoprompt import BudgetConfig, CreateAutopromptRunRequest, DriftConstraints

    constraints = DriftConstraints(
        required_keywords=args.required_keyword or [],
        forbidden_patterns=args.forbidden_pattern or [],
        min_similarity=args.min_similarity,
    )
    payload = CreateAutopromptRunRequest(
        task_key=args.task_key,
        baseline_prompt=args.prompt,
        session_id=args.session_id,
        trace_id=args.trace_id,
        budget=BudgetConfig(
            max_iterations=args.max_iterations,
            max_tokens=args.max_tokens,
            max_cost_usd=args.max_cost_usd,
            timeout_seconds=args.timeout_seconds,
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
