"""
API dependencies.

Common dependencies used across API endpoints.
"""
from ..database import get_db
from .auth import get_current_client, require_permissions

# Re-export for centralized dependency access
__all__ = ["get_db", "get_current_client", "require_permissions"]
