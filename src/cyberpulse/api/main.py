"""
FastAPI application entry point.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI

from ..config import settings
from .. import __version__
from .routers import content, sources, clients, health


def setup_logging() -> None:
    """Configure file logging for the application."""
    if settings.log_file is None:
        return

    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Avoid adding duplicate handlers
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return

    # Create rotating file handler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(log_level)

    # Set format
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


# Setup logging on import
setup_logging()

# Conditionally disable Swagger/OpenAPI docs in production
app = FastAPI(
    title="cyber-pulse API",
    description="Security Intelligence Collection System",
    version=__version__,
    docs_url="/docs" if should_enable_docs() else None,
    redoc_url="/redoc" if should_enable_docs() else None,
    openapi_url="/openapi.json" if should_enable_docs() else None,
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(content.router, prefix="/api/v1", tags=["content"])
app.include_router(sources.router, prefix="/api/v1", tags=["sources"])
app.include_router(clients.router, prefix="/api/v1", tags=["clients"])