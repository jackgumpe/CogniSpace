import logging
from pathlib import Path
from typing import Any

from app.core.config import settings

try:
    import structlog
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    structlog = None


def configure_logging() -> None:
    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
    )

    if structlog is not None:
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )


class _FallbackLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        if kwargs:
            self._logger.log(getattr(logging, level), "%s | %s", message, kwargs)
            return
        self._logger.log(getattr(logging, level), "%s", message)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log("ERROR", message, **kwargs)


logger = (
    structlog.get_logger("llm_workspace")
    if structlog is not None
    else _FallbackLogger("llm_workspace")
)
