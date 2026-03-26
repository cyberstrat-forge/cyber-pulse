"""
FastAPI application entry point.
"""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..config import settings
from .. import __version__
from .routers import content, health, items
from .routers.admin import sources_router, jobs_router, clients_router, logs_router, diagnose_router
from .startup import ensure_admin_client


class UnicodeJSONResponse(JSONResponse):
    """JSON response that preserves Unicode characters."""

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


def setup_logging() -> None:
    """Configure file logging for the application."""
    if settings.log_file is None:
        return

    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(log_level)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)


def should_enable_docs() -> bool:
    """Determine if API docs should be enabled based on environment."""
    is_production = settings.environment.lower() in ("production", "prod")
    return not is_production


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    setup_logging()
    ensure_admin_client()
    yield


# Setup logging on import
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="cyber-pulse API",
    description="Security Intelligence Collection System",
    version=__version__,
    default_response_class=UnicodeJSONResponse,
    docs_url="/docs" if should_enable_docs() else None,
    redoc_url="/redoc" if should_enable_docs() else None,
    openapi_url="/openapi.json" if should_enable_docs() else None,
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router, tags=["health"])

# Business API
app.include_router(items.router, prefix="/api/v1", tags=["items"])
app.include_router(content.router, prefix="/api/v1", tags=["content"])

# Admin API (new endpoints)
app.include_router(sources_router, prefix="/api/v1/admin", tags=["admin-sources"])
app.include_router(jobs_router, prefix="/api/v1/admin", tags=["admin-jobs"])
app.include_router(clients_router, prefix="/api/v1/admin", tags=["admin-clients"])
app.include_router(logs_router, prefix="/api/v1/admin", tags=["admin-logs"])
app.include_router(diagnose_router, prefix="/api/v1/admin", tags=["admin-diagnose"])