"""Tests for Job Admin API."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from cyberpulse.api.auth import get_current_client
from cyberpulse.api.dependencies import get_db
from cyberpulse.api.main import app
from cyberpulse.models import (
    ApiClient,
    ApiClientStatus,
    Job,
    JobStatus,
    JobType,
    Source,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_admin_client():
    """Create a mock admin API client for authentication."""
    client = Mock(spec=ApiClient)
    client.client_id = "cli_admin"
    client.name = "Admin Client"
    client.status = ApiClientStatus.ACTIVE
    client.permissions = ["admin", "read"]
    return client


class TestJobList:
    """Tests for job list endpoint."""

    def test_list_jobs_no_auth(self, client):
        """Test that listing jobs requires authentication."""
        response = client.get("/api/v1/admin/jobs")
        assert response.status_code == 401

    def test_list_jobs_with_admin(self, client, db_session, mock_admin_client):
        """Test listing jobs with admin permission."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data
        assert "server_timestamp" in data

    def test_list_jobs_with_status_filter(self, client, db_session, mock_admin_client):
        """Test listing jobs with status filter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs?status=completed")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data

    def test_list_jobs_with_type_filter(self, client, db_session, mock_admin_client):
        """Test listing jobs with type filter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs?type=ingest")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_jobs_with_source_id_filter(self, client, db_session, mock_admin_client):
        """Test listing jobs with source_id filter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs?source_id=src_test123")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_list_jobs_invalid_status(self, client, db_session, mock_admin_client):
        """Test listing jobs with invalid status returns 422."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs?status=invalid_status")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_list_jobs_invalid_type(self, client, db_session, mock_admin_client):
        """Test listing jobs with invalid type returns 422."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs?type=invalid_type")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_list_jobs_with_limit(self, client, db_session, mock_admin_client):
        """Test listing jobs with limit parameter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs?limit=10")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200

    def test_list_jobs_with_since(self, client, db_session, mock_admin_client):
        """Test listing jobs with since parameter."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        # Use Z suffix to avoid URL encoding issues with + sign
        since_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            response = client.get(f"/api/v1/admin/jobs?since={since_time}")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200


class TestJobCreate:
    """Tests for job creation endpoint."""

    def test_create_job_no_auth(self, client):
        """Test that creating a job requires authentication."""
        response = client.post("/api/v1/admin/jobs", json={"source_id": "src_test123"})
        assert response.status_code == 401

    def test_create_job_with_admin_source_not_found(self, client, db_session, mock_admin_client):
        """Test creating a job with non-existent source returns 404."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs", json={"source_id": "src_nonexistent"})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_job_missing_source_id(self, client, db_session, mock_admin_client):
        """Test creating a job without source_id returns 422."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.post("/api/v1/admin/jobs", json={})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422

    def test_create_job_with_valid_source(self, client, db_session, mock_admin_client):
        """Test creating a job with valid source."""
        # Create a source first
        source = Source(
            source_id="src_testjob01",
            name="Test Source for Job",
            connector_type="rss",
        )
        db_session.add(source)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session

        # Mock the Dramatiq task to avoid Redis dependency
        with patch("cyberpulse.api.routers.admin.jobs.ingest_source") as mock_task:
            mock_task.send = Mock()
            try:
                response = client.post("/api/v1/admin/jobs", json={"source_id": "src_testjob01"})
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].startswith("job_")
        assert data["type"] == "INGEST"
        assert data["status"] == "PENDING"
        assert data["source_id"] == "src_testjob01"
        assert data["source_name"] == "Test Source for Job"
        assert data["message"] == "Job created and queued"


class TestJobDetail:
    """Tests for job detail endpoint."""

    def test_get_job_no_auth(self, client):
        """Test that getting job details requires authentication."""
        response = client.get("/api/v1/admin/jobs/job_deadbeef")
        assert response.status_code == 401

    def test_get_job_not_found(self, client, db_session, mock_admin_client):
        """Test getting a non-existent job returns 404."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            # Use valid job_id format (hex after job_) but job doesn't exist
            response = client.get("/api/v1/admin/jobs/job_deadbeef")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_job_invalid_id_format(self, client, db_session, mock_admin_client):
        """Test getting a job with invalid ID format returns 400."""
        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs/invalid_id")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

    def test_get_job_with_valid_id(self, client, db_session, mock_admin_client):
        """Test getting a job with valid ID."""
        # Create a source and job
        source = Source(
            source_id="src_jobdetail01",
            name="Source for Job Detail Test",
            connector_type="rss",
        )
        db_session.add(source)

        job = Job(
            job_id="job_a1b2c3d4",
            type=JobType.INGEST,
            status=JobStatus.COMPLETED,
            source_id="src_jobdetail01",
            created_at=datetime.now(UTC) - timedelta(hours=1),
            started_at=datetime.now(UTC) - timedelta(minutes=30),
            completed_at=datetime.now(UTC) - timedelta(minutes=25),
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs/job_a1b2c3d4")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job_a1b2c3d4"
        assert data["type"] == "INGEST"
        assert data["status"] == "COMPLETED"
        assert data["source_id"] == "src_jobdetail01"
        assert data["source_name"] == "Source for Job Detail Test"
        assert "duration_seconds" in data

    def test_get_job_failed_status(self, client, db_session, mock_admin_client):
        """Test getting a failed job includes error details."""
        # Create a job with failed status
        job = Job(
            job_id="job_deadb33f",
            type=JobType.INGEST,
            status=JobStatus.FAILED,
            source_id=None,
            error_type="ConnectionError",
            error_message="Failed to connect to source",
            created_at=datetime.now(UTC),
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs/job_deadb33f")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "FAILED"
        assert data["error"] is not None
        assert data["error"]["type"] == "ConnectionError"
        assert data["error"]["message"] == "Failed to connect to source"

    def test_get_job_with_retry_count(self, client, db_session, mock_admin_client):
        """Test getting a job with retry count."""
        job = Job(
            job_id="job_c0ffee01",
            type=JobType.INGEST,
            status=JobStatus.RUNNING,
            source_id=None,
            retry_count=3,
            created_at=datetime.now(UTC),
        )
        db_session.add(job)
        db_session.commit()

        app.dependency_overrides[get_current_client] = lambda: mock_admin_client
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            response = client.get("/api/v1/admin/jobs/job_c0ffee01")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["retry_count"] == 3


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
