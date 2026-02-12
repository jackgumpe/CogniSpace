from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Awaitable, Callable
from uuid import uuid4

from app.models.autoprompt import (
    AutopromptRunRecord,
    AutopromptScoringWeights,
    DriftConstraints,
    PromptCandidate,
)
from app.services.autoprompt.drift_guard import DriftGuard
from app.services.autoprompt.registry import PromptRegistry

StatusCallback = Callable[[dict], Awaitable[None]]
CandidateCallback = Callable[[PromptCandidate], Awaitable[None]]


class AutopromptEngine:
    """Deterministic phase-1 optimizer using critique -> rewrite -> evaluate loop."""

    def __init__(
        self,
        registry: PromptRegistry,
        drift_guard: DriftGuard | None = None,
        scoring_weights: AutopromptScoringWeights | None = None,
    ) -> None:
        self._registry = registry
        self._drift_guard = drift_guard or DriftGuard()
        self._time_source = time.monotonic
        self._scoring_weights = scoring_weights or AutopromptScoringWeights()

    def get_scoring_weights(self) -> AutopromptScoringWeights:
        return self._scoring_weights.model_copy(deep=True)

    def set_scoring_weights(self, weights: AutopromptScoringWeights) -> AutopromptScoringWeights:
        self._scoring_weights = weights.model_copy(deep=True)
        return self.get_scoring_weights()

    def reset_scoring_weights(self) -> AutopromptScoringWeights:
        self._scoring_weights = AutopromptScoringWeights()
        return self.get_scoring_weights()

    def score_prompt(
        self,
        *,
        task_key: str,
        prompt_text: str,
        constraints: DriftConstraints | None = None,
    ) -> float:
        return self._score_prompt(
            task_key=task_key,
            prompt_text=prompt_text,
            constraints=constraints or DriftConstraints(),
        )

    async def run(
        self,
        run_id: str,
        *,
        on_status: StatusCallback | None = None,
        on_candidate: CandidateCallback | None = None,
    ) -> AutopromptRunRecord:
        run = self._registry.require_run(run_id)
        run.status = "RUNNING"
        run.updated_at = datetime.now(UTC)
        run.budget_usage.started_at = run.updated_at
        self._registry.save_run(run)

        if on_status is not None:
            await on_status({"run_id": run.run_id, "status": run.status})

        started_at = self._time_source()
        termination_reason = "iteration_cap"

        baseline_candidate = self._build_baseline_candidate(run)
        run.budget_usage.tokens_used += baseline_candidate.token_used
        run.budget_usage.cost_used_usd += baseline_candidate.cost_usd

        if run.budget_usage.tokens_used > run.budget.max_tokens:
            termination_reason = "token_cap"
            run.status = "FAILED"
            run.metrics["termination_reason"] = termination_reason
            run.updated_at = datetime.now(UTC)
            run.budget_usage.finished_at = run.updated_at
            self._registry.add_candidate(run_id=run.run_id, candidate=baseline_candidate)
            run.candidates.append(baseline_candidate)
            run.best_candidate = baseline_candidate
            run.best_prompt_version = baseline_candidate.prompt_version
            self._registry.save_run(run)
            return run

        if run.budget_usage.cost_used_usd > run.budget.max_cost_usd:
            termination_reason = "cost_cap"
            run.status = "FAILED"
            run.metrics["termination_reason"] = termination_reason
            run.updated_at = datetime.now(UTC)
            run.budget_usage.finished_at = run.updated_at
            self._registry.add_candidate(run_id=run.run_id, candidate=baseline_candidate)
            run.candidates.append(baseline_candidate)
            run.best_candidate = baseline_candidate
            run.best_prompt_version = baseline_candidate.prompt_version
            self._registry.save_run(run)
            return run

        best_candidate = baseline_candidate.model_copy(deep=True)
        best_candidate.selected = True
        self._registry.add_candidate(run_id=run.run_id, candidate=best_candidate)
        run.candidates.append(best_candidate)
        run.best_candidate = best_candidate
        run.best_prompt_version = best_candidate.prompt_version

        if on_candidate is not None:
            await on_candidate(best_candidate)

        no_improvement_rounds = 0

        for index in range(run.budget.max_iterations):
            if self._time_source() - started_at >= run.budget.timeout_seconds:
                termination_reason = "timeout"
                run.budget_usage.timed_out = True
                break

            critique = self._build_critique(run=run, current_prompt=best_candidate.prompt_text)
            candidate_text = self._rewrite_prompt(
                current_prompt=best_candidate.prompt_text,
                critique=critique,
                iteration=index + 1,
            )
            token_used = self._estimate_tokens(candidate_text)
            cost_used = self._estimate_cost(token_used)

            if run.budget_usage.tokens_used + token_used > run.budget.max_tokens:
                termination_reason = "token_cap"
                break
            if run.budget_usage.cost_used_usd + cost_used > run.budget.max_cost_usd:
                termination_reason = "cost_cap"
                break

            run.budget_usage.iterations_used += 1
            run.budget_usage.tokens_used += token_used
            run.budget_usage.cost_used_usd += cost_used

            is_valid, reject_reason = self._drift_guard.validate(
                baseline_prompt=run.baseline_prompt,
                candidate_prompt=candidate_text,
                constraints=run.constraints,
            )
            score = self._score_prompt(
                task_key=run.task_key,
                prompt_text=candidate_text,
                constraints=run.constraints,
            )
            candidate = PromptCandidate(
                candidate_id=f"cand_{uuid4().hex[:10]}",
                prompt_version=f"pv_{uuid4().hex[:12]}",
                prompt_text=candidate_text,
                critique=critique,
                score=score,
                token_used=token_used,
                cost_usd=cost_used,
                rejected_reason=reject_reason if not is_valid else None,
            )

            if is_valid:
                if candidate.score > best_candidate.score or (
                    candidate.score == best_candidate.score
                    and candidate.token_used < best_candidate.token_used
                ):
                    candidate.selected = True
                    best_candidate.selected = False
                    best_candidate = candidate
                    no_improvement_rounds = 0
                else:
                    no_improvement_rounds += 1
            else:
                no_improvement_rounds += 1

            self._registry.add_candidate(run_id=run.run_id, candidate=candidate)
            run.candidates.append(candidate)

            if on_candidate is not None:
                await on_candidate(candidate)

            if no_improvement_rounds >= 2:
                termination_reason = "plateau"
                break

        run.status = "SUCCEEDED" if run.best_candidate is not None else "FAILED"
        run.updated_at = datetime.now(UTC)
        run.budget_usage.finished_at = run.updated_at
        run.best_candidate = best_candidate
        run.best_prompt_version = best_candidate.prompt_version
        run.metrics = {
            "termination_reason": termination_reason,
            "iterations_completed": run.budget_usage.iterations_used,
            "tokens_used": run.budget_usage.tokens_used,
            "cost_used_usd": round(run.budget_usage.cost_used_usd, 6),
            "best_score": round(best_candidate.score, 6),
            "candidate_count": len(run.candidates),
        }

        self._registry.save_run(run)
        if on_status is not None:
            await on_status({"run_id": run.run_id, "status": run.status, "metrics": run.metrics})
        return run

    def _build_baseline_candidate(self, run: AutopromptRunRecord) -> PromptCandidate:
        token_used = self._estimate_tokens(run.baseline_prompt)
        return PromptCandidate(
            candidate_id=f"cand_{uuid4().hex[:10]}",
            prompt_version=run.baseline_prompt_version,
            prompt_text=run.baseline_prompt,
            critique="baseline",
            score=self._score_prompt(
                task_key=run.task_key,
                prompt_text=run.baseline_prompt,
                constraints=run.constraints,
            ),
            token_used=token_used,
            cost_usd=self._estimate_cost(token_used),
            selected=True,
        )

    @staticmethod
    def _estimate_tokens(prompt_text: str) -> int:
        return max(1, len(prompt_text.split()))

    @staticmethod
    def _estimate_cost(token_count: int) -> float:
        return round(token_count * 0.000001, 6)

    def _build_critique(self, *, run: AutopromptRunRecord, current_prompt: str) -> str:
        notes: list[str] = []
        if "json" not in current_prompt.lower():
            notes.append("Add explicit JSON output constraints.")
        if "must" not in current_prompt.lower():
            notes.append("Use enforceable language with MUST/SHALL requirements.")
        if len(current_prompt.split()) < 40:
            notes.append("Increase precision with concise acceptance checks.")
        if run.constraints.required_keywords:
            missing = [
                key
                for key in run.constraints.required_keywords
                if key.lower() not in current_prompt.lower()
            ]
            if missing:
                # Avoid leaking the literal required keywords into generated candidates.
                notes.append("Ensure all required constraint terms are explicitly satisfied.")
        if not notes:
            notes.append("Improve clarity and reduce ambiguity.")
        return " ".join(notes)

    @staticmethod
    def _rewrite_prompt(*, current_prompt: str, critique: str, iteration: int) -> str:
        return (
            f"{current_prompt.strip()}\n\n"
            f"[Optimization Round {iteration}] {critique}\n"
            "Return deterministic output and satisfy all hard constraints."
        )

    def _score_prompt(
        self,
        *,
        task_key: str,
        prompt_text: str,
        constraints: DriftConstraints,
    ) -> float:
        weights = self._scoring_weights
        text = prompt_text.lower()
        score = weights.base_score

        if "json" in text:
            score += weights.json_bonus
        if "must" in text or "shall" in text:
            score += weights.must_bonus
        score += min(len(prompt_text.split()) / float(weights.length_divisor), weights.length_max_bonus)

        task_tokens = [token for token in task_key.lower().replace("_", " ").split() if token]
        if task_tokens:
            score += min(
                sum(1 for token in task_tokens if token in text)
                / len(task_tokens)
                * weights.task_relevance_max_bonus,
                weights.task_relevance_max_bonus,
            )

        if constraints.required_keywords:
            coverage = sum(
                1 for keyword in constraints.required_keywords if keyword.lower() in text
            ) / max(len(constraints.required_keywords), 1)
            score += coverage * weights.keyword_coverage_max_bonus

        if constraints.forbidden_patterns:
            if any(
                re.search(pattern, prompt_text, flags=re.IGNORECASE)
                for pattern in constraints.forbidden_patterns
            ):
                score -= weights.forbidden_pattern_penalty

        return max(0.0, min(score, 1.0))
