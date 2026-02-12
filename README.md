# llm-workspace

Phase-1 scaffold for:
1. Autoprompting subsystem
2. Global/local conversation logging

## Top-level layout
- `contracts/schema`: canonical JSON schemas (single source of truth)
- `backend`: FastAPI + Socket.IO services
- `frontend`: React + TypeScript shell
- `ops`: docker + migration artifacts
- `docs/adr`: architecture decisions

## Current status
- Repo scaffolded
- Backend dependency manifest added
- Frontend dependency manifest added
- Core event schema placeholders added

## Next implementation target
- Build `autoprompt` service loop and replayable event ledger before orchestration/UI.
