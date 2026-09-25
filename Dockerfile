# Production Dockerfile for DRDO iDEX MALE UAV Aero Engine Digital Twin
# Base Image: Python 3.11-slim (Debian Linux)
FROM python:3.11-slim

# Set environment variables for non-interactive, unbuffered execution
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Create non-root application user for container execution safety
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install CPU-only PyTorch first to keep image size under 1.5 GB (~160 MB wheel)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy dependency specification and install remaining backend requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire repository application source code and model artifacts
COPY --chown=appuser:appuser . /app

# Ensure data directory permissions for lightweight SQLite persistence
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

# Switch to non-root user
USER appuser

# Expose HTTP & WebSocket server port
EXPOSE 8000

# Server execution entrypoint (Uvicorn 10Hz streaming orchestrator with dynamic PORT)
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
