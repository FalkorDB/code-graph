# Multi-stage build: Start with Python 3.12 base
FROM python:3.12-bookworm AS python-base

# Use the official Node image so npm is always available during frontend builds
FROM node:22-bookworm AS node-base

# Main stage: Use FalkorDB base and copy Python 3.12
FROM falkordb/falkordb:latest

ENV PYTHONUNBUFFERED=1 \
    FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379

USER root

# Copy Python 3.12 from the python base image
COPY --from=python-base /usr/local /usr/local

# Copy Node.js tooling from the official Node image
COPY --from=node-base /usr/local/bin/node /usr/local/bin/node
COPY --from=node-base /usr/local/lib/node_modules /usr/local/lib/node_modules

# Install netcat for wait loop in start.sh and system build tools
RUN apt-get update \
    && apt-get install -y -f \
    && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    git \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/local/bin/python3.12 /usr/bin/python \
    && ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

WORKDIR /app

# Install Python dependencies pinned to uv.lock so the image matches CI.
# uv is pinned too: it produces the constraints file, so an unpinned
# upgrade could change `uv export` semantics and break reproducibility.
# It is removed in the same layer, since only the export step needs it.
ARG UV_VERSION=0.12.5
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir --break-system-packages "uv==${UV_VERSION}" \
    && uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/constraints.txt \
    && pip uninstall -y --break-system-packages uv \
    && pip install --no-cache-dir --break-system-packages -c /tmp/constraints.txt . \
    && rm /tmp/constraints.txt

# Verify Node.js tooling for building the frontend
RUN node --version && npm --version

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
