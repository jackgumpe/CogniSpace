from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "llm-workspace"
    env: str = "dev"
    api_prefix: str = "/api/v1"
    log_dir: str = "logs"
    log_level: str = "INFO"
    # Keep redacted logs by default, but allow raw logs in dev for evaluation datasets.
    redact_event_payloads: bool = True
    allow_raw_event_logs: bool = True
    allow_raw_dataset_build: bool = True
    dataset_dir: str = "datasets"
    max_dataset_sessions: int = 1000
    autoprompt_scoring_profile_path: str = "config/autoprompt_scoring_profile.json"

    # Phase-1 defaults
    optimizer_max_iterations: int = 6
    optimizer_max_tokens: int = 200000
    optimizer_max_cost_usd: float = 3.0
    optimizer_timeout_seconds: int = 600

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
