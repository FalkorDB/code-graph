# Multi-stage build: Start with Python 3.12 base
FROM python:3.12-bookworm AS python-base

# Main stage: Use FalkorDB base and copy Python 3.12
FROM falkordb/falkordb:latest

ENV PYTHONUNBUFFERED=1 \
    FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379

USER root

# Copy Python 3.12 from the python base image
COPY --from=python-base /usr/local /usr/local

# Install netcat for wait loop in start.sh and system build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    git \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/local/bin/python3.12 /usr/bin/python

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --break-system-packages .

# Install Node.js for building the frontend
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# Copy frontend package files and install dependencies
COPY app/package*.json ./app/
RUN if [ -f ./app/package-lock.json ]; then \
        npm --prefix ./app ci --no-audit --no-fund; \
    elif [ -f ./app/package.json ]; then \
        npm --prefix ./app install --no-audit --no-fund; \
    fi

# Copy frontend source and build
COPY ./app ./app
RUN npm --prefix ./app run build

# Copy backend code
COPY ./api ./api

# Copy and make start.sh executable
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 5000 6379

# Use start.sh as entrypoint
ENTRYPOINT ["/start.sh"]

