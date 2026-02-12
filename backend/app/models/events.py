from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    event_id: str
    parent_event_id: str | None = None
    session_id: str
    trace_id: str
    timestamp_utc: datetime
    actor_id: str
    actor_role: Literal["PM", "LEAD", "DEV", "AUDITOR", "SYSTEM", "USER"]
    channel: Literal["GLOBAL", "LOCAL", "SYSTEM", "AUTOPROMPT"] = "GLOBAL"
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    safety_flags: list[str] = Field(default_factory=list)
    token_in: int = Field(default=0, ge=0)
    token_out: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
