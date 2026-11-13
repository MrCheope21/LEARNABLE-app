#!/bin/sh
# Installs the macOS login item that runs scripts/learnable-pull-backup.sh every 30 minutes and
# whenever the network changes. Usage:  sh scripts/install-backup-agent.sh user@SERVER_IP [~/.ssh/key]
set -eu
SERVER="${1:?usage: install-backup-agent.sh user@server-ip [ssh-key]}"
KEY="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
printf 'SERVER=%s\nKEY=%s\n' "$SERVER" "$KEY" > "$HOME/.learnable-backup"
chmod 600 "$HOME/.learnable-backup"
PLIST="$HOME/Library/LaunchAgents/com.learnable.backup.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.learnable.backup</string>
  <key>ProgramArguments</key><array><string>/bin/sh</string><string>$ROOT/scripts/learnable-pull-backup.sh</string></array>
  <key>StartInterval</key><integer>1800</integer>
  <key>WatchPaths</key><array><string>/Library/Preferences/SystemConfiguration/NetworkInterfaces.plist</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/com.learnable.backup" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Backups go to ~/LEARNABLE-backups."
