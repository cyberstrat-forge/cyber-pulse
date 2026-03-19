"""
Health check endpoint.
"""
import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

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
        logger.warning(f"Database health check failed: {e}")
        db_status = f"unhealthy: {e}"
    except Exception as e:
        # Unexpected error - log at error level and re-raise
        logger.error(f"Unexpected error during health check: {e}")
        raise

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "version": "0.1.0",
        "components": {
            "database": db_status,
            "api": "healthy",
        }
    }