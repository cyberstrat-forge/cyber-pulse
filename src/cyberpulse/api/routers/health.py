"""
Health check endpoint.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from ... import __version__
from ...database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(db: Session = Depends(get_db)) -> dict:
    """
    Health check endpoint.

    Returns:
        Status of API and database connections
    """
    # Check database
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except (SQLAlchemyError, DBAPIError) as e:
        # Log the full error for debugging, but don't expose to users
        logger.warning(f"Database health check failed: {e}", exc_info=True)
        db_status = "unhealthy"
    except Exception as e:
        # Unexpected error - log for debugging but return generic message
        logger.error(f"Unexpected error during health check: {e}", exc_info=True)
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": __version__,
        "components": {
            "database": db_status,
            "api": "healthy",
        }
    }
