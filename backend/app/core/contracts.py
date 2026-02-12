from __future__ import annotations

from pathlib import Path

from jsonschema import Draft202012Validator


class SchemaValidationError(ValueError):
    pass


class ContractValidator:
    """Validates runtime payloads against repository contract schemas."""

    def __init__(self, schema_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        self._schema_dir = schema_dir or root / "contracts" / "schema"
        self._event_validator = self._load_validator("event_envelope.schema.json")
        self._run_validator = self._load_validator("autoprompt_run.schema.json")

    def validate_event(self, payload: dict) -> None:
        self._validate(self._event_validator, payload)

    def validate_autoprompt_run(self, payload: dict) -> None:
        self._validate(self._run_validator, payload)

    def _load_validator(self, schema_name: str) -> Draft202012Validator:
        schema_path = self._schema_dir / schema_name
        schema = self._load_json(schema_path)
        return Draft202012Validator(schema)

    @staticmethod
    def _load_json(path: Path) -> dict:
        import json

        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _validate(validator: Draft202012Validator, payload: dict) -> None:
        errors = sorted(validator.iter_errors(payload), key=str)
        if not errors:
            return

        details = "; ".join(error.message for error in errors[:3])
        raise SchemaValidationError(details)
