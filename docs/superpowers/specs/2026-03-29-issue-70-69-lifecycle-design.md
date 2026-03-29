---
name: issue-70-69-job-source-lifecycle
description: Job lifecycle management (delete/retry/cleanup) + REMOVED sources cleanup
type: project
---

# Issue #70 + #69: Job/Source Lifecycle Management Design

## Problem Statement

Two related issues need unified implementation:

1. **Issue #70**: Job lifecycle management - delete failed jobs, retry failed jobs, cleanup old jobs
2. **Issue #69**: Cleanup REMOVED sources - delete sources marked as REMOVED with cascade deletion of related data

Both involve cleanup operations, require admin permissions, and should be accessible via CLI.

## Scope

**Included:**
- Job delete endpoint (FAILED jobs only)
- Job retry endpoint (FAILED jobs, respecting retry_count limit)
- Job cleanup endpoint (old completed jobs, configurable days threshold)
- Source cleanup endpoint (REMOVED sources with cascade deletion)
- CLI commands for all operations

**Deferred:**
- Scheduled cleanup jobs (APScheduler integration)
- Web UI integration

---

## Architecture

### API-First Design

```
CLI (api.sh) → Admin API → Service Layer → Database
```

All operations exposed via FastAPI admin endpoints, CLI provides user-friendly commands.

### Permission Requirements

All endpoints require admin API key (existing pattern in `/admin/*` routers).

---

## Design Details

### 1. Job Delete

**Endpoint**: `DELETE /admin/jobs/{job_id}`

**Logic**:
```python
def delete_job(job_id: str) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # Only FAILED jobs can be deleted
    if job.status != JobStatus.FAILED:
        raise HTTPException(400, "Only FAILED jobs can be deleted")

    session.delete(job)
    session.commit()

    return {"deleted": job_id}
```

**Why FAILED only**: Running/pending jobs are active; completed jobs may be needed for audit. FAILED jobs are typically noise users want to clean.

---

### 2. Job Retry

**Endpoint**: `POST /admin/jobs/{job_id}/retry`

**Logic**:
```python
def retry_job(job_id: str) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status != JobStatus.FAILED:
        raise HTTPException(400, "Only FAILED jobs can be retried")

    # Check retry limit (default: 3)
    MAX_RETRIES = 3
    if job.retry_count >= MAX_RETRIES:
        raise HTTPException(400, f"Job exceeded max retries ({MAX_RETRIES})")

    # Dispatch correct task based on job type
    if job.type == JobType.INGEST:
        ingest_source.send(job.source_id, job_id=job.job_id)
    elif job.type == JobType.IMPORT:
        process_import_job.send(job.job_id)
    else:
        raise HTTPException(400, f"Unsupported job type: {job.type}")

    # Reset job state
    job.status = JobStatus.PENDING
    job.retry_count += 1
    job.error_type = None
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    session.commit()

    return {"job_id": job_id, "status": "PENDING", "retry_count": job.retry_count}
```

**Key decision**: Use Dramatiq `.send()` for async execution (existing pattern).

---

### 3. Job Cleanup (Old Completed Jobs)

**Endpoint**: `POST /admin/jobs/cleanup`

**Parameters**:
- `days`: Delete jobs completed before this threshold (default: 30)
- `status`: Job status to clean (default: COMPLETED)

**Logic**:
```python
def cleanup_jobs(days: int = 30, status: JobStatus = JobStatus.COMPLETED) -> dict:
    threshold = datetime.now(UTC) - timedelta(days=days)

    # Delete old jobs
    stmt = delete(Job).where(
        Job.status == status,
        Job.completed_at < threshold
    )
    result = session.execute(stmt)
    session.commit()

    return {"deleted_count": result.rowcount, "threshold_days": days}
```

---

### 4. Source Cleanup (REMOVED Sources)

**Endpoint**: `POST /admin/sources/cleanup`

**Logic** (cascade deletion in correct order):

```python
def cleanup_sources() -> dict:
    # Find REMOVED sources
    removed_sources = session.scalars(
        select(Source).where(Source.status == SourceStatus.REMOVED)
    ).all()

    deleted_sources = 0
    deleted_items = 0
    deleted_jobs = 0

    for source in removed_sources:
        # Order matters: FK constraints require children deleted first
        # 1. Delete items (items.source_id → sources.source_id)
        items_result = session.execute(
            delete(Item).where(Item.source_id == source.source_id)
        )
        deleted_items += items_result.rowcount

        # 2. Delete jobs (jobs.source_id → sources.source_id)
        jobs_result = session.execute(
            delete(Job).where(Job.source_id == source.source_id)
        )
        deleted_jobs += jobs_result.rowcount

        # 3. Delete source
        session.delete(source)
        deleted_sources += 1

    session.commit()

    return {
        "deleted_sources": deleted_sources,
        "deleted_items": deleted_items,
        "deleted_jobs": deleted_jobs
    }
```

**Why manual cascade**: Database FK constraints have no `ON DELETE CASCADE`, requiring explicit deletion order.

---

## CLI Commands

### api.sh Extensions

```bash
# Job operations
./scripts/api.sh jobs delete <job_id>
./scripts/api.sh jobs retry <job_id>
./scripts/api.sh jobs cleanup [--days 30]

# Source operations
./scripts/api.sh sources cleanup
```

### Implementation Pattern

Follow existing `api.sh` patterns:
- Use `curl` with `ADMIN_API_KEY`
- Parse JSON response with `jq`
- Provide user-friendly output

---

## Files to Modify/Create

### New Files
- `src/cyberpulse/services/job_lifecycle_service.py` - Job lifecycle operations
- `src/cyberpulse/services/source_cleanup_service.py` - Source cleanup

### Modified Files
- `src/cyberpulse/api/routers/admin/jobs.py` - Add delete, retry, cleanup endpoints
- `src/cyberpulse/api/routers/admin/sources.py` - Add cleanup endpoint
- `scripts/api.sh` - Add new CLI commands
- `src/cyberpulse/api/schemas/job.py` - Add response schemas

### Test Files
- `tests/test_services/test_job_lifecycle_service.py`
- `tests/test_services/test_source_cleanup_service.py`
- `tests/test_api/test_admin_jobs.py` - Extend existing tests
- `tests/test_api/test_admin_sources.py` - Extend existing tests

---

## Constraints

1. **Retry limit**: Default 3 retries per job
2. **Delete restriction**: Only FAILED jobs can be manually deleted
3. **Cleanup order**: Items → Jobs → Source (FK constraints)
4. **Permission**: Admin API key required for all operations
5. **No CASCADE**: Manual cascade deletion required

---

## Testing Strategy

1. **Unit tests**: Service layer logic
2. **API tests**: Endpoint behavior, error cases
3. **Integration tests**: Full workflow via CLI
4. **Edge cases**:
   - Retry limit exceeded
   - Job not found
   - Job status not FAILED
   - Source with many items/jobs

---

## Why: Requirements from Issues

**Issue #70**: Users need to manage failed jobs without database access
**Issue #69**: REMOVED sources accumulate and need cleanup mechanism
**Combined**: Both need admin-controlled cleanup, unified design reduces duplication

---

## How to Apply

Implement in order:
1. Job lifecycle service + endpoints (core functionality)
2. Source cleanup service + endpoint (cascade logic)
3. CLI commands (user interface)
4. Tests for each component