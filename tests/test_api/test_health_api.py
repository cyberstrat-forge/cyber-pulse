"""
Tests for health check API endpoint.
"""
import pytest
from unittest.mock import Mock
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from cyberpulse.api.main import app
from cyberpulse.api.routers.health import get_db as health_get_db
from cyberpulse import __version__


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check_healthy(self, client, db_session):
        """Test health check when database is available."""
        # Override the dependency
        app.dependency_overrides[health_get_db] = lambda: db_session
        try:
            response = client.get("/health")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == __version__
        assert data["components"]["api"] == "healthy"
        assert data["components"]["database"] == "healthy"

    def test_health_check_database_unavailable(self, client):
        """Test health check when database is unavailable."""
        # Create a mock session that raises an error on execute
        mock_db = Mock()
        mock_db.execute.side_effect = SQLAlchemyError("Connection refused")

        # Override the dependency
        app.dependency_overrides[health_get_db] = lambda: mock_db
        try:
            response = client.get("/health")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "unhealthy" in data["components"]["database"]
        assert data["components"]["api"] == "healthy"


class TestAppMetadata:
    """Tests for FastAPI app metadata."""

    def test_app_title(self):
        """Test that app has correct title."""
        assert app.title == "cyber-pulse API"

    def test_app_description(self):
        """Test that app has correct description."""
        assert app.description == "Security Intelligence Collection System"

    def test_app_version(self):
        """Test that app has correct version."""
        assert app.version == __version__


class TestRouterRegistration:
    """Tests for router registration."""

    def test_health_router_registered(self):
        """Test that health router is registered."""
        from fastapi.routing import APIRoute
        routes = [route.path for route in app.routes if isinstance(route, APIRoute)]
        assert "/health" in routes

    def test_routers_included(self):
        """Test that all routers are included in the app."""
        # Check that the app has the expected routers by checking the routes
        from cyberpulse.api.routers import health, sources, clients

        # Health router should have routes
        assert len(health.router.routes) == 1  # /health endpoint

        # Placeholder routers should exist but have no routes yet
        assert sources.router is not None
        assert clients.router is not None