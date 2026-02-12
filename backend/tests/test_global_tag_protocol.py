from __future__ import annotations

from app.services.autoprompt.global_tags import GlobalTagProtocol


def test_global_tag_protocol_parses_known_tags() -> None:
    parser = GlobalTagProtocol()
    directives = parser.parse(
        (
            "Run with controls "
            "<critical>true</critical>"
            "<agents_required>11</agents_required>"
            "<context_handoff>required</context_handoff>"
            "<utility>schema_linter,security_scan</utility>"
        )
    )

    assert directives.severity == "CRITICAL"
    assert directives.cautious_mode is True
    assert directives.agents_required == 11
    assert directives.context_handoff_required is True
    assert "SCHEMA_LINTER" in directives.required_utilities
    assert "SECURITY_SCAN" in directives.required_utilities


def test_global_tag_protocol_handles_invalid_values() -> None:
    parser = GlobalTagProtocol()
    directives = parser.parse(
        (
            "<agents_required>bad</agents_required>"
            "<min_debate_cycles>bad</min_debate_cycles>"
            "<debate_mode>FAST</debate_mode>"
        )
    )

    assert directives.agents_required == 7
    assert directives.debate_mode_override is None
    assert len(directives.parse_warnings) >= 3
