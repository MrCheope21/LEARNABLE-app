#!/bin/sh
# Run ONCE on the new VM (Debian/Ubuntu), as your normal user:  sh setup-vm.sh
# Adds swap (a 1 GB VM can't build the web app without it), installs Docker and git, and makes
# the daily backup job. It does not touch your data or secrets.
set -eu

if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
sudo apt-get install -y git >/dev/null

REPO="$HOME/LEARNABLE-app"
[ -d "$REPO" ] || git clone https://github.com/MrCheope21/LEARNABLE-app.git "$REPO"

mkdir -p "$HOME/backups"
CRON="17 3 * * * sh $REPO/deploy/google/backup-on-server.sh >> $HOME/backups/backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v backup-on-server.sh; echo "$CRON" ) | crontab -

echo
echo "Done. Log out and back in (so Docker works without sudo), then follow docs/DEPLOYMENT_GOOGLE.md step 5."
