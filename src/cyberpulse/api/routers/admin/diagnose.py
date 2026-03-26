"""System diagnose API router for admin endpoints.

Provides system health overview and statistics.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .... import __version__
from ....database import engine
from ....models import Item, Job, JobStatus, Source, SourceStatus
from ...auth import ApiClient, require_permissions
from ...dependencies import get_db
from ...schemas.diagnose import DiagnoseResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def check_database() -> str:
    """Check database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "connected"
    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return "disconnected"


def check_redis() -> str:
    """Check Redis connectivity."""
    try:
        import redis

        from ....config import settings

        if not settings.redis_url:
            return "not_configured"

        r = redis.from_url(settings.redis_url)
        r.ping()
        return "connected"
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
        return "disconnected"


def check_scheduler() -> str:
    """Check scheduler status.

    This is a simplified check. In production, you might check
    if the scheduler process is running.
    """
    # For now, we assume scheduler is active if the service is running
    # A more robust check would query the scheduler's internal state
    return "active"


def get_source_statistics(db: Session) -> dict[str, int]:
    """Get source statistics."""
    active = db.query(Source).filter(Source.status == SourceStatus.ACTIVE).count()
    frozen = db.query(Source).filter(Source.status == SourceStatus.FROZEN).count()
    pending_review = db.query(Source).filter(Source.pending_review.is_(True)).count()

    return {
        "active": active,
        "frozen": frozen,
        "pending_review": pending_review,
    }


def get_job_statistics(db: Session) -> dict[str, int]:
    """Get job statistics."""
    yesterday = datetime.now(UTC) - timedelta(hours=24)

    pending = db.query(Job).filter(Job.status == JobStatus.PENDING).count()
    running = db.query(Job).filter(Job.status == JobStatus.RUNNING).count()
    failed_24h = db.query(Job).filter(
        Job.status == JobStatus.FAILED,
        Job.created_at >= yesterday.replace(tzinfo=None),
    ).count()

    return {
        "pending": pending,
        "running": running,
        "failed_24h": failed_24h,
    }


def get_item_statistics(db: Session) -> dict[str, int]:
    """Get item statistics."""
    yesterday = datetime.now(UTC) - timedelta(hours=24)

    total = db.query(Item).count()
    last_24h = db.query(Item).filter(
        Item.fetched_at >= yesterday.replace(tzinfo=None),
    ).count()

    return {
        "total": total,
        "last_24h": last_24h,
    }


def get_error_statistics(db: Session) -> dict[str, Any]:
    """Get error statistics from recent jobs."""
    yesterday = datetime.now(UTC) - timedelta(hours=24)

    # Count failed jobs by error type
    failed_jobs = db.query(Job).filter(
        Job.status == JobStatus.FAILED,
        Job.created_at >= yesterday.replace(tzinfo=None),
    ).all()

    # Group by error type
    error_counts: dict[str, int] = {}
    source_errors: dict[str, int] = {}

    for job in failed_jobs:
        error_type = job.error_type or "unknown"
        error_counts[error_type] = error_counts.get(error_type, 0) + 1

        if job.source_id:
            source_errors[job.source_id] = source_errors.get(job.source_id, 0) + 1

    # Get top error sources
    top_sources = []
    sorted_sources = sorted(source_errors.items(), key=lambda x: x[1], reverse=True)[:5]
    for source_id, count in sorted_sources:
        source = db.query(Source).filter(Source.source_id == source_id).first()
        if source:
            top_sources.append({
                "source_id": source_id,
                "source_name": source.name,
                "error_count": count,
            })

    # Format by_type
    by_type = [
        {"error_type": et, "count": c}
        for et, c in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "total_24h": len(failed_jobs),
        "by_type": by_type,
        "top_sources": top_sources,
    }


def determine_overall_status(components: dict[str, str], stats: dict[str, Any]) -> str:
    """Determine overall system status."""
    # Check critical components
    if components.get("database") != "connected":
        return "unhealthy"

    # Check for high error rate
    error_stats = stats.get("errors", {})
    if error_stats.get("total_24h", 0) > 100:
        return "degraded"

    # Check for many pending_review sources
    source_stats = stats.get("sources", {})
    if source_stats.get("pending_review", 0) > 10:
        return "degraded"

    return "healthy"


@router.get("/diagnose", response_model=DiagnoseResponse)
async def get_diagnose(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> DiagnoseResponse:
    """
    Get system diagnose overview.

    Returns system status, component health, and key statistics.
    Use this as the entry point for monitoring and troubleshooting.
    """
    logger.debug("Running system diagnose")

    # Check components
    components = {
        "database": check_database(),
        "redis": check_redis(),
        "scheduler": check_scheduler(),
    }

    # Gather statistics
    statistics = {
        "sources": get_source_statistics(db),
        "jobs": get_job_statistics(db),
        "items": get_item_statistics(db),
        "errors": get_error_statistics(db),
    }

    # Determine overall status
    status = determine_overall_status(components, statistics)

    return DiagnoseResponse(
        status=status,
        version=__version__,
        components=components,
        statistics=statistics,
        server_timestamp=datetime.now(UTC),
    )
