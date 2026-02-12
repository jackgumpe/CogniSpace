from dataclasses import dataclass


@dataclass
class Budget:
    max_iterations: int
    max_tokens: int
    max_cost_usd: float
    timeout_seconds: int


class AutopromptService:
    """Phase-1 placeholder service. Real optimization loop lands next."""

    def run_once(self, task_key: str, baseline_prompt: str, budget: Budget) -> dict[str, str]:
        return {
            "task_key": task_key,
            "status": "PENDING_IMPLEMENTATION",
            "note": "Optimization loop to be implemented in Phase-1 coding step.",
        }
