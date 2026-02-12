from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CorrectionDecision:
    should_autoprompt: bool
    severity: str
    action_code: str
    summary: str
    corrective_steps: list[str]
    generated_prompt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_autoprompt": self.should_autoprompt,
            "severity": self.severity,
            "action_code": self.action_code,
            "summary": self.summary,
            "corrective_steps": self.corrective_steps,
            "generated_prompt": self.generated_prompt,
        }


class CorrectionAgent:
    """Global deterministic error-correction policy with auto-prompt generation."""

    def analyze_exception(self, *, error_type: str, message: str, context: dict[str, Any] | None = None) -> CorrectionDecision:
        context = context or {}
        lowered = f"{error_type} {message}".lower()

        if "modulenotfounderror" in lowered:
            missing = context.get("missing_module") or self._extract_missing_module(message)
            return self._missing_dependency_decision(missing_module=missing)

        if "multiple top-level packages discovered in a flat-layout" in lowered:
            return self._setuptools_discovery_decision()

        if "getting requirements to build editable" in lowered and "subprocess-exited-with-error" in lowered:
            return self._editable_build_failure_decision()

        return self._generic_runtime_decision(error_type=error_type, message=message)

    @staticmethod
    def _extract_missing_module(message: str) -> str:
        marker = "No module named"
        if marker not in message:
            return "unknown"
        parts = message.split("'")
        if len(parts) >= 2:
            return parts[-2]
        return "unknown"

    def _missing_dependency_decision(self, *, missing_module: str) -> CorrectionDecision:
        steps = [
            "cd C:\\Dev\\llm-workspace\\backend",
            ".\\.venv\\Scripts\\Activate.ps1",
            "pip install -e .[dev]",
            "python -m app.cli deps check --output-json",
        ]
        prompt = (
            "You are the Error-Correction Agent. "
            f"Detected missing dependency module `{missing_module}`. "
            "Generate a minimal repair plan that restores runtime imports, "
            "adds/updates dependency tests, and validates with CLI dependency preflight."
        )
        return CorrectionDecision(
            should_autoprompt=True,
            severity="HIGH",
            action_code="DEPENDENCY_REPAIR",
            summary=f"Missing dependency: {missing_module}.",
            corrective_steps=steps,
            generated_prompt=prompt,
        )

    def _setuptools_discovery_decision(self) -> CorrectionDecision:
        steps = [
            "Edit pyproject.toml to pin package discovery to app*.",
            "Add [build-system] and [tool.setuptools.packages.find] if missing.",
            "Re-run pip install -e .[dev].",
            "Run python -m pytest tests -q.",
        ]
        prompt = (
            "You are the Error-Correction Agent. "
            "Setuptools package discovery failed due to multiple top-level directories. "
            "Create a patch that scopes discovery to app* only and add a regression test/check."
        )
        return CorrectionDecision(
            should_autoprompt=True,
            severity="HIGH",
            action_code="PACKAGING_DISCOVERY_FIX",
            summary="Editable build failed due to flat-layout package discovery.",
            corrective_steps=steps,
            generated_prompt=prompt,
        )

    def _editable_build_failure_decision(self) -> CorrectionDecision:
        steps = [
            "Capture full pip error output.",
            "Apply targeted pyproject build/discovery fix.",
            "Retry pip install -e .[dev].",
            "Run dependency preflight and tests.",
        ]
        prompt = (
            "You are the Error-Correction Agent. "
            "Editable build failed. Infer whether the issue is dependency, packaging discovery, or build backend config. "
            "Generate a minimal-risk corrective patch and required verification commands."
        )
        return CorrectionDecision(
            should_autoprompt=True,
            severity="HIGH",
            action_code="EDITABLE_BUILD_REPAIR",
            summary="Editable build process failed and requires controlled correction.",
            corrective_steps=steps,
            generated_prompt=prompt,
        )

    def _generic_runtime_decision(self, *, error_type: str, message: str) -> CorrectionDecision:
        steps = [
            "Capture traceback and command context.",
            "Classify error into dependency/config/runtime domain.",
            "Create focused fix and add regression test.",
            "Validate with relevant CLI/API command.",
        ]
        prompt = (
            "You are the Error-Correction Agent. "
            f"Classify and repair runtime error {error_type}: {message}. "
            "Output a minimal patch plan with validation checklist."
        )
        return CorrectionDecision(
            should_autoprompt=True,
            severity="MEDIUM",
            action_code="GENERAL_RUNTIME_REPAIR",
            summary=f"Runtime issue detected: {error_type}.",
            corrective_steps=steps,
            generated_prompt=prompt,
        )
