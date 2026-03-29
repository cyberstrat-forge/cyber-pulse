# syntax=docker/dockerfile:1
#
# Cyber Pulse Dockerfile
#
# 优化说明:
# - 使用 uv 替代 pip（符合全局规范）
# - 多阶段构建减小镜像体积
# - 使用 uv.lock 锁定依赖版本，确保构建可复现
#

# ============================================
# Stage 1: Builder
# ============================================
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN uv venv /app/.venv

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies only (exclude the project itself with --no-install-project)
# This uses uv.lock for exact versions (reproducible builds)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and config
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install the project into the virtual environment
RUN uv pip install -e .

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code and config
COPY --from=builder /app/src ./src
COPY --from=builder /app/alembic ./alembic
COPY --from=builder /app/alembic.ini ./

# Copy entrypoint script
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/.venv/bin:$PATH"

# 构建参数：版本号
ARG APP_VERSION=latest
ENV APP_VERSION=$APP_VERSION

# Expose port for API
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint runs migrations, then executes CMD
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Default command: run the API server
CMD ["uvicorn", "cyberpulse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]