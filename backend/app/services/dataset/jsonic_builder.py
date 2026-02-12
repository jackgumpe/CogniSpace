from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import orjson

from app.core.config import settings
from app.models.dataset import (
    BuildDatasetRequest,
    DatasetArtifacts,
    DatasetChecksums,
    DeployDatasetRequest,
    DeployDatasetResponse,
    JsonicDatasetRecord,
)
from app.models.events import EventEnvelope
from app.services.dataset.registry import DatasetRegistry
from app.services.logging.event_store import EventStore


class DatasetBuildError(RuntimeError):
    def __init__(self, code: str, message: str, *, payload: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


class JsonicDatasetBuilder:
    """Builds JSONIC datasets from replayable session logs."""

    def __init__(
        self,
        *,
        event_store: EventStore,
        registry: DatasetRegistry,
        dataset_dir: str | Path | None = None,
        allow_raw_dataset_build: bool = True,
        max_sessions: int = 1000,
    ) -> None:
        self._event_store = event_store
        self._registry = registry
        self._dataset_dir = Path(dataset_dir or settings.dataset_dir)
        self._dataset_dir.mkdir(parents=True, exist_ok=True)
        self._allow_raw_dataset_build = allow_raw_dataset_build
        self._max_sessions = max_sessions

    def build(self, request: BuildDatasetRequest) -> JsonicDatasetRecord:
        if request.raw and not self._allow_raw_dataset_build:
            raise DatasetBuildError("RAW_DATASET_BUILD_DISABLED", "Raw dataset build is disabled.")
        if request.raw and not self._event_store.raw_logs_enabled:
            raise DatasetBuildError("RAW_LOGS_DISABLED", "Raw logs are disabled in event store.")
        if len(request.session_ids) > self._max_sessions:
            raise DatasetBuildError(
                "SESSION_LIMIT_EXCEEDED",
                "Requested sessions exceed build limit.",
                payload={"max_sessions": self._max_sessions},
            )

        dataset_id = f"jsonic_{uuid4().hex[:12]}"
        created_at = datetime.now(UTC)

        unique_session_ids = list(dict.fromkeys(request.session_ids))
        missing_sessions: list[str] = []
        session_events: dict[str, list[EventEnvelope]] = {}

        include_types = set(request.include_event_types)
        for session_id in unique_session_ids:
            events = self._event_store.read_session_events(session_id=session_id, raw=request.raw)
            if include_types:
                events = [event for event in events if event.event_type in include_types]
            if not events:
                missing_sessions.append(session_id)
                continue
            session_events[session_id] = events

        if missing_sessions and not request.allow_partial:
            raise DatasetBuildError(
                "SESSIONS_NOT_FOUND",
                "Some requested sessions were not found or had no matching events.",
                payload={"missing_sessions": missing_sessions},
            )

        if not session_events:
            raise DatasetBuildError("DATASET_EMPTY", "No events available for dataset build.")

        events_path = self._dataset_dir / f"{dataset_id}.events.jsonl"
        conversations_path = self._dataset_dir / f"{dataset_id}.conversations.jsonl"
        manifest_path = self._dataset_dir / f"{dataset_id}.manifest.json"

        event_rows = self._build_event_rows(dataset_id=dataset_id, session_events=session_events, raw=request.raw)
        conversation_rows = self._build_conversation_rows(
            dataset_id=dataset_id,
            session_events=session_events,
            raw=request.raw,
        )
        self._write_jsonl(events_path, event_rows)
        self._write_jsonl(conversations_path, conversation_rows)

        manifest = {
            "dataset_schema": "jsonic_manifest_v1",
            "dataset_id": dataset_id,
            "status": "READY",
            "raw": request.raw,
            "created_at": created_at.isoformat(),
            "session_ids": unique_session_ids,
            "missing_sessions": missing_sessions,
            "event_count": len(event_rows),
            "conversation_count": len(conversation_rows),
            "include_event_types": request.include_event_types,
            "artifacts": {
                "events_path": str(events_path),
                "conversations_path": str(conversations_path),
            },
        }
        self._write_json(manifest_path, manifest)

        record = JsonicDatasetRecord(
            dataset_id=dataset_id,
            status="READY",
            raw=request.raw,
            session_ids=unique_session_ids,
            missing_sessions=missing_sessions,
            created_at=created_at,
            event_count=len(event_rows),
            conversation_count=len(conversation_rows),
            artifacts=DatasetArtifacts(
                events_path=str(events_path),
                conversations_path=str(conversations_path),
                manifest_path=str(manifest_path),
            ),
            checksums=DatasetChecksums(
                events_sha256=self._sha256(events_path),
                conversations_sha256=self._sha256(conversations_path),
                manifest_sha256=self._sha256(manifest_path),
            ),
        )
        return self._registry.save(record)

    def preview(self, *, dataset_id: str, artifact: str, limit: int) -> list[dict]:
        record = self._registry.require(dataset_id)
        if artifact not in {"events", "conversations"}:
            raise DatasetBuildError("INVALID_ARTIFACT", "Artifact must be events or conversations.")
        return self._read_jsonl(record.artifact_path(artifact), limit=limit)

    def deploy(self, *, dataset_id: str, request: DeployDatasetRequest) -> DeployDatasetResponse:
        record = self._registry.require(dataset_id)
        target_dir = Path(request.target_dir).resolve() / dataset_id
        target_dir.mkdir(parents=True, exist_ok=True)

        source_paths = [
            record.artifact_path("events"),
            record.artifact_path("conversations"),
            record.artifact_path("manifest"),
        ]
        copied: list[str] = []
        for source in source_paths:
            if not source.exists():
                raise DatasetBuildError("ARTIFACT_NOT_FOUND", f"Missing artifact: {source}")
            destination = target_dir / source.name
            shutil.copy2(source, destination)
            copied.append(str(destination))

        record.deployment.deployed = True
        record.deployment.target_dir = str(target_dir)
        record.deployment.deployed_at = datetime.now(UTC)
        self._registry.save(record)

        return DeployDatasetResponse(
            dataset_id=dataset_id,
            deployed=True,
            target_dir=str(target_dir),
            copied_files=copied,
        )

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict]) -> None:
        with path.open("wb") as f:
            for row in rows:
                f.write(orjson.dumps(row))
                f.write(b"\n")

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        with path.open("wb") as f:
            f.write(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

    @staticmethod
    def _read_jsonl(path: Path, *, limit: int) -> list[dict]:
        rows: list[dict] = []
        if not path.exists():
            return rows
        with path.open("rb") as f:
            for line in f:
                if not line.strip():
                    continue
                rows.append(orjson.loads(line))
                if len(rows) >= limit:
                    break
        return rows

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _build_event_rows(
        *,
        dataset_id: str,
        session_events: dict[str, list[EventEnvelope]],
        raw: bool,
    ) -> list[dict]:
        rows: list[dict] = []
        global_index = 0
        for session_id in sorted(session_events.keys()):
            for turn_index, event in enumerate(session_events[session_id]):
                rows.append(
                    {
                        "dataset_schema": "jsonic_event_v1",
                        "dataset_id": dataset_id,
                        "raw": raw,
                        "global_index": global_index,
                        "turn_index": turn_index,
                        "session_id": event.session_id,
                        "trace_id": event.trace_id,
                        "event_id": event.event_id,
                        "timestamp_utc": event.timestamp_utc.isoformat(),
                        "actor_id": event.actor_id,
                        "actor_role": event.actor_role,
                        "channel": event.channel,
                        "event_type": event.event_type,
                        "payload": event.payload,
                    }
                )
                global_index += 1
        return rows

    @staticmethod
    def _build_conversation_rows(
        *,
        dataset_id: str,
        session_events: dict[str, list[EventEnvelope]],
        raw: bool,
    ) -> list[dict]:
        rows: list[dict] = []
        for session_id in sorted(session_events.keys()):
            events = session_events[session_id]
            conversation = [
                {
                    "timestamp_utc": event.timestamp_utc.isoformat(),
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "actor_role": event.actor_role,
                    "channel": event.channel,
                    "payload": event.payload,
                }
                for event in events
            ]
            rows.append(
                {
                    "dataset_schema": "jsonic_conversation_v1",
                    "dataset_id": dataset_id,
                    "raw": raw,
                    "session_id": session_id,
                    "trace_ids": sorted({event.trace_id for event in events}),
                    "event_count": len(events),
                    "started_at": events[0].timestamp_utc.isoformat(),
                    "ended_at": events[-1].timestamp_utc.isoformat(),
                    "conversation": conversation,
                }
            )
        return rows
