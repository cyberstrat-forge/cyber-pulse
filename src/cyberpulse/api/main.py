"""
FastAPI application entry point.
"""
from fastapi import FastAPI

from .routers import content, sources, clients, health

app = FastAPI(
    title="cyber-pulse API",
    description="Security Intelligence Collection System",
    version="0.1.0",
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(content.router, prefix="/api/v1", tags=["content"])
app.include_router(sources.router, prefix="/api/v1", tags=["sources"])
app.include_router(clients.router, prefix="/api/v1", tags=["clients"])