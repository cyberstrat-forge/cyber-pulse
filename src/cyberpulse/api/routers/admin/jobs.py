"""Job management API router for admin endpoints."""

import logging
import re
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ....models import Job, JobStatus, JobType, Source
from ....tasks.ingestion_tasks import ingest_source
from ...auth import ApiClient, require_permissions
from ...dependencies import get_db
from ...schemas.job import JobCreate, JobCreatedResponse, JobListResponse, JobResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# job_id format: job_{uuid}
JOB_ID_PATTERN = re.compile(r"^job_[a-f0-9]+$")


def validate_job_id(job_id: str) -> None:
    """Validate job_id format."""
    if not JOB_ID_PATTERN.match(job_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job_id format: {job_id}"
        )


def build_job_response(job: Job, source_name: str | None = None) -> JobResponse:
    """Build JobResponse from Job model."""
    duration_seconds = None
    if job.started_at and job.completed_at:
        delta = job.completed_at - job.started_at
        duration_seconds = int(delta.total_seconds())

    error = None
    if job.status == JobStatus.FAILED:
        error = {
            "type": job.error_type or "unknown",
            "message": job.error_message or "Unknown error",
        }

    return JobResponse(
        job_id=job.job_id,
        type=job.type.value,
        status=job.status.value,
        source_id=job.source_id,
        source_name=source_name,
        file_name=job.file_name,
        result=job.result,
        error=error,
        retry_count=job.retry_count,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration_seconds,
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    type: str | None = Query(None, description="Filter by type: ingest, import"),
    status: str | None = Query(None, description="Filter by status: pending, running, completed, failed"),
    source_id: str | None = Query(None, description="Filter by source ID"),
    since: datetime | None = Query(None, description="Created after this time"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobListResponse:
    """List jobs with optional filtering."""
    logger.debug(f"Listing jobs: type={type}, status={status}, source_id={source_id}")

    query = db.query(Job)

    if type:
        try:
            type_enum = JobType(type.lower())
            query = query.filter(Job.type == type_enum)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid type '{type}'. Must be one of: ingest, import"
            )

    if status:
        try:
            status_enum = JobStatus(status.lower())
            query = query.filter(Job.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of: pending, running, completed, failed"
            )

    if source_id:
        query = query.filter(Job.source_id == source_id)

    if since:
        query = query.filter(Job.created_at >= since)

    jobs = query.order_by(desc(Job.created_at)).limit(limit).all()

    # Get source names
    source_ids = {j.source_id for j in jobs if j.source_id}
    sources = db.query(Source).filter(Source.source_id.in_(source_ids)).all()
    source_map = {s.source_id: s.name for s in sources}

    return JobListResponse(
        data=[build_job_response(j, source_map.get(j.source_id)) for j in jobs],
        count=len(jobs),
        server_timestamp=datetime.now(UTC),
    )


@router.post("/jobs", response_model=JobCreatedResponse, status_code=201)
async def create_job(
    request: JobCreate,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobCreatedResponse:
    """Create a manual ingestion job."""
    logger.info(f"Creating job for source: {request.source_id}")

    # Verify source exists
    source = db.query(Source).filter(Source.source_id == request.source_id).first()
    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"Source not found: {request.source_id}"
        )

    # Create job
    job = Job(
        job_id=f"job_{secrets.token_hex(8)}",
        type=JobType.INGEST,
        status=JobStatus.PENDING,
        source_id=request.source_id,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Created job: {job.job_id}")

    # Trigger Dramatiq task
    try:
        ingest_source.send(request.source_id)
        logger.info(f"Triggered ingest_source task for source: {request.source_id}")
    except (OSError, ConnectionError) as e:
        logger.warning(f"Failed to trigger ingest_source task: {e}")

    return JobCreatedResponse(
        job_id=job.job_id,
        type=job.type.value,
        status=job.status.value,
        source_id=request.source_id,
        source_name=source.name,
        message="Job created and queued",
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobResponse:
    """Get job details."""
    validate_job_id(job_id)

    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}"
        )

    # Get source name
    source_name = None
    if job.source_id:
        source = db.query(Source).filter(Source.source_id == job.source_id).first()
        source_name = source.name if source else None

    return build_job_response(job, source_name)
