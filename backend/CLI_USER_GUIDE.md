# CogniSpace Backend CLI User Guide (Windows)

## 1) Where To Run It
- Open **PowerShell** or **Command Prompt**.
- Change directory to:
  - `C:\Dev\llm-workspace\backend`
- Activate your virtual env if needed:
  - `.\.venv\Scripts\Activate.ps1`

Why this directory:
- `python -m app.cli ...` expects the `app` package in the current backend project.

## 2) Start DOS Menu Mode
- Run:
  - `python -m app.cli menu`
- You will see:
  - `COGNISPACE BACKEND CLI (DOS MENU)`
  - prompt: `COGNISPACE>`

In menu mode:
- `HELP` shows command list.
- `WHERE` shows active log/scoring profile paths.
- `DEPS CHECK` verifies installed Python dependencies.
- `TEAM GATHER-DEFAULT --OUTPUT-JSON` gathers and validates default 6+1 team process.
- `TEAM VALIDATE-DEFAULT --OUTPUT-JSON` checks default team governance health.
- `CLS` clears screen.
- `EXIT` quits menu mode.

## 3) Quick Commands (Direct Mode)
- Health check:
  - `python -m app.cli health --output-json`
- List sessions:
  - `python -m app.cli logs sessions --output-json`
- Session summary:
  - `python -m app.cli logs summary --session-id sess_123 --output-json`
- Replay logs:
  - `python -m app.cli logs replay --session-id sess_123 --limit 50 --output-json`
- Session analytics:
  - `python -m app.cli logs analyze --session-id sess_123 --output-json`
- Global analytics:
  - `python -m app.cli logs global-analysis --limit-sessions 50 --output-json`
- Dependency preflight:
  - `python -m app.cli deps check --output-json`
- Gather default dev team process:
  - `python -m app.cli team gather-default --output-json`
- Validate default dev team process:
  - `python -m app.cli team validate-default --output-json`
- Run autoprompt:
  - `python -m app.cli autoprompt run --task-key t1 --prompt "Return JSON output with MUST constraints." --output-json`

## 4) Metric Tuning Commands
- Show active scoring profile:
  - `python -m app.cli autoprompt metrics show --output-json`
- Tune scoring weights:
  - `python -m app.cli autoprompt metrics set --json-bonus 0.25 --must-bonus 0.2 --output-json`
- Reset scoring weights:
  - `python -m app.cli autoprompt metrics reset --output-json`
- Preview score impact:
  - `python -m app.cli autoprompt metrics score-preview --task-key t1 --prompt "Return JSON output." --output-json`

Scoring profile persistence:
- Default file:
  - `backend\config\autoprompt_scoring_profile.json`
- Override path:
  - add `--scoring-profile-path <path>` to any command.

## 5) Optional Installed Command
After `pip install -e .[dev]` in `backend`, you can use:
- `cogni-backend menu`
- `cogni-backend help`

## 6) Troubleshooting
- `ModuleNotFoundError: app`:
  - You are not in `C:\Dev\llm-workspace\backend` (or package not installed).
- `ModuleNotFoundError: jsonschema` or similar:
  - Run `python -m app.cli deps check --output-json`.
  - Activate `.venv` and run `pip install -e .[dev]`.
- Empty session list:
  - No events written yet in selected `--log-dir`.
- Want custom data location:
  - pass `--log-dir`, `--dataset-dir`, and `--scoring-profile-path`.
