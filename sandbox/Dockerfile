# octopOS Sandbox - Secure Execution Environment
# Base image for ephemeral worker containers

FROM python:3.11-slim-bookworm

LABEL maintainer="octopOS Team"
LABEL description="Secure sandbox for ephemeral task execution"
LABEL version="1.0"

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Security: Create non-root user
RUN groupadd --gid 1000 worker && \
    useradd --uid 1000 --gid worker --shell /bin/bash --create-home worker

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Basic utilities
    curl \
    wget \
    git \
    jq \
    # Build tools (for pip installs)
    build-essential \
    # Python dev headers
    python3-dev \
    # Security tools
    ca-certificates \
    openssl \
    # File operations
    unzip \
    tar \
    gzip \
    # Text processing
    grep \
    sed \
    awk \
    # Network tools (limited)
    netcat-openbsd \
    dnsutils \
    # Process management
    procps \
    htop \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python packages commonly needed by primitives
RUN pip install --no-cache-dir \
    # AWS SDK
    boto3>=1.28.0 \
    botocore>=1.31.0 \
    # HTTP clients
    requests>=2.31.0 \
    httpx>=0.24.0 \
    # Data processing
    numpy>=1.24.0 \
    pandas>=2.0.0 \
    # Utilities
    pydantic>=2.0.0 \
    pyyaml>=6.0.0 \
    python-dotenv>=1.0.0 \
    # Testing
    pytest>=7.4.0 \
    pytest-asyncio>=0.21.0 \
    # Async
    aiohttp>=3.8.0 \
    aiosqlite>=0.19.0

# Set up workspace directory
RUN mkdir -p /workspace && \
    chown -R worker:worker /workspace

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown worker:worker /entrypoint.sh

# Copy security configuration
COPY config/security.conf /etc/octopos/security.conf
COPY config/limits.conf /etc/octopos/limits.conf

# Security hardening
# Remove unnecessary setuid/setgid binaries
RUN find / -perm /6000 -type f -exec chmod a-s {} \; 2>/dev/null || true

# Restrict permissions
RUN chmod 755 /etc/octopos && \
    chmod 644 /etc/octopos/*.conf

# Switch to non-root user
USER worker

# Set working directory
WORKDIR /workspace

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD echo "healthy" || exit 1

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command (can be overridden)
CMD ["python3"]
