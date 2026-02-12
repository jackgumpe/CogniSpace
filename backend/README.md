# Backend

Run (dev):
- `python -m venv .venv`
- `.\.venv\Scripts\Activate.ps1`
- `pip install -e .[dev]`
- `uvicorn app.main:asgi_app --reload --port 8000`

Key API groups:
- `/api/v1/autoprompt/*` run lifecycle + deploy.
- `/api/v1/logs/*` replayable global/local logs.
- `/api/v1/datasets/jsonic/*` dataset build/preview/download/deploy.
- `/api/v1/autoprompt/dev-team/plan` create 1+6 team plan with Kanban workflow.
- `/api/v1/autoprompt/dev-team/benchmark` benchmark baseline vs team/meta-autoprompt strategy.
- `/api/v1/autoprompt/dev-team/directives/resolve` parse XML control tags into runtime directives.
- `/api/v1/autoprompt/dev-team/preplan` run preplanning scout agent for upcoming phase cards/risks/handoff packet.
- `/api/v1/gitops/snapshot` inspect git state for branching/commit hygiene.
- `/api/v1/gitops/advise` get multi-agent git recommendations (fork/branch/commit/prune/sync).

CLI (pre-planning/debug):
- `python -m app.cli help`
- `python -m app.cli menu`
- `python -m app.cli deps check --output-json`
- `python -m app.cli health --output-json`
- `python -m app.cli team gather-default --output-json`
- `python -m app.cli team validate-default --output-json`
- `python -m app.cli team preplan --task-key phase2 --task-description "..." --horizon-cards 6 --output-json`
- `python -m app.cli gitops snapshot --output-json`
- `python -m app.cli gitops advise --objective "prepare phase2 commit strategy" --changes-summary "..." --output-json`
- `python -m app.cli logs sessions --output-json`
- `python -m app.cli logs summary --session-id <id> --output-json`
- `python -m app.cli logs replay --session-id <id> --limit 50 --output-json`
- `python -m app.cli logs analyze --session-id <id> --output-json`
- `python -m app.cli logs global-analysis --output-json`
- `python -m app.cli autoprompt run --task-key t1 --prompt "Return JSON output." --output-json`
- `python -m app.cli autoprompt metrics show --output-json`
- `python -m app.cli autoprompt metrics set --json-bonus 0.25 --must-bonus 0.2 --output-json`
- `python -m app.cli autoprompt metrics score-preview --task-key t1 --prompt "..." --output-json`

