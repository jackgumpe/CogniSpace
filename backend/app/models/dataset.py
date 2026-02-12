from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DatasetStatus = Literal["READY", "FAILED"]


class BuildDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ids: list[str] = Field(min_length=1)
    raw: bool = True
    include_event_types: list[str] = Field(default_factory=list)
    allow_partial: bool = False

    @field_validator("session_ids")
    @classmethod
    def _non_empty_ids(cls, session_ids: list[str]) -> list[str]:
        cleaned = [item.strip() for item in session_ids if item.strip()]
        if not cleaned:
            raise ValueError("session_ids must include at least one non-empty id")
        return cleaned


class DatasetArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events_path: str
    conversations_path: str
    manifest_path: str


class DatasetChecksums(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events_sha256: str
    conversations_sha256: str
    manifest_sha256: str


class DeploymentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployed: bool = False
    target_dir: str | None = None
    deployed_at: datetime | None = None


class JsonicDatasetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    status: DatasetStatus
    raw: bool
    session_ids: list[str]
    missing_sessions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_count: int
    conversation_count: int
    artifacts: DatasetArtifacts
    checksums: DatasetChecksums
    deployment: DeploymentInfo = Field(default_factory=DeploymentInfo)

    def artifact_path(self, artifact: Literal["events", "conversations", "manifest"]) -> Path:
        mapping = {
            "events": self.artifacts.events_path,
            "conversations": self.artifacts.conversations_path,
            "manifest": self.artifacts.manifest_path,
        }
        return Path(mapping[artifact])


class DatasetPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    artifact: Literal["events", "conversations"]
    limit: int
    rows: list[dict[str, Any]]


class DeployDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_dir: str = Field(min_length=1)


class DeployDatasetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    deployed: bool
    target_dir: str
    copied_files: list[str]
