#!/usr/bin/env bash
# Restores the latest backup made by backup.sh into the stack of THIS machine (run it on the
# standby VM). It replaces the database and the uploaded files here. See docs/DEPLOYMENT_HOME.md.
#   BACKUP_REMOTE=gcs:learnable-backups deploy/home/restore.sh
set -euo pipefail

: "${BACKUP_REMOTE:?set BACKUP_REMOTE to the same rclone path backup.sh uses}"

cd "$(dirname "$0")/../.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

db="$(rclone lsf "$BACKUP_REMOTE" --include 'db-*.sql.gz' | sort | tail -n 1)"
docs="$(rclone lsf "$BACKUP_REMOTE" --include 'documents-*.tar.gz' | sort | tail -n 1)"
[ -n "$db" ] && [ -n "$docs" ] || { echo "no backup found in $BACKUP_REMOTE" >&2; exit 1; }
echo "restoring $db and $docs"
rclone copy "$BACKUP_REMOTE" "$tmp" --include "$db" --include "$docs"

# The backend runs the migrations at startup, so keep it stopped while the database is replaced.
docker compose up -d postgres
docker compose stop backend
gzip -dc "$tmp/$db" | docker compose exec -T postgres sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"' > /dev/null

docker compose run --rm --no-deps -T --user root --entrypoint sh backend \
  -c 'tar xzf - -C /app/var && chown -R appuser:appuser /app/var/documents' < "$tmp/$docs"

docker compose up -d
echo "restored. Check /health, then point the Cloudflare hostname at this machine's tunnel."
