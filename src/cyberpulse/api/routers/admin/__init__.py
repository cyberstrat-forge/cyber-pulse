"""Admin API routers."""

from .clients import router as clients_router
from .diagnose import router as diagnose_router
from .jobs import router as jobs_router
from .logs import router as logs_router
from .sources import router as sources_router

__all__ = ["sources_router", "jobs_router", "clients_router", "logs_router", "diagnose_router"]
