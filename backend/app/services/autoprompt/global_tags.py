from __future__ import annotations

import re
from collections import defaultdict

from app.models.dev_team import GlobalProtocolDirectives


class GlobalTagProtocol:
    """Parses global XML-like control tags from freeform task text."""

    _TAG_PATTERN = re.compile(r"<(?P<tag>[a-z_]+)>(?P<value>.*?)</(?P=tag)>", re.IGNORECASE | re.DOTALL)
    _TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "required"}
    _FALSE_VALUES = {"0", "false", "no", "off", "disabled", "optional"}

    def parse(self, text: str) -> GlobalProtocolDirectives:
        directives = GlobalProtocolDirectives()
        if "<" not in text or ">" not in text:
            return directives

        tags = self._extract_tags(text)
        if not tags:
            return directives

        directives.raw_tags = {tag: values[-1] for tag, values in tags.items()}
        directives.required_utilities = []

        if self._as_bool(tags.get("critical", [""])[-1]):
            directives.severity = "CRITICAL"
            directives.cautious_mode = True
            directives.debate_mode_override = "SYNC"
            directives.min_debate_cycles = max(directives.min_debate_cycles, 3)
            directives.requires_supervisor_approval = True
            directives.required_utilities.extend(
                [
                    "RISK_REVIEW",
                    "FAILSAFE_CHECKLIST",
                    "ROLLBACK_PLAN",
                    "ESCALATION_AUDIT_LOG",
                ]
            )

        if self._as_bool(tags.get("cautious", [""])[-1]):
            if directives.severity != "CRITICAL":
                directives.severity = "CAUTIOUS"
            directives.cautious_mode = True
            directives.min_debate_cycles = max(directives.min_debate_cycles, 2)
            directives.required_utilities.extend(["RISK_REVIEW", "ASSUMPTION_TRACKER"])

        if "agents_required" in tags:
            agents_value = tags["agents_required"][-1].strip()
            try:
                requested = int(agents_value)
            except ValueError:
                directives.parse_warnings.append(
                    f"agents_required must be integer; received '{agents_value}'. Using default=7."
                )
            else:
                if requested < 7:
                    directives.parse_warnings.append(
                        f"agents_required={requested} is below minimum team size 7; clamped to 7."
                    )
                    requested = 7
                if requested > 20:
                    directives.parse_warnings.append(
                        f"agents_required={requested} exceeds cap 20; clamped to 20."
                    )
                    requested = 20
                directives.agents_required = requested

        if "debate_mode" in tags:
            mode = tags["debate_mode"][-1].strip().upper()
            if mode in {"SYNC", "ASYNC", "MIXED"}:
                directives.debate_mode_override = mode  # type: ignore[assignment]
            else:
                directives.parse_warnings.append(
                    f"debate_mode must be SYNC|ASYNC|MIXED; received '{mode}'."
                )

        if "context_handoff" in tags:
            directives.context_handoff_required = self._as_bool(tags["context_handoff"][-1])

        if "supervisor_approval" in tags:
            directives.requires_supervisor_approval = self._as_bool(tags["supervisor_approval"][-1])

        if "min_debate_cycles" in tags:
            value = tags["min_debate_cycles"][-1].strip()
            try:
                cycles = int(value)
            except ValueError:
                directives.parse_warnings.append(
                    f"min_debate_cycles must be integer; received '{value}'."
                )
            else:
                directives.min_debate_cycles = max(1, min(8, cycles))

        if "utility" in tags:
            utilities = []
            for value in tags["utility"]:
                for token in re.split(r"[,\n]", value):
                    item = token.strip().upper()
                    if item:
                        utilities.append(item)
            directives.required_utilities.extend(utilities)

        directives.required_utilities = sorted(set(directives.required_utilities))
        return directives

    def _extract_tags(self, text: str) -> dict[str, list[str]]:
        values: dict[str, list[str]] = defaultdict(list)
        for match in self._TAG_PATTERN.finditer(text):
            tag = match.group("tag").strip().lower()
            value = match.group("value").strip()
            values[tag].append(value)
        return values

    def _as_bool(self, value: str) -> bool:
        normalized = value.strip().lower()
        if normalized in self._TRUE_VALUES:
            return True
        if normalized in self._FALSE_VALUES:
            return False
        return normalized != ""
