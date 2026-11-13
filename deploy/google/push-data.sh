#!/bin/sh
# Run on your MAC, once: copies your local database and uploaded files to the new server.
# Usage:  sh deploy/google/push-data.sh youruser@SERVER_IP
# Stop the server's app first (the guide says when). A copy of the old data stays on the server.
set -eu
TARGET="${1:?usage: push-data.sh user@server-ip}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sqlite3 "$ROOT/backend/dev.db" ".backup '$TMP/learnable.db'"
mkdir -p "$TMP/documents"
[ -d "$ROOT/backend/var/documents" ] && cp -R "$ROOT/backend/var/documents/." "$TMP/documents/"
tar -czf "$TMP/data.tar.gz" -C "$TMP" learnable.db documents
scp "$TMP/data.tar.gz" "$TARGET:/tmp/learnable-data.tar.gz"
ssh "$TARGET" 'docker run --rm -v learnable_app_var:/v -v /tmp:/in alpine sh -c "
  mkdir -p /v/old && cp -a /v/learnable.db /v/documents /v/old/ 2>/dev/null || true
  tar -xzf /in/learnable-data.tar.gz -C /v && chown -R 10001:10001 /v" && rm /tmp/learnable-data.tar.gz'
echo "Data copied. On the server run:  docker compose -f deploy/google/docker-compose.yml up -d"
