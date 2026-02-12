from __future__ import annotations

from pathlib import Path

import orjson

from app.models.autoprompt import AutopromptScoringWeights


class ScoringProfileStore:
    """Persistence for autoprompt scoring profile used by CLI and app bootstrap."""

    def __init__(self, profile_path: str | Path) -> None:
        self._profile_path = Path(profile_path)

    @property
    def profile_path(self) -> Path:
        return self._profile_path

    def load(self) -> AutopromptScoringWeights:
        if not self._profile_path.exists():
            return AutopromptScoringWeights()

        with self._profile_path.open("rb") as f:
            payload = orjson.loads(f.read())
        return AutopromptScoringWeights.model_validate(payload)

    def load_or_default(self) -> AutopromptScoringWeights:
        try:
            return self.load()
        except Exception:
            return AutopromptScoringWeights()

    def save(self, weights: AutopromptScoringWeights) -> None:
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        with self._profile_path.open("wb") as f:
            f.write(orjson.dumps(weights.model_dump(mode="json")))
