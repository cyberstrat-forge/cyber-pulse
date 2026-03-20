FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# - gcc: Required for compiling some Python packages
# - libpq-dev: Required for psycopg2 PostgreSQL adapter
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml README.md ./

# Copy source code (required for editable install)
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Install Python dependencies (production only, no dev tools)
RUN pip install --no-cache-dir -e "."

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port for API
EXPOSE 8000

# Default command: run the API server
CMD ["uvicorn", "cyberpulse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]