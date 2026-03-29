# Job/Source Lifecycle Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement job lifecycle management (delete/retry/cleanup) and REMOVED sources cleanup with CLI commands.

**Architecture:** API-first design with FastAPI admin endpoints, CLI via api.sh. Service layer handles business logic. No scheduled jobs (manual CLI-triggered only).

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, Dramatiq, PostgreSQL

---

## File Structure

```
src/cyberpulse/
├── services/
│   └── job_lifecycle_service.py     # NEW: Job lifecycle operations
├── api/
│   ├── routers/admin/
│   │   ├── jobs.py                  # MODIFY: Add delete/retry/cleanup endpoints
│   │   └── sources.py               # MODIFY: Add cleanup endpoint
│   └── schemas/
│       └── job.py                   # MODIFY: Add new response schemas
scripts/
└── api.sh                           # MODIFY: Add CLI commands
tests/
├── test_api/
│   └── test_admin_jobs.py           # MODIFY: Add tests for new endpoints
```

---

## Task 1: Add Response Schemas

**Files:**
- Modify: `src/cyberpulse/api/schemas/job.py`

- [ ] **Step 1: Add new response schemas**

Add the following schemas to `src/cyberpulse/api/schemas/job.py` after the existing `JobCreatedResponse` class:

```python
class JobDeleteResponse(BaseModel):
    """Job deletion response."""
    deleted: str
    message: str = "Job deleted successfully"


class JobRetryResponse(BaseModel):
    """Job retry response."""
    job_id: str
    status: str
    retry_count: int
    message: str = "Job queued for retry"


class JobCleanupResponse(BaseModel):
    """Job cleanup response."""
    deleted_count: int
    threshold_days: int
    message: str = "Jobs cleaned up successfully"


class SourceCleanupResponse(BaseModel):
    """Source cleanup response."""
    deleted_sources: int
    deleted_items: int
    deleted_jobs: int
    message: str = "REMOVED sources cleaned up successfully"
```

- [ ] **Step 2: Run tests to verify no syntax errors**

Run: `uv run python -c "from cyberpulse.api.schemas.job import JobDeleteResponse, JobRetryResponse, JobCleanupResponse, SourceCleanupResponse; print('OK')"`
Expected: Output "OK"

- [ ] **Step 3: Commit**

```bash
git add src/cyberpulse/api/schemas/job.py
git commit -m "feat(api): add response schemas for job lifecycle endpoints"
```

---

## Task 2: Create Job Lifecycle Service

**Files:**
- Create: `src/cyberpulse/services/job_lifecycle_service.py`

- [ ] **Step 1: Write the failing test**

Create file `tests/test_services/test_job_lifecycle_service.py`:

