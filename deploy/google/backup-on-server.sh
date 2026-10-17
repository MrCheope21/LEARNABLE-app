#!/bin/sh
# Daily on the server (cron): a consistent copy of the database plus the uploaded files, in
# ~/backups, keeping the last 14 days. The Mac pulls these (scripts/learnable-pull-backup.sh).
set -eu
DEST="$HOME/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
docker run --rm -v learnable_app_var:/v:ro -v "$DEST":/out python:3.12-slim python - "$STAMP" <<'PY'
import sqlite3, sys, tarfile, os, tempfile
stamp = sys.argv[1]
src = sqlite3.connect("file:/v/learnable.db?mode=ro", uri=True)
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "learnable.db")
dst = sqlite3.connect(db)
src.backup(dst)  # safe while the app is writing
dst.close()
with tarfile.open(f"/out/learnable-{stamp}.tar.gz", "w:gz") as tar:
    tar.add(db, arcname="learnable.db")
    if os.path.isdir("/v/documents"):
        tar.add("/v/documents", arcname="documents")
PY
ls -1t "$DEST"/learnable-*.tar.gz | tail -n +15 | xargs -r rm -f
echo "$(date -Is) backup learnable-$STAMP.tar.gz ok"
