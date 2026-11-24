#!/bin/sh
# Pulls the server's newest backup into ~/LEARNABLE-backups whenever this Mac has internet.
# Quiet and quick when offline; run by launchd every 30 minutes and when the network changes
# (scripts/install-backup-agent.sh). Config: ~/.learnable-backup (SERVER=user@host, KEY optional).
CONF="$HOME/.learnable-backup"
[ -f "$CONF" ] || exit 0
# shellcheck disable=SC1090
. "$CONF"
OUT="$HOME/LEARNABLE-backups"
mkdir -p "$OUT"
SSH="ssh -o ConnectTimeout=8 -o BatchMode=yes ${KEY:+-i $KEY}"
LATEST="$($SSH "$SERVER" 'ls -1t ~/backups/learnable-*.tar.gz 2>/dev/null | head -1')" || exit 0
[ -n "$LATEST" ] || exit 0
NAME="$(basename "$LATEST")"
[ -f "$OUT/$NAME" ] && exit 0
scp -q -o ConnectTimeout=8 -o BatchMode=yes ${KEY:+-i $KEY} "$SERVER:$LATEST" "$OUT/$NAME.part" \
  && mv "$OUT/$NAME.part" "$OUT/$NAME" \
  && echo "$(date) pulled $NAME" >> "$OUT/pull.log"
# Keep the last 30 copies.
ls -1t "$OUT"/learnable-*.tar.gz 2>/dev/null | tail -n +31 | xargs -I{} rm -f {}
