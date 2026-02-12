from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

import orjson

from app.core.contracts import ContractValidator
from app.core.config import settings
from app.models.events import EventEnvelope


class EventStore:
    """Append-only JSONL storage for Phase-1 global/local logging."""

    _SENSITIVE_KEY_NAMES = {
        "password",
        "passphrase",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "authorization",
        "access_token",
        "refresh_token",
        "bearer_token",
        "private_key",
    }
    _VALUE_SECRET_PATTERNS = [
        re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
        re.compile(r"(?i)sk-[a-z0-9]{12,}"),
        re.compile(r"(?i)(api[_-]?key|password|secret)\s*[:=]\s*[\w\-]+"),
    ]

    def __init__(
        self,
        base_dir: str | None = None,
        *,
        validator: ContractValidator | None = None,
        allow_raw_logs: bool = False,
        redact_payloads: bool = True,
    ) -> None:
        self.base_dir = Path(base_dir or settings.log_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._validator = validator
        self._lock = RLock()
        self._allow_raw_logs = allow_raw_logs
        self._redact_payloads = redact_payloads

    @property
    def raw_logs_enabled(self) -> bool:
        return self._allow_raw_logs

    def append_event(self, event: EventEnvelope) -> EventEnvelope:
        sanitized = self._sanitize_event(event) if self._redact_payloads else event
        self.append_global(sanitized, raw=False)
        self.append_session(sanitized.session_id, sanitized, raw=False)
        if self._allow_raw_logs:
            self.append_global(event, raw=True)
            self.append_session(event.session_id, event, raw=True)
        return sanitized

    def append_global(self, event: EventEnvelope, *, raw: bool = False) -> None:
        suffix = ".raw" if raw else ""
        self._append(f"global_events{suffix}.jsonl", event)

    def append_session(self, session_id: str, event: EventEnvelope, *, raw: bool = False) -> None:
        suffix = ".raw" if raw else ""
        self._append(f"session_{session_id}{suffix}.jsonl", event)

    def get_session_summary(self, *, session_id: str, raw: bool = False) -> dict[str, Any]:
        events = self.read_session_events(session_id=session_id, raw=raw)
        if not events:
            return {
                "session_id": session_id,
                "count": 0,
                "first_ts": None,
                "last_ts": None,
                "actors": [],
                "channels": [],
            }

        return {
            "session_id": session_id,
            "count": len(events),
            "first_ts": events[0].timestamp_utc.isoformat(),
            "last_ts": events[-1].timestamp_utc.isoformat(),
            "actors": sorted({event.actor_id for event in events}),
            "channels": sorted({event.channel for event in events}),
        }

    def replay_session_events(
        self,
        *,
        session_id: str,
        since_event_id: str | None,
        limit: int,
        offset: int,
        raw: bool = False,
    ) -> dict[str, Any]:
        events = self.read_session_events(session_id=session_id, raw=raw)
        source = events
        if since_event_id is not None:
            try:
                anchor_idx = next(
                    idx for idx, event in enumerate(events) if event.event_id == since_event_id
                )
            except StopIteration as exc:
                raise KeyError(since_event_id) from exc
            source = events[anchor_idx + 1 :]

        total_after_since = len(source)
        sliced = source[offset : offset + limit]
        next_offset = offset + len(sliced)
        if next_offset >= total_after_since:
            next_offset = None

        serialized = []
        for seq, event in enumerate(sliced, start=offset):
            row = event.model_dump(mode="json")
            row["sequence"] = seq
            serialized.append(row)

        return {
            "session_id": session_id,
            "since_event_id": since_event_id,
            "offset": offset,
            "limit": limit,
            "next_offset": next_offset,
            "total_after_since": total_after_since,
            "events": serialized,
        }

    def read_session_events(self, *, session_id: str, raw: bool = False) -> list[EventEnvelope]:
        suffix = ".raw" if raw else ""
        return self._read_events(f"session_{session_id}{suffix}.jsonl")

    def list_session_ids(self, *, raw: bool = False) -> list[str]:
        pattern = "session_*.raw.jsonl" if raw else "session_*.jsonl"
        ids: set[str] = set()
        raw_suffix = ".raw.jsonl"
        clean_suffix = ".jsonl"

        for path in self.base_dir.glob(pattern):
            name = path.name
            if not name.startswith("session_"):
                continue
            if raw:
                if not name.endswith(raw_suffix):
                    continue
                session_id = name[len("session_") : -len(raw_suffix)]
            else:
                if name.endswith(raw_suffix) or not name.endswith(clean_suffix):
                    continue
                session_id = name[len("session_") : -len(clean_suffix)]
            if session_id:
                ids.add(session_id)
        return sorted(ids)

    def _read_events(self, filename: str) -> list[EventEnvelope]:
        path = self.base_dir / filename
        if not path.exists():
            return []

        events: list[EventEnvelope] = []
        with path.open("rb") as f:
            for line in f:
                if not line.strip():
                    continue
                data = orjson.loads(line)
                events.append(EventEnvelope.model_validate(data))

        return sorted(events, key=lambda row: (row.timestamp_utc, row.event_id))

    def _append(self, filename: str, event: EventEnvelope) -> None:
        data = event.model_dump(mode="json")
        data.setdefault("timestamp_utc", datetime.now(UTC).isoformat())
        if self._validator is not None:
            self._validator.validate_event(data)

        path = self.base_dir / filename
        with self._lock, path.open("ab") as f:
            f.write(orjson.dumps(data))
            f.write(b"\n")

    def _sanitize_event(self, event: EventEnvelope) -> EventEnvelope:
        sanitized_payload = self._redact_payload(event.payload)
        return event.model_copy(update={"payload": sanitized_payload})

    def _redact_payload(self, value: Any, key_name: str | None = None) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                if self._is_sensitive_key(key):
                    redacted[key] = "[REDACTED]"
                    continue
                redacted[key] = self._redact_payload(item, key_name=key)
            return redacted

        if isinstance(value, list):
            return [self._redact_payload(item, key_name=key_name) for item in value]

        if isinstance(value, str):
            if key_name is not None and self._is_sensitive_key(key_name):
                return "[REDACTED]"
            redacted_value = value
            for pattern in self._VALUE_SECRET_PATTERNS:
                redacted_value = pattern.sub("[REDACTED]", redacted_value)
            return redacted_value

        return value

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        normalized = key.lower().strip()
        return normalized in cls._SENSITIVE_KEY_NAMES
