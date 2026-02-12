from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from app.core.contracts import ContractValidator
from app.models.autoprompt import (
    AutopromptRunRecord,
    CreateAutopromptRunRequest,
    PromptCandidate,
    PromptVersionRecord,
)


class PromptRegistry:
    """In-memory registry for phase-1 runs and prompt versions."""

    def __init__(self, *, validator: ContractValidator | None = None) -> None:
        self._lock = RLock()
        self._runs: dict[str, AutopromptRunRecord] = {}
        self._prompt_versions: dict[str, PromptVersionRecord] = {}
        self._active_prompts: dict[str, str] = {}
        self._validator = validator

    def create_run(self, payload: CreateAutopromptRunRequest) -> AutopromptRunRecord:
        now = datetime.now(UTC)
        run_id = f"run_{uuid4().hex[:12]}"
        baseline_prompt_version = f"pv_{uuid4().hex[:12]}"
        session_id = payload.session_id or f"sess_{uuid4().hex[:10]}"
        trace_id = payload.trace_id or f"trace_{uuid4().hex[:10]}"

        run = AutopromptRunRecord(
            run_id=run_id,
            task_key=payload.task_key,
            status="PENDING",
            created_at=now,
            baseline_prompt_version=baseline_prompt_version,
            budget=payload.budget,
            session_id=session_id,
            trace_id=trace_id,
            baseline_prompt=payload.baseline_prompt,
            constraints=payload.constraints,
        )
        self._validate_run_contract(run)

        baseline_version = PromptVersionRecord(
            prompt_version=baseline_prompt_version,
            run_id=run_id,
            task_key=payload.task_key,
            prompt_text=payload.baseline_prompt,
            score=0.0,
            created_at=now,
        )

        with self._lock:
            self._runs[run_id] = run
            self._prompt_versions[baseline_prompt_version] = baseline_version

        return run.model_copy(deep=True)

    def get_run(self, run_id: str) -> AutopromptRunRecord | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            return run.model_copy(deep=True)

    def require_run(self, run_id: str) -> AutopromptRunRecord:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        return run

    def save_run(self, run: AutopromptRunRecord) -> AutopromptRunRecord:
        self._validate_run_contract(run)
        with self._lock:
            self._runs[run.run_id] = run
        return run.model_copy(deep=True)

    def add_candidate(self, *, run_id: str, candidate: PromptCandidate) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(f"run not found: {run_id}")

            run.candidates.append(candidate)
            self._prompt_versions[candidate.prompt_version] = PromptVersionRecord(
                prompt_version=candidate.prompt_version,
                run_id=run_id,
                task_key=run.task_key,
                prompt_text=candidate.prompt_text,
                score=candidate.score,
                created_at=candidate.created_at,
            )
            self._runs[run_id] = run

    def deploy_prompt(self, prompt_version: str) -> tuple[str, bool]:
        with self._lock:
            prompt = self._prompt_versions.get(prompt_version)
            if prompt is None:
                raise KeyError(f"prompt version not found: {prompt_version}")

            current = self._active_prompts.get(prompt.task_key)
            if current == prompt_version:
                return prompt.task_key, True

            self._active_prompts[prompt.task_key] = prompt_version
            return prompt.task_key, False

    def _validate_run_contract(self, run: AutopromptRunRecord) -> None:
        if self._validator is None:
            return
        self._validator.validate_autoprompt_run(run.contract_view())
