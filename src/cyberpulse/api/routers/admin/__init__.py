"""Admin API routers."""

from .sources import router as sources_router
from .jobs import router as jobs_router
from .clients import router as clients_router

__all__ = ["sources_router", "jobs_router", "clients_router"]