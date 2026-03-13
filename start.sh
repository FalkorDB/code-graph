#!/bin/bash
set -e

# Set default values if not set
FALKORDB_HOST="${FALKORDB_HOST:-localhost}"
FALKORDB_PORT="${FALKORDB_PORT:-6379}"

# Start FalkorDB Redis server in background only if using a local address (not an external instance)
if [ "${FALKORDB_HOST}" = "localhost" ] || [[ "${FALKORDB_HOST}" =~ ^127\.0\.0\.[0-9]+$ ]]; then
    redis-server --loadmodule /var/lib/falkordb/bin/falkordb.so | cat &
fi

# Wait until FalkorDB is ready
FALKORDB_WAIT_TIMEOUT="${FALKORDB_WAIT_TIMEOUT:-30}"
echo "Waiting for FalkorDB to start on $FALKORDB_HOST:$FALKORDB_PORT (timeout: ${FALKORDB_WAIT_TIMEOUT}s)..."

SECONDS=0
while ! nc -z "$FALKORDB_HOST" "$FALKORDB_PORT"; do
  if [ "$SECONDS" -ge "$FALKORDB_WAIT_TIMEOUT" ]; then
    echo "ERROR: FalkorDB did not become reachable at $FALKORDB_HOST:$FALKORDB_PORT within ${FALKORDB_WAIT_TIMEOUT}s" >&2
    exit 1
  fi
  sleep 0.5
done

echo "FalkorDB is up - launching Flask..."

# Start the Flask backend
exec flask --app api/index.py run --host "${HOST:-0.0.0.0}" --port "${PORT:-5000}" ${FLASK_DEBUG:+--debug}
