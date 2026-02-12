from __future__ import annotations

from app.services.autoprompt.correction_agent import CorrectionAgent


def test_correction_agent_missing_dependency_generates_repair_prompt() -> None:
    agent = CorrectionAgent()
    decision = agent.analyze_exception(
        error_type="ModuleNotFoundError",
        message="No module named 'jsonschema'",
        context={"missing_module": "jsonschema"},
    )
    assert decision.should_autoprompt is True
    assert decision.action_code == "DEPENDENCY_REPAIR"
    assert decision.severity == "HIGH"
    assert "jsonschema" in decision.summary
    assert "pip install -e .[dev]" in decision.corrective_steps
    assert "Error-Correction Agent" in decision.generated_prompt


def test_correction_agent_detects_packaging_discovery_failure() -> None:
    agent = CorrectionAgent()
    decision = agent.analyze_exception(
        error_type="BuildError",
        message="error: Multiple top-level packages discovered in a flat-layout: ['app', 'logs']",
    )
    assert decision.action_code == "PACKAGING_DISCOVERY_FIX"
    assert decision.should_autoprompt is True
    assert any("pyproject.toml" in step for step in decision.corrective_steps)
