# octopOS Production Dockerfile
# EC2 deployment için optimize edilmiş image

FROM python:3.11-slim-bookworm

# Metadata
LABEL maintainer="octopOS Team"
LABEL description="octopOS - Agentic Operating System"

# -----------------------------------------------------------------------------
# Stage 1: Base dependencies
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm as base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # AWS CLI dependencies
    # curl \
    # git \
    # Docker client (for worker pool)
    # Development tools (optional)
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Application build
# -----------------------------------------------------------------------------
FROM base as builder

# Install pip and build tools
RUN pip install --no-cache-dir --break-system-packages \
    pip>=23.0 \
    build

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# -----------------------------------------------------------------------------
# Stage 3: Production image
# -----------------------------------------------------------------------------
FROM base as production

# Create non-root user
RUN groupadd -r octopos && \
    useradd -r -g octopos -d /home/octopos -s /bin/bash octopos

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=octopos:octopos src /app/src
COPY --chown=octopos:octopos pyproject.toml /app/
COPY --chown=octopos:octopos README.md /app/

# Create data directories
RUN mkdir -p /data /workspace /config && \
    chown -R octopos:octopos /app /data /workspace

WORKDIR /app

# Switch to non-root user
USER octopos

# Expose port
EXPOSE 8080

# Health check - checks if port 8080 is listening
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "
import sys
import socket
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8080))
    sock.close()
    sys.exit(0 if result == 0 else 1)
except Exception:
    sys.exit(1)
" || exit 1

# Default command
CMD ["python", "-m", "src.interfaces.cli.main", "chat"]