```python
"""Tests for JobLifecycleService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cyberpulse.database import Base
from cyberpulse.models import Item, Job, JobStatus, JobType, Source, SourceStatus
from cyberpulse.services.job_lifecycle_service import JobLifecycleService


@pytest.fixture
def db_engine():
    """Create in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine) -> Session:
    """Create database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


class TestDeleteJob:
    """Tests for delete_job method."""

    def test_delete_failed_job_success(self, db_session):
        """Test deleting a FAILED job."""
        job = Job(
            job_id="job_delete01",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            error_type="TestError",
            error_message="Test error",
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)
        result = service.delete_job("job_delete01")

        assert result["deleted"] == "job_delete01"
        # Verify job is deleted
        deleted_job = db_session.get(Job, "job_delete01")
        assert deleted_job is None

    def test_delete_non_failed_job_fails(self, db_session):
        """Test that deleting non-FAILED job raises error."""
        job = Job(
            job_id="job_running01",
            type=JobType.INGEST,
            status=JobStatus.RUNNING,
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)
        with pytest.raises(ValueError, match="Only FAILED jobs can be deleted"):
            service.delete_job("job_running01")

    def test_delete_nonexistent_job_fails(self, db_session):
        """Test that deleting non-existent job raises error."""
        service = JobLifecycleService(db_session)
        with pytest.raises(ValueError, match="Job not found"):
            service.delete_job("job_nonexistent")


class TestRetryJob:
    """Tests for retry_job method."""

    def test_retry_ingest_job_success(self, db_session):
        """Test retrying a FAILED INGEST job."""
        source = Source(
            source_id="src_retry01",
            name="Test Source",
            connector_type="rss",
        )
        db_session.add(source)

        job = Job(
            job_id="job_retry01",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id="src_retry01",
            error_type="ConnectionError",
            error_message="Connection failed",
            retry_count=1,
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)

        # Mock Dramatiq task to avoid Redis dependency
        with patch("cyberpulse.services.job_lifecycle_service.ingest_source") as mock_task:
            mock_task.send = Mock()
            result = service.retry_job("job_retry01")

            assert result["job_id"] == "job_retry01"
            assert result["status"] == "PENDING"
            assert result["retry_count"] == 2

            # Verify task was dispatched
            mock_task.send.assert_called_once_with("src_retry01", job_id="job_retry01")

        # Verify job state reset
        db_session.refresh(job)
        assert job.status == JobStatus.PENDING
        assert job.error_type is None
        assert job.error_message is None

    def test_retry_import_job_success(self, db_session):
        """Test retrying a FAILED IMPORT job."""
        job = Job(
            job_id="job_import01",
            type=JobType.IMPORT,
            status=JobStatus.FAILED,
            file_name="test.opml",
            error_type="ParseError",
            error_message="Parse failed",
            retry_count=0,
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)

        # Mock Dramatiq task to avoid Redis dependency
        with patch("cyberpulse.services.job_lifecycle_service.process_import_job") as mock_task:
            mock_task.send = Mock()
            result = service.retry_job("job_import01")

            assert result["job_id"] == "job_import01"
            assert result["status"] == "PENDING"
            assert result["retry_count"] == 1

            # Verify task was dispatched
            mock_task.send.assert_called_once_with("job_import01")

    def test_retry_exceeds_limit_fails(self, db_session):
        """Test that retrying job with max retries raises error."""
        job = Job(
            job_id="job_maxretry",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            retry_count=3,  # Already at max
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)
        with pytest.raises(ValueError, match="exceeded max retries"):
            service.retry_job("job_maxretry")

    def test_retry_non_failed_job_fails(self, db_session):
        """Test that retrying non-FAILED job raises error."""
        job = Job(
            job_id="job_pending01",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)
        with pytest.raises(ValueError, match="Only FAILED jobs can be retried"):
            service.retry_job("job_pending01")


class TestCleanupJobs:
    """Tests for cleanup_jobs method."""

    def test_cleanup_old_completed_jobs(self, db_session):
        """Test cleaning up old COMPLETED jobs."""
        # Create old completed job
        old_job = Job(
            job_id="job_old01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(days=60),
        )
        # Create recent completed job
        recent_job = Job(
            job_id="job_recent01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(days=10),
        )
        db_session.add_all([old_job, recent_job])
        db_session.commit()

        service = JobLifecycleService(db_session)
        result = service.cleanup_jobs(days=30)

        assert result["deleted_count"] == 1
        assert result["threshold_days"] == 30

        # Verify old job deleted, recent job remains
        assert db_session.get(Job, "job_old01") is None
        assert db_session.get(Job, "job_recent01") is not None

    def test_cleanup_with_custom_days(self, db_session):
        """Test cleanup with custom days threshold."""
        job = Job(
            job_id="job_45days",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(days=45),
        )
        db_session.add(job)
        db_session.commit()

        service = JobLifecycleService(db_session)
        result = service.cleanup_jobs(days=30)

        assert result["deleted_count"] == 1

    def test_cleanup_preserves_failed_jobs(self, db_session):
        """Test that cleanup with status=COMPLETED doesn't delete FAILED jobs."""
        failed_job = Job(
            job_id="job_failed_old",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            completed_at=datetime.now(UTC) - timedelta(days=60),
        )
        db_session.add(failed_job)
        db_session.commit()

        service = JobLifecycleService(db_session)
        result = service.cleanup_jobs(days=30, status=JobStatus.COMPLETED)

        assert result["deleted_count"] == 0
        assert db_session.get(Job, "job_failed_old") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_job_lifecycle_service.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Create the service implementation**

Create file `src/cyberpulse/services/job_lifecycle_service.py`:

```python
"""Job lifecycle service for delete, retry, and cleanup operations."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Job, JobStatus, JobType
from ..tasks.import_tasks import process_import_job
from ..tasks.ingestion_tasks import ingest_source

logger = logging.getLogger(__name__)

# Default maximum retries for a job
MAX_RETRIES = 3


class JobLifecycleService:
    """Service for managing job lifecycle operations.

    Provides methods for:
    - Deleting failed jobs
    - Retrying failed jobs
    - Cleaning up old jobs
    """

    def __init__(self, db: Session):
        """Initialize service with database session.

        Args:
            db: SQLAlchemy session for database operations.
        """
        self.db = db

    def delete_job(self, job_id: str) -> dict:
        """Delete a FAILED job.

        Args:
            job_id: The job ID to delete.

        Returns:
            Dict with deleted job_id.

        Raises:
            ValueError: If job not found or not in FAILED status.
        """
        job = self.db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != JobStatus.FAILED:
            raise ValueError(f"Only FAILED jobs can be deleted, current status: {job.status.value}")

        self.db.delete(job)
        self.db.commit()
        logger.info(f"Deleted job: {job_id}")

        return {"deleted": job_id}

    def retry_job(self, job_id: str) -> dict:
        """Retry a FAILED job.

        Resets job state and dispatches appropriate Dramatiq task.

        Args:
            job_id: The job ID to retry.

        Returns:
            Dict with job_id, status, and retry_count.

        Raises:
            ValueError: If job not found, not FAILED, or exceeds retry limit.
        """
        job = self.db.get(Job, job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        if job.status != JobStatus.FAILED:
            raise ValueError(f"Only FAILED jobs can be retried, current status: {job.status.value}")

        if job.retry_count >= MAX_RETRIES:
            raise ValueError(f"Job exceeded max retries ({MAX_RETRIES})")

        # Dispatch appropriate task based on job type
        if job.type == JobType.INGEST:
            ingest_source.send(job.source_id, job_id=job.job_id)
            logger.info(f"Dispatched ingest_source for job {job_id}, source {job.source_id}")
        elif job.type == JobType.IMPORT:
            process_import_job.send(job.job_id)
            logger.info(f"Dispatched process_import_job for job {job_id}")
        else:
            raise ValueError(f"Unsupported job type: {job.type.value}")

        # Reset job state
        job.status = JobStatus.PENDING
        job.retry_count += 1
        job.error_type = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        self.db.commit()

        logger.info(f"Job {job_id} queued for retry (attempt {job.retry_count})")

        return {
            "job_id": job_id,
            "status": "PENDING",
            "retry_count": job.retry_count,
        }

    def cleanup_jobs(
        self,
        days: int = 30,
        status: JobStatus = JobStatus.COMPLETED
    ) -> dict:
        """Clean up old jobs by status.

        Args:
            days: Delete jobs completed before this many days ago.
            status: Job status to clean up.

        Returns:
            Dict with deleted_count and threshold_days.
        """
        threshold = datetime.now(UTC) - timedelta(days=days)

        stmt = delete(Job).where(
            Job.status == status,
            Job.completed_at < threshold
        )
        result = self.db.execute(stmt)
        self.db.commit()

        deleted_count = result.rowcount
        logger.info(f"Cleaned up {deleted_count} jobs older than {days} days with status {status.value}")

        return {
            "deleted_count": deleted_count,
            "threshold_days": days,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_services/test_job_lifecycle_service.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/services/job_lifecycle_service.py tests/test_services/test_job_lifecycle_service.py
git commit -m "feat(services): add JobLifecycleService with delete/retry/cleanup"
```

---

## Task 3: Add Job Delete Endpoint

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/jobs.py`
- Modify: `tests/test_api/test_admin_jobs.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api/test_admin_jobs.py` after the existing `TestJobDetail` class:

```python
class TestJobDelete:
    """Tests for job delete endpoint."""

    def test_delete_job_no_auth(self, client):
        """Test that deleting a job requires authentication."""
        response = client.delete("/api/v1/admin/jobs/job_delete01")
        assert response.status_code == 401

    def test_delete_job_not_found(self, client, db_session, mock_admin_client):
        """Test deleting non-existent job returns 404."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/jobs/job_nonexistent")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_delete_non_failed_job_fails(self, client, db_session, mock_admin_client):
        """Test that deleting non-FAILED job returns 400."""
        job = Job(
            job_id="job_running_del",
            type=JobType.INGEST,
            status=JobStatus.RUNNING,
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/jobs/job_running_del")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Only FAILED jobs" in response.json()["detail"]

    def test_delete_failed_job_success(self, client, db_session, mock_admin_client):
        """Test deleting a FAILED job."""
        job = Job(
            job_id="job_failed_del",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            error_type="TestError",
            error_message="Test error",
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.delete("/api/v1/admin/jobs/job_failed_del")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == "job_failed_del"

        # Verify job is deleted
        assert db_session.get(Job, "job_failed_del") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api/test_admin_jobs.py::TestJobDelete -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 3: Add delete endpoint**

Add to `src/cyberpulse/api/routers/admin/jobs.py` after the `get_job` function (around line 197):

```python
@router.delete("/jobs/{job_id}", response_model=JobDeleteResponse)
async def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobDeleteResponse:
    """Delete a FAILED job.

    Only FAILED jobs can be deleted. Running, pending, and completed jobs
    cannot be deleted through this endpoint.
    """
    validate_job_id(job_id)

    from ....services.job_lifecycle_service import JobLifecycleService

    service = JobLifecycleService(db)
    try:
        result = service.delete_job(job_id)
        return JobDeleteResponse(deleted=result["deleted"])
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "not found" in str(e).lower() else 400,
            detail=str(e)
        )
```

Add the import for `JobDeleteResponse` at the top of the file:

```python
from ...schemas.job import JobCreate, JobCreatedResponse, JobDeleteResponse, JobListResponse, JobResponse
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api/test_admin_jobs.py::TestJobDelete -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/api/routers/admin/jobs.py tests/test_api/test_admin_jobs.py
git commit -m "feat(api): add DELETE /admin/jobs/{job_id} endpoint"
```

---

## Task 4: Add Job Retry Endpoint

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/jobs.py`
- Modify: `tests/test_api/test_admin_jobs.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api/test_admin_jobs.py` after the `TestJobDelete` class:

```python
class TestJobRetry:
    """Tests for job retry endpoint."""

    def test_retry_job_no_auth(self, client):
        """Test that retrying a job requires authentication."""
        response = client.post("/api/v1/admin/jobs/job_retry01/retry")
        assert response.status_code == 401

    def test_retry_job_not_found(self, client, db_session, mock_admin_client):
        """Test retrying non-existent job returns 404."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs/job_nonexistent/retry")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_retry_non_failed_job_fails(self, client, db_session, mock_admin_client):
        """Test that retrying non-FAILED job returns 400."""
        job = Job(
            job_id="job_pending_retry",
            type=JobType.INGEST,
            status=JobStatus.PENDING,
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs/job_pending_retry/retry")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Only FAILED jobs" in response.json()["detail"]

    def test_retry_exceeds_limit_fails(self, client, db_session, mock_admin_client):
        """Test that retrying job with max retries returns 400."""
        job = Job(
            job_id="job_maxretry",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            retry_count=3,
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs/job_maxretry/retry")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "max retries" in response.json()["detail"].lower()

    def test_retry_failed_ingest_job_success(self, client, db_session, mock_admin_client):
        """Test retrying a FAILED INGEST job."""
        source = Source(
            source_id="src_retry_test",
            name="Test Source",
            connector_type="rss",
        )
        db_session.add(source)

        job = Job(
            job_id="job_retry_ingest",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id="src_retry_test",
            error_type="ConnectionError",
            error_message="Connection failed",
            retry_count=1,
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session

        # Mock at service layer where Dramatiq tasks are called
        with patch("cyberpulse.services.job_lifecycle_service.ingest_source") as mock_task:
            mock_task.send = Mock()
            try:
                response = client.post("/api/v1/admin/jobs/job_retry_ingest/retry")
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job_retry_ingest"
        assert data["status"] == "PENDING"
        assert data["retry_count"] == 2

        # Verify task was dispatched
        mock_task.send.assert_called_once_with("src_retry_test", job_id="job_retry_ingest")

    def test_retry_failed_import_job_success(self, client, db_session, mock_admin_client):
        """Test retrying a FAILED IMPORT job."""
        job = Job(
            job_id="job_retry_import",
            type=JobType.IMPORT,
            status=JobStatus.FAILED,
            file_name="test.opml",
            retry_count=0,
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session

        # Mock at service layer where Dramatiq tasks are called
        with patch("cyberpulse.services.job_lifecycle_service.process_import_job") as mock_task:
            mock_task.send = Mock()
            try:
                response = client.post("/api/v1/admin/jobs/job_retry_import/retry")
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job_retry_import"
        assert data["status"] == "PENDING"
        assert data["retry_count"] == 1

        # Verify task was dispatched
        mock_task.send.assert_called_once_with("job_retry_import")
```

Add the import for `patch` at the top of the test file (it's already there from existing tests).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api/test_admin_jobs.py::TestJobRetry -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 3: Add retry endpoint**

Add to `src/cyberpulse/api/routers/admin/jobs.py` after the `delete_job` function:

```python
@router.post("/jobs/{job_id}/retry", response_model=JobRetryResponse)
async def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobRetryResponse:
    """Retry a FAILED job.

    Resets the job state and dispatches the appropriate Dramatiq task.
    Maximum 3 retries allowed per job.
    """
    validate_job_id(job_id)

    from ....services.job_lifecycle_service import JobLifecycleService

    service = JobLifecycleService(db)
    try:
        result = service.retry_job(job_id)
        return JobRetryResponse(
            job_id=result["job_id"],
            status=result["status"],
            retry_count=result["retry_count"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "not found" in str(e).lower() else 400,
            detail=str(e)
        )
```

Add the import for `JobRetryResponse` at the top of the file:

```python
from ...schemas.job import JobCreate, JobCreatedResponse, JobDeleteResponse, JobListResponse, JobResponse, JobRetryResponse
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api/test_admin_jobs.py::TestJobRetry -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/api/routers/admin/jobs.py tests/test_api/test_admin_jobs.py
git commit -m "feat(api): add POST /admin/jobs/{job_id}/retry endpoint"
```

---

## Task 5: Add Job Cleanup Endpoint

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/jobs.py`
- Modify: `tests/test_api/test_admin_jobs.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api/test_admin_jobs.py` after the `TestJobRetry` class:

```python
class TestJobCleanup:
    """Tests for job cleanup endpoint."""

    def test_cleanup_jobs_no_auth(self, client):
        """Test that cleanup requires authentication."""
        response = client.post("/api/v1/admin/jobs/cleanup")
        assert response.status_code == 401

    def test_cleanup_jobs_default_params(self, client, db_session, mock_admin_client):
        """Test cleanup with default parameters."""
        # Create old completed job
        old_job = Job(
            job_id="job_cleanup_old",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(days=60),
        )
        # Create recent completed job
        recent_job = Job(
            job_id="job_cleanup_recent",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(days=10),
        )
        db_session.add_all([old_job, recent_job])
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs/cleanup")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 1
        assert data["threshold_days"] == 30

    def test_cleanup_jobs_custom_days(self, client, db_session, mock_admin_client):
        """Test cleanup with custom days parameter."""
        job = Job(
            job_id="job_cleanup_45",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            completed_at=datetime.now(UTC) - timedelta(days=45),
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs/cleanup?days=30")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 1
        assert data["threshold_days"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api/test_admin_jobs.py::TestJobCleanup -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 3: Add cleanup endpoint**

Add to `src/cyberpulse/api/routers/admin/jobs.py` **BEFORE** the `get_job` function (static paths before dynamic):

```python
@router.post("/jobs/cleanup", response_model=JobCleanupResponse)
async def cleanup_jobs(
    days: int = Query(30, ge=1, description="Delete jobs completed before this many days"),
    status: str = Query("COMPLETED", description="Job status to clean up"),
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> JobCleanupResponse:
    """Clean up old jobs.

    Deletes jobs with the specified status that completed before the threshold.
    Default: Delete COMPLETED jobs older than 30 days.
    """
    # Validate status
    try:
        status_enum = JobStatus(status.upper())
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {[s.value for s in JobStatus]}"
        )

    from ....services.job_lifecycle_service import JobLifecycleService

    service = JobLifecycleService(db)
    result = service.cleanup_jobs(days=days, status=status_enum)

    return JobCleanupResponse(
        deleted_count=result["deleted_count"],
        threshold_days=result["threshold_days"],
    )
```

Add the import for `JobCleanupResponse` at the top of the file:

```python
from ...schemas.job import JobCleanupResponse, JobCreate, JobCreatedResponse, JobDeleteResponse, JobListResponse, JobResponse, JobRetryResponse
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api/test_admin_jobs.py::TestJobCleanup -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/cyberpulse/api/routers/admin/jobs.py tests/test_api/test_admin_jobs.py
git commit -m "feat(api): add POST /admin/jobs/cleanup endpoint"
```

---

## Task 6: Add Source Cleanup Endpoint

**Files:**
- Modify: `src/cyberpulse/api/routers/admin/sources.py`
- Modify: `src/cyberpulse/api/schemas/job.py`
- Modify: `tests/test_api/test_admin_sources.py`

- [ ] **Step 1: Add cleanup method to JobLifecycleService**

Add to `src/cyberpulse/services/job_lifecycle_service.py` after the `cleanup_jobs` method:

```python
    def cleanup_sources(self) -> dict:
        """Clean up REMOVED sources with cascade deletion.

        Deletes all sources with status=REMOVED along with their
        associated items and jobs.

        Returns:
            Dict with counts of deleted sources, items, and jobs.
        """
        from ..models import Item, Source, SourceStatus

        removed_sources = self.db.scalars(
            select(Source).where(Source.status == SourceStatus.REMOVED)
        ).all()

        deleted_sources = 0
        deleted_items = 0
        deleted_jobs = 0

        for source in removed_sources:
            # Order matters: FK constraints require children deleted first
            # 1. Delete items (items.source_id is NOT null)
            items_result = self.db.execute(
                delete(Item).where(Item.source_id == source.source_id)
            )
            deleted_items += items_result.rowcount

            # 2. Delete jobs with this source_id (jobs.source_id is nullable)
            jobs_result = self.db.execute(
                delete(Job).where(Job.source_id == source.source_id)
            )
            deleted_jobs += jobs_result.rowcount

            # 3. Delete source
            self.db.delete(source)
            deleted_sources += 1

        self.db.commit()

        logger.info(
            f"Cleaned up {deleted_sources} REMOVED sources, "
            f"{deleted_items} items, {deleted_jobs} jobs"
        )

        return {
            "deleted_sources": deleted_sources,
            "deleted_items": deleted_items,
            "deleted_jobs": deleted_jobs,
        }
```

Add the import for `Item` at the top of the file (inside the method to avoid circular import):

The `Item` and `Source`, `SourceStatus` imports are done inside the method to avoid circular imports.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_api/test_admin_sources.py` after the existing test classes:

```python
class TestSourceCleanup:
    """Tests for source cleanup endpoint."""

    def test_cleanup_sources_no_auth(self, client):
        """Test that cleanup requires authentication."""
        response = client.post("/api/v1/admin/sources/cleanup")
        assert response.status_code == 401

    def test_cleanup_sources_with_removed_sources(self, client, db_session, mock_admin_client):
        """Test cleanup removes REMOVED sources and their items/jobs."""
        # Create a REMOVED source with items and jobs
        source = Source(
            source_id="src_removed01",
            name="Removed Source",
            connector_type="rss",
            status=SourceStatus.REMOVED,
        )
        db_session.add(source)

        # Add items
        item1 = Item(
            item_id="item_src01_01",
            source_id="src_removed01",
            external_id="ext1",
            url="https://example.com/1",
            title="Item 1",
            published_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
        )
        item2 = Item(
            item_id="item_src01_02",
            source_id="src_removed01",
            external_id="ext2",
            url="https://example.com/2",
            title="Item 2",
            published_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
        )
        db_session.add_all([item1, item2])

        # Add job
        job = Job(
            job_id="job_src01",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id="src_removed01",
        )
        db_session.add(job)

        # Create an ACTIVE source that should NOT be deleted
        active_source = Source(
            source_id="src_active01",
            name="Active Source",
            connector_type="rss",
            status=SourceStatus.ACTIVE,
        )
        db_session.add(active_source)

        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/sources/cleanup")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_sources"] == 1
        assert data["deleted_items"] == 2
        assert data["deleted_jobs"] == 1

        # Verify REMOVED source is deleted
        assert db_session.get(Source, "src_removed01") is None

        # Verify ACTIVE source still exists
        assert db_session.get(Source, "src_active01") is not None

    def test_cleanup_sources_no_removed_sources(self, client, db_session, mock_admin_client):
        """Test cleanup when no REMOVED sources exist."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/sources/cleanup")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_sources"] == 0
        assert data["deleted_items"] == 0
        assert data["deleted_jobs"] == 0
```

Add the necessary imports at the top of the test file (update the existing imports):

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from cyberpulse.api.auth import get_current_client
from cyberpulse.api.dependencies import get_db
from cyberpulse.api.main import app
from cyberpulse.models import ApiClient, ApiClientStatus, Item, Job, JobStatus, JobType, Source, SourceStatus
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_api/test_admin_sources.py::TestSourceCleanup -v`
Expected: FAIL with 404 (endpoint not found)

- [ ] **Step 4: Add cleanup endpoint**

Add to `src/cyberpulse/api/routers/admin/sources.py` **BEFORE** the `get_source` function (static paths before dynamic), around line 478:

```python
@router.post("/sources/cleanup", response_model=SourceCleanupResponse)
async def cleanup_sources(
    db: Session = Depends(get_db),
    _admin: ApiClient = Depends(require_permissions(["admin"])),
) -> SourceCleanupResponse:
    """Clean up REMOVED sources.

    Permanently deletes all sources with status=REMOVED along with
    their associated items and jobs. This is a physical delete,
    unlike DELETE /sources/{source_id} which is a soft delete.
    """
    from ....services.job_lifecycle_service import JobLifecycleService

    service = JobLifecycleService(db)
    result = service.cleanup_sources()

    return SourceCleanupResponse(
        deleted_sources=result["deleted_sources"],
        deleted_items=result["deleted_items"],
        deleted_jobs=result["deleted_jobs"],
    )
```

Add the import for `SourceCleanupResponse` at the top of the file:

```python
from ...schemas.job import JobCleanupResponse, SourceCleanupResponse
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api/test_admin_sources.py::TestSourceCleanup -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add src/cyberpulse/services/job_lifecycle_service.py src/cyberpulse/api/routers/admin/sources.py tests/test_api/test_admin_sources.py
git commit -m "feat(api): add POST /admin/sources/cleanup endpoint"
```

---

## Task 7: Add CLI Commands

**Files:**
- Modify: `scripts/api.sh`

- [ ] **Step 1: Add jobs delete command**

In `scripts/api.sh`, find the `cmd_jobs` function (around line 577) and update the case statement to include the new subcommands:

```bash
cmd_jobs() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)       cmd_jobs_list "$@" ;;
        get)        cmd_jobs_get "$@" ;;
        run)        cmd_jobs_run "$@" ;;
        delete)     cmd_jobs_delete "$@" ;;
        retry)      cmd_jobs_retry "$@" ;;
        cleanup)    cmd_jobs_cleanup "$@" ;;
        *)
            print_error "Unknown jobs subcommand: $subcommand"
            print_jobs_help
            exit 1
            ;;
    esac
}
```

Add the new command functions after `cmd_jobs_run` (around line 661):

```bash
cmd_jobs_delete() {
    local job_id="${1:-}"

    if [[ -z "$job_id" ]]; then
        die "Usage: api.sh jobs delete <job_id>"
    fi

    local response
    response=$(api_delete "/api/v1/admin/jobs/$job_id")
    check_api_error "$response"

    print_success "Job deleted: $job_id"
    echo "$response" | jq .
}

cmd_jobs_retry() {
    local job_id="${1:-}"

    if [[ -z "$job_id" ]]; then
        die "Usage: api.sh jobs retry <job_id>"
    fi

    print_info "Retrying job: $job_id"

    local response
    response=$(api_post "/api/v1/admin/jobs/${job_id}/retry")
    check_api_error "$response"

    print_success "Job queued for retry"
    echo "$response" | jq .
}

cmd_jobs_cleanup() {
    local days="30"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --days)  days="$2"; shift 2 ;;
            *)       shift ;;
        esac
    done

    print_info "Cleaning up jobs older than $days days..."

    local response
    response=$(api_post "/api/v1/admin/jobs/cleanup?days=${days}")
    check_api_error "$response"

    local deleted_count
    deleted_count=$(echo "$response" | jq -r '.deleted_count')

    print_success "Deleted $deleted_count old jobs"
    echo "$response" | jq .
}
```

- [ ] **Step 2: Update print_jobs_help**

Update the `print_jobs_help` function (around line 663):

```bash
print_jobs_help() {
    echo ""
    echo "Jobs commands:"
    echo "  list [--type TYPE] [--status STATUS] [--source SOURCE_ID]"
    echo "  get <job_id>"
    echo "  run <source_id>"
    echo "  delete <job_id>              Delete a FAILED job"
    echo "  retry <job_id>               Retry a FAILED job"
    echo "  cleanup [--days 30]          Cleanup old completed jobs"
}
```

- [ ] **Step 3: Add sources cleanup command**

Find the `cmd_sources` function (around line 213) and add the cleanup subcommand:

```bash
cmd_sources() {
    local subcommand="${1:-list}"
    shift || true

    case "$subcommand" in
        list)           cmd_sources_list "$@" ;;
        get)            cmd_sources_get "$@" ;;
        create)         cmd_sources_create "$@" ;;
        update)         cmd_sources_update "$@" ;;
        delete)         cmd_sources_delete "$@" ;;
        test)           cmd_sources_test "$@" ;;
        schedule)       cmd_sources_schedule "$@" ;;
        unschedule)     cmd_sources_unschedule "$@" ;;
        import)         cmd_sources_import "$@" ;;
        export)         cmd_sources_export "$@" ;;
        defaults)       cmd_sources_defaults "$@" ;;
        set-defaults)   cmd_sources_set_defaults "$@" ;;
        cleanup)        cmd_sources_cleanup "$@" ;;
        *)
            print_error "Unknown sources subcommand: $subcommand"
            print_sources_help
            exit 1
            ;;
    esac
}
```

Add the new command function (after `cmd_sources_set_defaults`):

```bash
cmd_sources_cleanup() {
    print_info "Cleaning up REMOVED sources..."

    local response
    response=$(api_post "/api/v1/admin/sources/cleanup")
    check_api_error "$response"

    local deleted_sources deleted_items deleted_jobs
    deleted_sources=$(echo "$response" | jq -r '.deleted_sources')
    deleted_items=$(echo "$response" | jq -r '.deleted_items')
    deleted_jobs=$(echo "$response" | jq -r '.deleted_jobs')

    print_success "Cleaned up $deleted_sources sources, $deleted_items items, $deleted_jobs jobs"
    echo "$response" | jq .
}
```

- [ ] **Step 4: Update print_sources_help**

Update the `print_sources_help` function (around line 553):

```bash
print_sources_help() {
    echo ""
    echo "Sources commands:"
    echo "  list [--status STATUS] [--tier TIER] [--scheduled BOOL]"
    echo "  get <source_id>"
    echo "  create --name NAME --type TYPE --url URL [--tier TIER]"
    echo "  update <source_id> [--name NAME] [--url URL] [--tier TIER] [--status STATUS]"
    echo "  delete <source_id>"
    echo ""
    echo "  test <source_id>                          测试源连接"
    echo "  schedule <source_id> --interval SECONDS   设置采集调度"
    echo "  unschedule <source_id>                    取消采集调度"
    echo ""
    echo "  import --file FILE.opml [--skip-invalid]  批量导入"
    echo "  export [OUTPUT_FILE]                      导出源配置"
    echo ""
    echo "  defaults                                  查看默认配置"
    echo "  set-defaults --interval SECONDS           设置默认采集间隔"
    echo ""
    echo "  cleanup                                   清理已删除的源（物理删除）"
}
```

- [ ] **Step 5: Update show_help main help section**

Update the `show_help` function to include the new commands in the jobs section (around line 1016):

```bash
    echo "  jobs <cmd>             任务管理"
    echo "    list                 列出任务"
    echo "    get <id>             获取任务详情"
    echo "    run <source_id>      运行采集任务"
    echo "    delete <id>          删除失败任务"
    echo "    retry <id>           重试失败任务"
    echo "    cleanup [--days N]   清理旧任务"
```

- [ ] **Step 6: Verify script syntax**

Run: `bash -n scripts/api.sh`
Expected: No output (syntax OK)

- [ ] **Step 7: Commit**

```bash
git add scripts/api.sh
git commit -m "feat(cli): add jobs delete/retry/cleanup and sources cleanup commands"
```

---

## Task 8: Run Full Test Suite

**Files:**
- None (verification only)

- [ ] **Step 1: Run all API tests**

Run: `uv run pytest tests/test_api/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run service tests**

Run: `uv run pytest tests/test_services/test_job_lifecycle_service.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run linting**

Run: `uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 4: Run type check**

Run: `uv run mypy src/cyberpulse/services/job_lifecycle_service.py --ignore-missing-imports`
Expected: No errors

---

## Summary

This plan implements Issue #70 and Issue #69:

1. **Job Delete** - `DELETE /admin/jobs/{job_id}` - Delete FAILED jobs only
2. **Job Retry** - `POST /admin/jobs/{job_id}/retry` - Retry FAILED jobs (max 3 retries)
3. **Job Cleanup** - `POST /admin/jobs/cleanup` - Cleanup old COMPLETED jobs
4. **Source Cleanup** - `POST /admin/sources/cleanup` - Physical delete REMOVED sources
5. **CLI Commands** - `jobs delete/retry/cleanup`, `sources cleanup`

All endpoints require admin authentication. Tests cover success and error cases.