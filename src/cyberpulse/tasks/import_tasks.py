"""Import tasks for batch source creation."""

import logging
from datetime import UTC, datetime

import dramatiq

from ..database import SessionLocal
from ..models import Job, JobStatus, SourceTier
from ..services.source_service import SourceService

logger = logging.getLogger(__name__)


@dramatiq.actor(max_retries=3)
def process_import_job(job_id: str) -> None:
    """Process an IMPORT job.

    This task:
    1. Gets the import job from database
    2. Extracts feeds list from job.result
    3. Creates sources for each feed
    4. Updates job status and result

    Args:
        job_id: The import job ID to process.
    """
    db = SessionLocal()
    try:
        # Get job from database
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: {job_id}")
            return

        # Mark job as RUNNING
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        logger.info(f"Processing import job {job_id}")

        # Get feeds from job result
        feeds = job.result.get("feeds", [])
        skip_invalid = job.result.get("skip_invalid", True)

        if not feeds:
            logger.warning(f"No feeds in import job {job_id}")
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            job.result = {
                **job.result,
                "imported": 0,
                "skipped": 0,
                "failed": 0,
                "details": [],
            }
            db.commit()
            return

        # Process each feed
        source_service = SourceService(db)
        imported = 0
        skipped = 0
        failed = 0
        details = []

        for feed in feeds:
            feed_url = feed.get("url")
            feed_title = feed.get("title", feed_url)

            if not feed_url:
                logger.warning(f"Skipping feed with no URL: {feed}")
                if not skip_invalid:
                    failed += 1
                    details.append({
                        "url": None,
                        "title": feed_title,
                        "status": "failed",
                        "reason": "No URL provided",
                    })
                continue

            try:
                # Create source
                source, message = source_service.add_source(
                    name=feed_title,
                    connector_type="rss",
                    tier=SourceTier.T2,
                    config={"feed_url": feed_url},
                )

                if source:
                    imported += 1
                    details.append({
                        "url": feed_url,
                        "title": feed_title,
                        "status": "imported",
                        "source_id": source.source_id,
                    })
                    logger.info(f"Imported source: {feed_title} ({source.source_id})")
                else:
                    # Duplicate or other issue
                    skipped += 1
                    details.append({
                        "url": feed_url,
                        "title": feed_title,
                        "status": "skipped",
                        "reason": message,
                    })
                    logger.info(f"Skipped source: {feed_title} - {message}")

            except Exception as e:
                logger.error(f"Failed to import source {feed_title}: {e}")
                if skip_invalid:
                    skipped += 1
                    details.append({
                        "url": feed_url,
                        "title": feed_title,
                        "status": "skipped",
                        "reason": str(e),
                    })
                else:
                    failed += 1
                    details.append({
                        "url": feed_url,
                        "title": feed_title,
                        "status": "failed",
                        "reason": str(e),
                    })

        # Update job result
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC).replace(tzinfo=None)
        job.result = {
            **job.result,
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "details": details,
        }
        db.commit()

        logger.info(
            f"Import job {job_id} completed: "
            f"{imported} imported, {skipped} skipped, {failed} failed"
        )

    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}", exc_info=True)

        # Mark job as FAILED
        if job:
            job.status = JobStatus.FAILED
            job.error_type = type(e).__name__
            job.error_message = str(e)[:500]
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()

        raise

    finally:
        db.close()
