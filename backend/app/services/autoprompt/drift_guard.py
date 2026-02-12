from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.models.autoprompt import DriftConstraints


class DriftGuard:
    """Rejects candidates that drift from hard constraints or baseline semantics."""

    def validate(
        self,
        *,
        baseline_prompt: str,
        candidate_prompt: str,
        constraints: DriftConstraints,
    ) -> tuple[bool, str | None]:
        candidate_lower = candidate_prompt.lower()

        for keyword in constraints.required_keywords:
            if keyword.lower() not in candidate_lower:
                return False, f"missing required keyword: {keyword}"

        for pattern in constraints.forbidden_patterns:
            if re.search(pattern, candidate_prompt, flags=re.IGNORECASE):
                return False, f"forbidden pattern matched: {pattern}"

        similarity = SequenceMatcher(
            a=baseline_prompt.lower().strip(),
            b=candidate_prompt.lower().strip(),
        ).ratio()
        if similarity < constraints.min_similarity:
            return False, f"similarity {similarity:.3f} below minimum {constraints.min_similarity:.3f}"

        return True, None
