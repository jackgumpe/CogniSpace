from fastapi import FastAPI
from socketio import ASGIApp, AsyncServer

from app.api.autoprompt import router as autoprompt_router
from app.api.dev_team import router as dev_team_router
from app.api.datasets import router as datasets_router
from app.api.health import router as health_router
from app.api.gitops import router as gitops_router
from app.api.logs import router as logs_router
from app.core.config import settings
from app.core.contracts import ContractValidator
from app.core.logging import configure_logging
from app.services.autoprompt.dev_team import DevTeamOrchestrator
from app.services.autoprompt.drift_guard import DriftGuard
from app.services.autoprompt.engine import AutopromptEngine
from app.services.autoprompt.gitops import GitOpsAdvisor
from app.services.autoprompt.registry import PromptRegistry
from app.services.autoprompt.scoring_profile import ScoringProfileStore
from app.services.dataset.jsonic_builder import JsonicDatasetBuilder
from app.services.dataset.registry import DatasetRegistry
from app.services.logging.analytics import ConversationAnalytics
from app.services.logging.event_store import EventStore

configure_logging()


def create_application(
    *,
    log_dir: str | None = None,
    dataset_dir: str | None = None,
    scoring_profile_path: str | None = None,
) -> tuple[FastAPI, AsyncServer, ASGIApp]:
    app = FastAPI(title="llm-workspace-backend")
    sio = AsyncServer(async_mode="asgi", cors_allowed_origins="*")

    contracts = ContractValidator()
    resolved_log_dir = log_dir or settings.log_dir
    resolved_dataset_dir = dataset_dir or settings.dataset_dir
    resolved_scoring_profile_path = scoring_profile_path or settings.autoprompt_scoring_profile_path
    event_store = EventStore(
        base_dir=resolved_log_dir,
        validator=contracts,
        allow_raw_logs=settings.allow_raw_event_logs,
        redact_payloads=settings.redact_event_payloads,
    )
    prompt_registry = PromptRegistry(validator=contracts)
    scoring_profile_store = ScoringProfileStore(resolved_scoring_profile_path)
    autoprompt_engine = AutopromptEngine(
        prompt_registry,
        drift_guard=DriftGuard(),
        scoring_weights=scoring_profile_store.load_or_default(),
    )
    dev_team_orchestrator = DevTeamOrchestrator()
    gitops_advisor = GitOpsAdvisor()
    dataset_registry = DatasetRegistry()
    log_analytics = ConversationAnalytics()
    jsonic_dataset_builder = JsonicDatasetBuilder(
        event_store=event_store,
        registry=dataset_registry,
        dataset_dir=resolved_dataset_dir,
        allow_raw_dataset_build=settings.allow_raw_dataset_build,
        max_sessions=settings.max_dataset_sessions,
    )

    app.state.sio = sio
    app.state.contracts = contracts
    app.state.event_store = event_store
    app.state.prompt_registry = prompt_registry
    app.state.autoprompt_engine = autoprompt_engine
    app.state.scoring_profile_store = scoring_profile_store
    app.state.dev_team_orchestrator = dev_team_orchestrator
    app.state.gitops_advisor = gitops_advisor
    app.state.log_analytics = log_analytics
    app.state.dataset_registry = dataset_registry
    app.state.jsonic_dataset_builder = jsonic_dataset_builder

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(autoprompt_router, prefix=settings.api_prefix)
    app.include_router(dev_team_router, prefix=settings.api_prefix)
    app.include_router(gitops_router, prefix=settings.api_prefix)
    app.include_router(logs_router, prefix=settings.api_prefix)
    app.include_router(datasets_router, prefix=settings.api_prefix)

    @sio.event
    async def connect(sid: str, environ: dict, auth: dict | None) -> None:
        del sid, environ, auth

    @sio.event
    async def disconnect(sid: str) -> None:
        del sid

    asgi_app = ASGIApp(socketio_server=sio, other_asgi_app=app)
    return app, sio, asgi_app


app, sio, asgi_app = create_application()
