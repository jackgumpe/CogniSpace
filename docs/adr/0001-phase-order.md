# ADR 0001: Phase Order

Status: Accepted

Decision:
- Build autoprompting and global/local logging first.
- Defer cross-LLM orchestration and UI complexity until contracts + telemetry are stable.

Rationale:
- Prevents context drift and debugging blind spots.
- Establishes measurable quality gates before scaling system complexity.
