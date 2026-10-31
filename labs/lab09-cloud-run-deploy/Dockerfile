# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install uv from the official Astral image for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

# Copy dependency metadata first so Docker caches the layer when only code changes
COPY pyproject.toml ./
RUN uv pip install --system --no-cache fastapi>=0.115.0 pydantic>=2.7.0 uvicorn>=0.30.0

# Create a dedicated non-root user so the container never runs as root
RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /sbin/nologin --create-home appuser

# Copy application source code and assign ownership to appuser
COPY --chown=appuser:appgroup production_app.py ./

USER appuser

EXPOSE 8080

# Cloud Run injects the PORT environment variable automatically
CMD ["uvicorn", "production_app:app", "--host", "0.0.0.0", "--port", "8080"]
