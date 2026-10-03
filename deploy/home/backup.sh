#!/usr/bin/env bash
# Sends a database dump and the uploaded files to a remote (e.g. a Google Cloud Storage bucket)
# through rclone, and deletes copies older than KEEP_DAYS. Run from cron; see
# docs/DEPLOYMENT_HOME.md. Needs docker compose, gzip and rclone on the host.
#   BACKUP_REMOTE=gcs:learnable-backups deploy/home/backup.sh
set -euo pipefail

: "${BACKUP_REMOTE:?set BACKUP_REMOTE to an rclone path, e.g. gcs:learnable-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

cd "$(dirname "$0")/../.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
stamp="$(date +%Y-%m-%d-%H%M)"

docker compose exec -T postgres sh -c \
  'pg_dump --clean --if-exists --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$tmp/db-$stamp.sql.gz"
docker compose exec -T backend tar czf - -C /app/var documents > "$tmp/documents-$stamp.tar.gz"

# A dump of an empty or broken database is the failure that goes unnoticed until a restore.
gzip -t "$tmp/db-$stamp.sql.gz"
tar tzf "$tmp/documents-$stamp.tar.gz" > /dev/null
if [ "$(gzip -dc "$tmp/db-$stamp.sql.gz" | grep -c 'CREATE TABLE')" -lt 5 ]; then
  echo "backup aborted: the dump contains no schema" >&2
  exit 1
fi

rclone copy "$tmp" "$BACKUP_REMOTE"
rclone delete "$BACKUP_REMOTE" --min-age "${KEEP_DAYS}d"
echo "$(date -Is) backup $stamp uploaded to $BACKUP_REMOTE"
